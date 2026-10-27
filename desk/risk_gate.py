"""The risk gate: code, not an agent. Every order passes here at the clock tick, and the gate sizes it.

An agent can propose and the head trader can approve, but only check() turns a ticket into an order, in this order:
  1. halts      KILL file, daily / weekly loss stop, drawdown kill (logs/desk/state/limits.json)
  2. ticket     fields valid, pod active in this phase, pod owns the instrument, profile allows it
  3. market     symbol tradable, fresh price, spread under spread_mult x normal, no high-impact news inside the window;
                the event pod only 15-240 min after a release for its instrument
  4. risk       asked risk x the pod's competition tilt, capped at per_trade_pct and the new-edge cap, x the phase scale;
                the pod stop halves it at a 3% month loss on the pod's allocation and refuses at 5%
  5. book       pod, desk, group, net-USD and per-instrument limits; netting (never both sides of one instrument);
                adds only to a ticket already at breakeven
  6. prop       weekend cutoff, every open stop hit at once must leave the daily and max-loss floors intact
  7. size       volume from the stop distance, rounded down to the lot step; stop beyond stops_level; margin share
Only the owner edits risk.json; the gate reads it on every check.
"""
import datetime as dt
import math

from desk import clocks, journal, news, paths, phase, spreads, tickets

LIMITS = paths.STATE / "limits.json"
FREE_ROAM_PODS = ("systematic", "event")  # may trade any instrument; the others trade what they own


def profile():
    r = paths.risk()
    name = r.get("active")
    return name, r.get("profiles", {}).get(name, {})


# ---- 1. halts --------------------------------------------------------------------------------------------------

def limits():
    return paths.read_json(LIMITS, {})


HALT_RANK = {"day": 1, "week": 2, "kill": 3}


def update_limits(acct, prof, t=None, name=None):
    """Roll the day and week, track the equity peak, and set a halt when a loss line is crossed. Returns the state.

    halt levels: 'day' clears at the next server day; 'week' (DESIGN §9: stop until the owner reviews) and 'kill' only
    by the owner (cli resume). A halt is never downgraded by a milder one.
    """
    t = t or clocks.now()
    s = limits()
    day, week = clocks.trading_day(t).isoformat(), clocks.week_key(t)
    bal, eq = acct["balance"], acct["equity"]
    who = f"{acct.get('company')}/{acct.get('kind')}/{name}"
    if s.get("account") != who:
        # a new account or risk profile starts its own lines: the old peak and day/week marks belong to the old one
        for k in ("day", "week", "peak", "day_balance", "day_equity", "week_equity"):
            s.pop(k, None)
        if s.get("halt", {}).get("level") in ("day", "week"):
            s.pop("halt")
        s["account"] = who
    if s.get("day") != day:
        s.update(day=day, day_balance=bal, day_equity=eq)
        if s.get("halt", {}).get("level") == "day":
            s.pop("halt")
    if s.get("week") != week:
        s.update(week=week, week_equity=eq)
        if s.get("halt", {}).get("level") == "day":
            s.pop("halt")
    s["peak"] = max(s.get("peak", eq), eq)
    s["equity"], s["balance"] = eq, bal
    # the live gate's drawdown record: never reset by resume, only when the account changes
    rec = s.get("record") or {}
    if rec.get("account") != who:
        rec = {"account": who, "peak": eq, "max_dd_pct": 0.0, "since": t.isoformat(timespec="seconds")}
    rec["peak"] = max(rec["peak"], eq)
    rec["max_dd_pct"] = round(max(rec["max_dd_pct"], (rec["peak"] - eq) / rec["peak"] * 100 if rec["peak"] else 0), 3)
    s["record"] = rec
    fl = floors(s, prof)
    s["floors"] = fl
    if s.get("halt", {}).get("level") != "kill":
        why = None
        if eq <= fl["kill"]:
            level, why = "kill", f"equity {eq:.2f} at or under the kill floor {fl['kill']:.2f}"
        elif eq <= fl["week"]:
            level, why = "week", f"weekly loss: equity {eq:.2f} under {fl['week']:.2f}"
        elif eq <= fl["day"]:
            level, why = "day", f"daily loss: equity {eq:.2f} under {fl['day']:.2f}"
        if why and HALT_RANK[level] > HALT_RANK.get(s.get("halt", {}).get("level"), 0):
            s["halt"] = {"level": level, "why": why, "t": t.isoformat(timespec="seconds")}
            journal.log("halt", level=level, why=why)
    paths.write_json(LIMITS, s)
    return s


def floors(s, prof):
    """Equity lines: day, week, kill. A prop profile measures the daily loss on the initial balance from the day's
    start (the higher of balance and equity then) and adds the static max-loss floor to the kill line."""
    eq_day = max(s.get("day_balance", 0), s.get("day_equity", 0))
    if prof.get("kind") == "prop":
        init = prof["initial_balance"]
        day = eq_day - init * prof["daily_loss_pct"] / 100
        kill = max(s["peak"] * (1 - prof["kill_dd_pct"] / 100), init * (1 - prof["max_loss_pct"] / 100))
    else:
        day = eq_day * (1 - prof.get("daily_loss_pct", 3) / 100)
        kill = s["peak"] * (1 - prof.get("kill_dd_pct", 12) / 100)
    week = s.get("week_equity", eq_day) * (1 - prof.get("weekly_loss_pct", 6) / 100)
    return {"day": day, "week": week, "kill": kill}


def halted():
    """Why new trades are stopped, or None. The KILL file beats everything."""
    if paths.KILL.exists():
        return "KILL file: " + (paths.KILL.read_text(encoding="utf-8").strip() or "kill switch on")
    h = limits().get("halt")
    return f"{h['level']} halt: {h['why']}" if h else None


def kill(why, by="code"):
    paths.KILL.parent.mkdir(parents=True, exist_ok=True)
    paths.KILL.write_text(f"{clocks.now().isoformat(timespec='seconds')} {by}: {why}\n", encoding="utf-8")
    s = limits()
    s["halt"] = {"level": "kill", "why": why, "t": clocks.now().isoformat(timespec="seconds")}
    paths.write_json(LIMITS, s)
    journal.log("kill", why=why, by=by)


def resume(by):
    """Owner only: clear the KILL file and any halt; the peak resets to today's equity."""
    if paths.KILL.exists():
        paths.KILL.unlink()
    s = limits()
    s.pop("halt", None)
    if "equity" in s:
        s["peak"] = s["equity"]
    paths.write_json(LIMITS, s)
    journal.log("resume", by=by)


# ---- helpers ---------------------------------------------------------------------------------------------------

def exposure(tk):
    """Percent of balance a live ticket can still lose: 0 once its stop is at breakeven or better."""
    if tk.get("status") not in ("placed", "open"):
        return 0.0
    return float(tk.get("risk_now", tk.get("risk_used", 0)) or 0)


def edge_key(tk):
    return tk.get("edge") or f"{tk.get('pod')}:discretionary"


def edge_trades(key, state):
    return sum(1 for v in state.values() if v.get("status") == "closed" and edge_key(v) == key)


def groups_of(instrument, cfg):
    return [g for g, members in cfg.get("groups", {}).items() if instrument in members]


SOFT = {"pod_stop": {"halve_pct": 3.0, "pause_pct": 5.0, "alloc_mult": 3.0}, "net_usd": {"share_of_desk": 0.6},
        "event_pod": {"min_delay_min": 15, "max_after_min": 240}}


def soft_limits(cfg):
    """config.json "limits" over the defaults: desk limits the code keeps, below the owner's risk.json."""
    got = cfg.get("limits") or {}
    return {k: {**v, **(got.get(k) or {})} for k, v in SOFT.items()}


def usd_sign(instrument, side):
    """+1 when the position is long USD, -1 short, 0 when it has no USD leg (indices, oil and crypto left out)."""
    if len(instrument) != 6 or "USD" not in (instrument[:3], instrument[3:]) or instrument[:3] in ("BTC", "ETH"):
        return 0
    s = 1 if instrument[:3] == "USD" else -1
    return s if side == "buy" else -s


def pod_month_loss(pod, state, cfg, prof, acct, t):
    """(realised loss this calendar month, allocation) for a pod, both in account money.

    The allocation is the pod's share (the weekly competition's, else its base) of the initial balance (prop) or the
    balance, times alloc_mult: pod-shop books are levered against their capital, and a bare 2,000 sleeve would stop at
    about one loss."""
    month = t.strftime("%Y-%m")
    pnl = sum(float(v.get("pnl") or 0) for v in state.values()
              if v.get("status") == "closed" and v.get("pod") == pod and str(v.get("updated", "")).startswith(month))
    pods = cfg.get("pods", {})
    tot = sum(float(v.get("base_share", 0)) for v in pods.values()) or 1
    share = (paths.read_json(phase.ALLOC, {}).get("shares") or {}).get(pod)
    if share is None:
        share = float(pods.get(pod, {}).get("base_share", 0)) / tot
    bal = float(prof.get("initial_balance") or acct.get("balance") or 0)
    return max(0.0, -pnl), share * bal * soft_limits(cfg)["pod_stop"]["alloc_mult"]


def round_step(x, step):
    return math.floor(x / step + 1e-9) * step


def weekend_cutoff(prof, t):
    """True once a flat-before-weekend profile is past its Friday cutoff (New York)."""
    if not prof.get("flat_before_weekend"):
        return False
    ny = t.astimezone(clocks.NY)
    h, m = clocks.parse_hhmm(prof.get("weekend_cutoff_ny", "15:00"))
    return ny.weekday() == 4 and (ny.hour, ny.minute) >= (h, m) or ny.weekday() in (5, 6)


# ---- the check -------------------------------------------------------------------------------------------------

def check(tk, b, cfg=None, prof=None, ph=None, state=None, t=None):
    """Turn an approved ticket into an order, or say why not. Returns {"ok", "why", ...order fields}."""
    cfg = cfg or paths.config()
    if prof is None:
        _, prof = profile()
    ph = phase.current() if ph is None else ph
    state = tickets.fold() if state is None else state
    t = t or clocks.now()
    soft = soft_limits(cfg)

    def no(why):
        return {"ok": False, "why": why}

    if not prof:
        return no("risk profile missing in risk.json")

    # 1. halts
    h = halted()
    if h:
        return no(h)
    acct = b.account()
    if not acct:
        return no("no account")
    if acct["kind"] == "live" and not prof.get("allow_live"):
        return no("live account and risk.json does not allow live")
    if not acct.get("trade_allowed") or not acct.get("terminal_algo"):
        return no("trading not allowed on the account or Algo Trading is off")

    # 2. ticket
    errs = tickets.validate(tk, cfg)
    if errs:
        return no("invalid: " + "; ".join(errs))
    pod, ins, side = tk["pod"], tk["instrument"], tk["side"]
    if pod not in phase.pods_active(cfg, ph):
        return no(f"pod {pod} not active in phase {ph}")
    owns = cfg["pods"][pod].get("owns") or []
    if pod not in FREE_ROAM_PODS and owns and ins not in owns:
        return no(f"{pod} does not trade {ins}")
    if cfg["instruments"][ins].get("class") == "crypto" and prof.get("allow_crypto") is False:
        return no("crypto not allowed on this profile")
    if weekend_cutoff(prof, t):
        return no("past the weekend cutoff")

    # 3. market
    sym = b.resolve(ins)
    if not sym:
        return no(f"{ins} not offered by this broker")
    spec, tick = b.spec(sym), b.tick(sym)
    if not spec or not tick:
        return no(f"no spec or price for {sym}")
    if spec.get("trade_mode", 4) != 4:
        return no(f"{sym} not open for new trades (trade_mode {spec.get('trade_mode')})")
    if t - tick["time"] > dt.timedelta(minutes=5):
        return no(f"{sym} price is stale ({tick['time']:%H:%M} UTC); market closed?")
    ok, why = spreads.check(b, sym, spec, tick, prof.get("spread_mult", 2.0), cfg["instruments"][ins].get("cost"), t)
    if not ok:
        return no("spread: " + why)
    win = prof.get("news_window_min", 2)
    if pod == "event":
        # the event pod trades the reaction, never the release: blocked min_delay either side of one, and only
        # inside max_after of a release that moves this instrument
        lim = soft["event_pod"]
        win = max(win, lim["min_delay_min"])
    ev = news.blocking(ins, t, win)
    if ev:
        return no(f"news: {ev['ccy']} {ev['title']} at {ev['t']}")
    if pod == "event":
        ccy = news.currencies(ins)
        after = [e for e in news.events(t - dt.timedelta(minutes=lim["max_after_min"]),
                                        t - dt.timedelta(minutes=lim["min_delay_min"])) if e["ccy"] in ccy]
        if not after:
            return no(f"event pod: no {'/'.join(ccy)} release between {lim['min_delay_min']} and "
                      f"{lim['max_after_min']} min ago")

    # 4. risk
    asked = float(tk.get("risk_pct") or prof["per_trade_pct"])
    ceiling = prof["per_trade_pct"]
    key = edge_key(tk)
    n = edge_trades(key, state)
    if n < prof.get("new_edge_trades", 20):
        ceiling = min(ceiling, prof["new_edge_cap_pct"])
    scale = phase.risk_scale(prof, ph)
    # the competition tilts a pod's risk by its share, but never past the per-trade or new-edge cap
    risk = min(asked * phase.tilt(pod), ceiling) * scale
    if risk <= 0:
        return no(f"phase {ph} trades no risk")
    lost, alloc = pod_month_loss(pod, state, cfg, prof, acct, t)
    ps = soft["pod_stop"]
    if alloc and lost >= ps["pause_pct"] / 100 * alloc:
        return no(f"pod stop: {pod} lost {lost:.2f} this month, {lost / alloc * 100:.1f}% of its {alloc:.0f} "
                  f"allocation (stop {ps['pause_pct']}%)")
    if alloc and lost >= ps["halve_pct"] / 100 * alloc:
        risk *= 0.5

    # 5. book
    live = [v for v in state.values() if v.get("status") in ("placed", "open") and v["id"] != tk.get("id")]
    same = [v for v in live if v["instrument"] == ins]
    if any(v["side"] != side for v in same):
        return no(f"netting: the desk already holds the other side of {ins}")
    if len(same) >= prof.get("max_per_instrument", 3):
        return no(f"{ins} already has {len(same)} desk positions")
    mine = [v for v in same if v["pod"] == pod]
    slots = tk.get("arm") and tk.get("edge") and all(
        v.get("edge") == tk["edge"] and int(v.get("slot") or 0) != int(tk.get("slot") or 0) for v in mine)
    if mine and not slots:  # an armed grid holds one position per level (slot) of the same edge
        add = tk.get("add_to")
        base = state.get(add) if add else None
        if (not base or base.get("status") != "open" or exposure(base) > 0
                or base.get("instrument") != ins or base.get("pod") != pod):
            return no(f"{pod} already holds {ins}; add only with add_to a ticket whose stop is at breakeven")
    pod_open = sum(exposure(v) for v in live if v["pod"] == pod)
    if pod_open + risk > prof["pod_cap_pct"] + 1e-9:
        return no(f"pod cap: {pod_open:.2f}% open + {risk:.2f}% > {prof['pod_cap_pct']}%")
    desk_open = sum(exposure(v) for v in live)
    if desk_open + risk > prof["desk_open_pct"] + 1e-9:
        return no(f"desk cap: {desk_open:.2f}% open + {risk:.2f}% > {prof['desk_open_pct']}%")
    for g in groups_of(ins, cfg):
        g_open = sum(exposure(v) for v in live if v["instrument"] in cfg["groups"][g])
        if g_open + risk > prof["group_open_pct"] + 1e-9:
            return no(f"group {g} cap: {g_open:.2f}% open + {risk:.2f}% > {prof['group_open_pct']}%")
    # one dollar bet spread over pods and groups: the net may shrink freely but not grow past the cap
    sign = usd_sign(ins, side)
    if sign:
        net = sum(usd_sign(v["instrument"], v["side"]) * exposure(v) for v in live)
        cap = soft["net_usd"]["share_of_desk"] * prof["desk_open_pct"]
        if abs(net + sign * risk) > max(abs(net), cap) + 1e-9:
            return no(f"net USD cap: {net:+.2f}% open {sign * risk:+.2f}% > {cap:.2f}%")

    # 6. prop: all open stops hit at once plus this one must stay above the floors
    if prof.get("worst_case_daily"):
        fl = limits().get("floors") or {}
        # open profit may be given back before the stops are hit, so start from the lower of balance and equity
        worst = min(acct["equity"], acct["balance"]) - (desk_open + risk) / 100 * acct["balance"]
        for name in ("day", "week", "kill"):
            if name in fl and worst <= fl[name]:
                return no(f"worst case {worst:.2f} would breach the {name} floor {fl[name]:.2f}")

    # 7. size
    e = tk.get("entry") or {"type": "market"}
    entry = float(e["price"]) if e.get("type") in ("limit", "stop") else (tick["ask"] if side == "buy" else tick["bid"])
    stop = float(tk["stop"])
    if (side == "buy" and stop >= entry) or (side == "sell" and stop <= entry):
        return no(f"stop {stop} is on the wrong side of the price {entry}")
    dist = abs(entry - stop)
    spread = tick["ask"] - tick["bid"]
    min_dist = spec.get("stops_level", 0) * spec["point"] + spread
    if dist < min_dist:
        return no(f"stop {dist:.6g} away, closer than the broker allows ({min_dist:.6g})")
    if e.get("type") == "limit" and (side == "buy" and entry >= tick["ask"] or side == "sell" and entry <= tick["bid"]):
        return no("limit price is through the market; send it as market")
    if e.get("type") == "stop" and (side == "buy" and entry <= tick["ask"] or side == "sell" and entry >= tick["bid"]):
        return no("stop-entry price is already passed")
    base_bal = min(acct["balance"], acct["equity"])
    loss_per_lot = dist / spec["tick_size"] * spec["tick_value"]
    vol = round_step(base_bal * risk / 100 / loss_per_lot, spec["vol_step"])
    vol = min(vol, spec["vol_max"])
    if vol < spec["vol_min"] - 1e-12:
        return no(f"stop too wide: the minimum lot {spec['vol_min']} would risk "
                  f"{spec['vol_min'] * loss_per_lot / base_bal * 100:.2f}% > {risk:.2f}%")
    used = vol * loss_per_lot / base_bal * 100
    margin = b.calc_margin(sym, side, vol, entry)
    if margin is not None and acct["margin"] + margin > prof.get("max_margin_share", 0.5) * acct["equity"]:
        return no(f"margin {acct['margin'] + margin:.0f} would pass {prof.get('max_margin_share', 0.5):.0%} of equity")
    tp = float(tk["targets"][-1][0]) if tk.get("targets") else 0.0
    magic = cfg["magic_base"] + cfg["pods"][pod]["index"]
    return {"ok": True, "why": f"risk {used:.3f}% (asked {asked}%, edge trades {n}, phase {ph} x{scale})",
            "symbol": sym, "side": side, "volume": round(vol, 8), "kind": e.get("type", "market"),
            "price": entry, "sl": stop, "tp": tp, "magic": magic, "risk_used": round(used, 4),
            "loss_per_lot": loss_per_lot}
