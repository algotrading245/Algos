"""The executor: code, not an agent. Every clock tick it turns approved tickets into orders (through the risk gate),
matches the terminal to the tickets, and manages each open position by its ticket.

  run()        the whole pass: limits and halts, reconcile, flatten if halted, manage, execute, reconcile again
  reconcile()  placed -> open when the order filled; open -> closed when the position is gone (P&L from the deals);
               desk positions or orders no ticket knows are closed
  manage()     partial targets (all but the last, which sits on the broker as the TP), breakeven, trail, time stop,
               an agent's close or tighter-stop request; risk_now kept current for the gate
  execute()    approved tickets through risk_gate.check(); spread, news and stale prices wait, anything else blocks

Every order carries a server-side stop. A stop only ever moves toward the price.
"""
import datetime as dt

from desk import clocks, journal, paths, phase, risk_gate, tickets

REASONS = {0: "manual", 1: "mobile", 2: "web", 3: "desk", 4: "stop", 5: "target", 6: "stop_out"}
TRANSIENT = ("spread:", "news:", "price is stale", "no spec or price", "not open for new trades", "no account",
             "Algo Trading is off")
MARKET_TTL = dt.timedelta(minutes=30)  # an approved market ticket with no expires waits at most this long
PENDING_TTL = dt.timedelta(hours=24)  # a limit or stop entry with no expires lives at most this long
SETTLE_WAIT = dt.timedelta(minutes=10)  # how long a vanished position waits for its deals before closing blind


def _t(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=clocks.UTC)
    try:
        v = dt.datetime.fromisoformat(str(s))
    except ValueError:
        return None
    return v if v.tzinfo else v.replace(tzinfo=clocks.UTC)


def desk_magic(m, cfg):
    return cfg["magic_base"] <= int(m or 0) < cfg["magic_base"] + 100


def _round_px(x, spec):
    return round(float(x), int(spec.get("digits", 5)))


def _loss_to_stop(side, entry, sl, volume, spec):
    """Money lost if the stop is hit from this entry; 0 once the stop is at breakeven or better."""
    if not sl:
        return None
    d = (entry - sl) if side == "buy" else (sl - entry)
    return max(0.0, d) / spec["tick_size"] * spec["tick_value"] * volume


# ---- reconcile ---------------------------------------------------------------------------------------------------

def _deals(b, state, t):
    live = [v for v in state.values() if v.get("status") in ("placed", "open")]
    starts = [_t(v.get("created")) for v in live if _t(v.get("created"))]
    since = min(starts) - dt.timedelta(hours=1) if starts else t - dt.timedelta(days=1)
    return b.deals_since(max(since, t - dt.timedelta(days=30)))


def settle(b, tk, deals=None, t=None, why=None):
    """Close an open ticket whose position is gone: P&L is every deal of the position (commission and swap in)."""
    t = t or clocks.now()
    pid = tk.get("position")
    deals = deals if deals is not None else b.deals_since(_t(tk.get("created")) - dt.timedelta(hours=1))
    mine = [d for d in deals if d.get("position") == pid]
    outs = [d for d in mine if d.get("entry") in ("out", "inout", "out_by")]
    if not outs:
        seen = _t(tk.get("gone_since"))
        if seen is None:
            tickets.update(tk["id"], gone_since=t.isoformat(timespec="seconds"))
            return False
        if t - seen < SETTLE_WAIT:
            return False
        tickets.closed(tk["id"], pnl=None, exit=None, reason=why or tk.get("closing") or "unknown",
                       note="position gone, no closing deal found")
        return True
    pnl = round(sum(float(d.get("profit") or 0) for d in mine), 2)
    last = max(enumerate(outs), key=lambda x: (x[1]["time"], x[0]))[1]  # same-second deals: the later one
    reason = tk.get("closing") or why or REASONS.get(last.get("reason"), str(last.get("reason")))
    rm = tk.get("risk_money")
    r = round(pnl / rm, 3) if rm else None
    tickets.closed(tk["id"], pnl=pnl, exit=last.get("price"), reason=reason, R=r,
                   exit_time=last["time"].isoformat(timespec="seconds") if hasattr(last["time"], "isoformat") else last["time"])
    return True


def reconcile(b, cfg, state=None, t=None):
    """Bring the tickets in line with the terminal. Returns the refreshed state."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    pos = b.positions()
    ords = b.orders()
    deals = _deals(b, state, t)
    by_pos = {p["ticket"]: p for p in pos}
    by_ord = {o["ticket"]: o for o in ords}
    known_pos, known_ord = set(), set()

    for tk in [v for v in state.values() if v.get("status") == "placed"]:
        tid, oid = tk["id"], tk.get("order")
        p = next((p for p in pos if p.get("comment") == tid), None)
        if p is None:
            d = next((d for d in deals if d.get("entry") == "in" and oid and d.get("order") == oid), None)
            if d is not None:
                p = by_pos.get(d["position"]) or {"ticket": d["position"], "price_open": d["price"],
                                                   "volume": d["volume"], "sl": tk.get("sl"), "gone": True}
        if p is not None:
            spec = b.spec(tk["symbol"]) or {}
            fill = float(p["price_open"])
            loss = _loss_to_stop(tk["side"], fill, p.get("sl") or tk.get("sl"), p["volume"], spec) if spec else None
            base = tk.get("risk_money") / (tk.get("risk_used") or 1) * 100 if tk.get("risk_money") else None
            extra = {"risk_now": round(loss / base * 100, 4)} if loss is not None and base else {}
            tickets.opened(tid, position=p["ticket"], fill=fill, volume=p["volume"],
                           open_time=t.isoformat(timespec="seconds"), initial_volume=p["volume"], **extra)
            known_pos.add(p["ticket"])
            tk = dict(tk, status="open", position=p["ticket"], fill=fill, volume=p["volume"])
            state[tid] = tk
            if p.get("gone"):
                settle(b, tk, deals, t)
            continue
        if oid in by_ord:
            known_ord.add(oid)
            exp = _t(tk.get("expires_at"))
            if exp and t >= exp:
                r = b.cancel(oid)
                if r.get("ok"):
                    tickets.expire(tid, "entry not reached before it expired")
            continue
        if _t(tk.get("updated")) and t - _t(tk["updated"]) > dt.timedelta(minutes=2):
            tickets.expire(tid, "order gone without a fill (expired or cancelled at the broker)")

    for tk in [v for v in state.values() if v.get("status") == "open"]:
        pid = tk.get("position")
        if pid in by_pos:
            known_pos.add(pid)
            continue
        settle(b, tk, deals, t)

    for p in pos:
        if p["ticket"] not in known_pos and desk_magic(p.get("magic"), cfg):
            journal.log("orphan_position", ticket=p["ticket"], symbol=p["symbol"], comment=p.get("comment"))
            b.close_position(p["ticket"])
    for o in ords:
        if o["ticket"] not in known_ord and desk_magic(o.get("magic"), cfg):
            journal.log("orphan_order", ticket=o["ticket"], symbol=o["symbol"], comment=o.get("comment"))
            b.cancel(o["ticket"])
    return tickets.fold()


# ---- halts -------------------------------------------------------------------------------------------------------

def flatten(b, cfg, why, state=None, t=None):
    """Close every desk position, cancel every desk order and every ticket not yet placed."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    n = 0
    for o in b.orders():
        if desk_magic(o.get("magic"), cfg):
            b.cancel(o["ticket"])
            n += 1
    for p in b.positions():
        if desk_magic(p.get("magic"), cfg):
            b.close_position(p["ticket"])
            n += 1
    for tk in state.values():
        st = tk.get("status")
        if st in ("proposed", "approved"):
            tickets.cancel(tk["id"], why, by="risk-gate")
        elif st == "placed":
            tickets.cancel(tk["id"], why, by="risk-gate")
        elif st == "open" and not tk.get("closing"):
            tickets.update(tk["id"], closing=why)
    if n:
        journal.log("flatten", why=why, orders_and_positions=n)
    return n


# ---- manage ------------------------------------------------------------------------------------------------------

def atr(b, sym, tf, n):
    df = b.bars(sym, tf, n + 1)
    if df is None or len(df) < n + 1:
        return None
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(df))]
    return sum(tr[-n:]) / n


def _better(side, new, old):
    """True if a new stop is tighter (closer to the price, less risk) than the old one."""
    if not old:
        return True
    return new > old if side == "buy" else new < old


def _move_stop(b, tk, p, spec, tick, sl, why):
    sl = _round_px(sl, spec)
    if not _better(tk["side"], sl, p.get("sl")):
        return False
    gap = spec.get("stops_level", 0) * spec["point"]
    if tk["side"] == "buy" and sl > tick["bid"] - gap or tk["side"] == "sell" and sl < tick["ask"] + gap:
        return False
    r = b.modify_position(p["ticket"], sl=sl)
    if not r.get("ok"):
        journal.log("sl_move_fail", id=tk["id"], sl=sl, why=why, comment=r.get("comment"))
        return False
    p["sl"] = sl
    journal.log("sl_move", id=tk["id"], sl=sl, why=why)
    return True


def manage(b, cfg, state=None, t=None):
    """Work every open position by its ticket. Returns how many actions were taken."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    pos = {p["ticket"]: p for p in b.positions()}
    acct = b.account() or {}
    acts = 0
    for tk in [v for v in state.values() if v.get("status") == "open"]:
        p = pos.get(tk.get("position"))
        if p is None:
            continue
        sym, side, tid = tk["symbol"], tk["side"], tk["id"]
        spec, tick = b.spec(sym), b.tick(sym)
        if not spec or not tick:
            continue
        px = tick["bid"] if side == "buy" else tick["ask"]  # the price the position closes at
        up = (lambda a, lvl: a >= lvl) if side == "buy" else (lambda a, lvl: a <= lvl)
        fill = float(tk.get("fill") or p["price_open"])

        # closes first: the owner's or an agent's request, the time stop, a closing mark (a halt)
        stop_at = _t(tk.get("time_stop"))
        why = tk.get("close_request") or tk.get("closing") or ("time stop" if stop_at and t >= stop_at else None)
        if why:
            r = b.close_position(p["ticket"])
            if r.get("ok"):
                if not tk.get("closing"):
                    tickets.update(tid, closing=why)
                acts += 1
            else:
                journal.log("close_fail", id=tid, why=why, comment=r.get("comment"))
            continue

        # partial targets: every target but the last, which is the broker TP
        targets = tk.get("targets") or []
        done = int(tk.get("targets_done") or 0)
        init_vol = float(tk.get("initial_volume") or p["volume"])
        while done < len(targets) - 1 and up(px, float(targets[done][0])):
            vol = risk_gate.round_step(init_vol * float(targets[done][1]), spec["vol_step"])
            left = p["volume"] - vol
            note = None
            if vol >= spec["vol_min"] - 1e-12 and left >= spec["vol_min"] - 1e-12:
                r = b.close_position(p["ticket"], vol)
                if r.get("ok"):
                    p["volume"] = round(left, 8)
                    acts += 1
                else:
                    note = f"partial close failed: {r.get('comment')}"
            else:
                note = "share below the minimum lot; kept"
            done += 1
            tickets.update(tid, targets_done=done, volume=p["volume"], note=note)
            journal.log("partial", id=tid, target=targets[done - 1][0], volume=vol, note=note)

        # breakeven, then the trail; an agent's tighter stop
        be = tk.get("breakeven_at")
        if be and up(px, float(be)) and _better(side, fill, p.get("sl")):
            if _move_stop(b, tk, p, spec, tick, fill, "breakeven"):
                acts += 1
        tr = tk.get("trail")
        if isinstance(tr, dict) and (not tr.get("after") or up(px, float(tr["after"]))):
            dist = tr.get("dist")
            if tr.get("atr"):
                a = atr(b, sym, tr.get("tf", "H1"), int(tr.get("n", 14)))
                dist = a * float(tr["atr"]) if a else None
            if dist:
                sl = px - float(dist) if side == "buy" else px + float(dist)
                if _move_stop(b, tk, p, spec, tick, sl, "trail"):
                    acts += 1
        ms = tk.get("move_stop")
        if ms and _better(side, float(ms), p.get("sl")):
            if _move_stop(b, tk, p, spec, tick, float(ms), "requested"):
                acts += 1

        # what the position can still lose, for the gate's caps
        loss = _loss_to_stop(side, fill, p.get("sl"), p["volume"], spec)
        base = min(acct.get("balance", 0), acct.get("equity", 0)) or None
        if loss is not None and base:
            rn = round(loss / base * 100, 4)
            if abs(rn - float(tk.get("risk_now") or 0)) > 1e-4 or p.get("sl") != tk.get("sl"):
                tickets.update(tid, risk_now=rn, sl=p.get("sl"), volume=p["volume"])
    return acts


# ---- execute -----------------------------------------------------------------------------------------------------

def _approved_at(tk):
    for h in reversed(tk.get("history", [])):
        if h["event"] in ("approve", "new"):
            return _t(h["t"])
    return _t(tk.get("created"))


def execute(b, cfg, prof, ph, state=None, t=None):
    """Send every approved ticket the gate passes. Returns the number of orders placed."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    sent = 0
    for tk in sorted((v for v in state.values() if v.get("status") == "approved"), key=lambda v: v.get("updated", "")):
        tid = tk["id"]
        kind = (tk.get("entry") or {}).get("type", "market")
        exp = _t(tk.get("expires"))
        if exp is None:
            base = _approved_at(tk) or t
            exp = base + (MARKET_TTL if kind == "market" else PENDING_TTL)
        if t >= exp:
            tickets.expire(tid, "approved but not placed before it expired")
            continue
        g = risk_gate.check(tk, b, cfg, prof, ph, state, t)
        if not g["ok"]:
            if any(x in g["why"] for x in TRANSIENT):
                if tk.get("waiting") != g["why"]:
                    tickets.update(tid, waiting=g["why"])
                continue
            tickets.block(tid, g["why"])
            state[tid] = dict(tk, status="blocked")
            continue
        acct = b.account()
        risk_money = round(g["risk_used"] / 100 * min(acct["balance"], acct["equity"]), 2)
        req = dict(symbol=g["symbol"], side=g["side"], volume=g["volume"], kind=g["kind"],
                   price=g["price"] if g["kind"] != "market" else None, sl=g["sl"], tp=g["tp"], magic=g["magic"],
                   comment=tid, expire=exp if g["kind"] != "market" else None)
        r = b.send(**req)
        if not r.get("ok") and r.get("retcode") == 10022 and req["expire"] is not None:  # broker refuses expiry
            req["expire"] = None
            r = b.send(**req)
        if not r.get("ok"):
            tickets.block(tid, f"broker refused: {r.get('retcode')} {r.get('comment')}")
            state[tid] = dict(tk, status="blocked")
            continue
        tickets.placed(tid, order=r.get("order"), symbol=g["symbol"], volume=g["volume"], kind=g["kind"],
                       price_sent=g["price"], sl=g["sl"], tp=g["tp"], magic=g["magic"], risk_used=g["risk_used"],
                       risk_now=g["risk_used"], risk_money=risk_money, gate=g["why"],
                       expires_at=exp.isoformat(timespec="seconds"))
        state = tickets.fold()
        sent += 1
    return sent


# ---- the pass ----------------------------------------------------------------------------------------------------

def run(b, cfg=None, t=None):
    """One executor pass. Returns a summary dict for the heartbeat."""
    cfg = cfg or paths.config()
    t = t or clocks.now()
    name, prof = risk_gate.profile()
    acct = b.account()
    if not acct:
        return {"ok": False, "why": "no account"}
    phase.start(acct["kind"])
    ph = phase.current(acct["kind"])
    lim = risk_gate.update_limits(acct, prof, t)
    state = reconcile(b, cfg, None, t)

    level = (lim.get("halt") or {}).get("level")
    if paths.KILL.exists() and level != "kill":
        level = "kill"
    if level == "kill" and not paths.KILL.exists():
        risk_gate.kill(lim["halt"]["why"], by="risk-gate")
    halt = risk_gate.halted()
    if halt:
        flatten(b, cfg, halt, state, t)
    elif risk_gate.weekend_cutoff(prof, t):
        live = [v for v in state.values() if v.get("status") in ("placed", "open")]
        if live:
            flatten(b, cfg, "flat before the weekend (prop profile)", state, t)
    state = tickets.fold()
    acts = manage(b, cfg, state, t)
    sent = 0 if halt else execute(b, cfg, prof, ph, tickets.fold(), t)
    state = reconcile(b, cfg, None, t)
    counts = {}
    for v in state.values():
        counts[v.get("status")] = counts.get(v.get("status"), 0) + 1
    return {"ok": True, "profile": name, "phase": ph, "halt": halt, "equity": acct["equity"],
            "balance": acct["balance"], "managed": acts, "sent": sent, "tickets": counts,
            "floors": lim.get("floors")}
