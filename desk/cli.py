"""The one door into the desk, for the agents and for the owner. Agents run it through Bash; every command prints JSON.

The runner sets AURUM_DESK_ROLE for an agent (a pod name, head-trader, debrief, monitor, scorekeeper). A pod may
propose, cancel and close only its own tickets and set only its own triggers; only the head trader (or the owner, who
runs with no role) approves; only the owner resumes after a kill. Orders are never sent here: the clock does that.

python -m desk.cli status
python -m desk.cli view account|positions|tickets [--all]|quote SYM [SYM ...]|bars SYM [SYM ...] TF [N]
                        |calendar [HOURS]|triggers [POD]|journal [KIND] [DAYS]|limits|config
python -m desk.cli ticket new '<json>' | @file.json
python -m desk.cli ticket approve|reject ID "why"
python -m desk.cli ticket cancel|close ID "why"
python -m desk.cli ticket stop ID PRICE "why"           tighter stop only (the executor ignores a looser one)
python -m desk.cli trigger add POD KIND "why" key=value ...   (above/below: instrument level; time: at; event: ccy;
                                                               ticket: ticket on=open|closed; spread: instrument mult)
python -m desk.cli trigger remove ID
python -m desk.cli kill "why"                            close everything now; the desk stays stopped
python -m desk.cli resume                                owner only
python -m desk.cli alert ack "why"                       owner only: archives inbox/ALERT.md once dealt with
"""
import datetime as dt
import json
import os
import sys

from desk import clocks, journal, jobs, news, paths, phase, risk_gate, tickets, triggers

HEAD = "head-trader"


class Refused(Exception):
    pass


def role():
    # an agent (AURUM_AGENT is set by the runner and the autopilot) that blanks its role is still not the owner
    return os.environ.get("AURUM_DESK_ROLE") or ("agent" if os.environ.get("AURUM_AGENT") else "")


def _pod_role(cfg):
    r = role()
    return r if r in cfg.get("pods", {}) else None


def _owner():
    return role() == ""


def _out(obj):
    print(json.dumps(obj, indent=1, default=str))


def _ticket_brief(v):
    keep = ("id", "status", "pod", "instrument", "side", "entry", "stop", "targets", "risk_pct", "confidence", "edge",
            "position", "fill", "volume", "sl", "tp", "risk_now", "why", "waiting", "closing", "close_request",
            "created", "updated", "time_stop", "pnl", "R", "reason")
    return {k: v[k] for k in keep if k in v}


# ---- status and views ------------------------------------------------------------------------------------------------

def status():
    cfg = paths.config()
    hb = paths.read_json(paths.STATE / "heartbeat.json", {})
    name, prof = risk_gate.profile()
    ph = phase.current()
    state = tickets.fold()
    live = [_ticket_brief(v) for v in tickets.live(state).values()]
    return {"now": clocks.now().isoformat(timespec="seconds"), "phase": ph, "phase_day": phase.days_in(),
            "pods_active": phase.pods_active(cfg, ph), "profile": name, "risk_scale": phase.risk_scale(prof, ph),
            "halt": risk_gate.halted(), "heartbeat": {k: hb.get(k) for k in ("t", "ok", "broker", "why")},
            "account": {k: (hb.get("summary") or {}).get(k) for k in ("equity", "balance", "floors")},
            "live_tickets": live, "jobs_pending": [{"id": j["id"], "kind": j["kind"], "pod": j.get("pod")}
                                                   for j in jobs.pending()]}


def _broker():
    from desk import broker
    b = broker.connect(paths.config())
    if not b.connected():
        raise Refused(f"desk terminal not connected: {getattr(b, 'why', '')}")
    return b


TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1")


def _bars(b, sym, tf, n):
    from desk import broker as bk
    real = b.resolve(sym)
    if not real:
        raise Refused(f"{sym} not offered by this broker")
    df = b.bars(real, tf, int(n))
    if df is None:
        return []
    rows = []
    for r in df.itertuples():
        rows.append({"t": bk.server_epoch_to_utc(int(r.time)).isoformat(timespec="minutes"), "o": r.open,
                     "h": r.high, "l": r.low, "c": r.close, "spread": int(r.spread)})
    return rows


def _quote(b, sym):
    real = b.resolve(sym)
    if not real:
        raise Refused(f"{sym} not offered by this broker")
    tk, spec = b.tick(real), b.spec(real)
    return {"symbol": real, "bid": tk and tk["bid"], "ask": tk and tk["ask"],
            "time": tk and tk["time"].isoformat(timespec="seconds"), "digits": spec and spec["digits"],
            "spread_pts": spec and spec["spread_pts"]}


def _each(syms, fn):
    """One market gives its answer; several give {SYM: answer}, a refused one {SYM: {"refused": why}} (owner
    2026-10-27: a pod asked for three markets in one call and the shell loop it wrote was refused)."""
    if len(syms) == 1:
        return fn(syms[0])
    out = {}
    for s in syms:
        try:
            out[s] = fn(s)
        except Refused as e:
            out[s] = {"refused": str(e)}
    return out


def view(args):
    what = args[0] if args else "account"
    cfg = paths.config()
    if what == "tickets":
        state = tickets.fold()
        if "--all" in args:
            since = (clocks.now() - dt.timedelta(days=7)).isoformat()
            rows = [v for v in state.values() if v.get("updated", "") >= since]
        else:
            rows = list(tickets.live(state).values())
        pod = _pod_role(cfg)
        return [_ticket_brief(v) for v in rows if pod is None or v.get("pod") == pod or "--all" in args]
    if what == "triggers":
        return triggers.active(args[1] if len(args) > 1 else None)
    if what == "calendar":
        hours = float(args[1]) if len(args) > 1 else 24
        return [{k: v for k, v in e.items() if k != "time"} for e in news.upcoming(hours)]
    if what == "journal":
        kind = args[1] if len(args) > 1 and args[1] != "all" else None
        days = int(args[2]) if len(args) > 2 else 1
        return journal.recent([kind] if kind else None, days)[-200:]
    if what == "limits":
        return risk_gate.limits()
    if what == "config":
        name, prof = risk_gate.profile()
        return {"profile": name, "risk": prof, "pods": cfg["pods"], "instruments": sorted(cfg["instruments"])}
    if what == "bars":
        at = next((i for i, a in enumerate(args) if i > 1 and a.upper() in TIMEFRAMES), None)
        if at is None:
            raise Refused("view bars SYM [SYM ...] TF [N]")
        syms, tf = args[1:at], args[at].upper()
        n = min(int(args[at + 1]) if len(args) > at + 1 else 100, 1000)
    elif what == "quote":
        syms = args[1:]
        if not syms:
            raise Refused("view quote SYM [SYM ...]")
    b = _broker()
    try:
        if what == "account":
            return b.account()
        if what == "positions":
            pos = b.positions()
            if pos is None:
                raise Refused("the terminal did not return positions; try again")
            return pos
        if what == "quote":
            return _each(syms, lambda s: _quote(b, s))
        if what == "bars":
            return _each(syms, lambda s: _bars(b, s, tf, n))
    finally:
        b.shutdown()
    raise Refused(f"unknown view {what}")


# ---- tickets ---------------------------------------------------------------------------------------------------------

def _load_json(s):
    if s.startswith("@"):
        with open(s[1:], encoding="utf-8") as f:
            return json.load(f)
    return json.loads(s)


def _own(tk, cfg):
    pod = _pod_role(cfg)
    if _owner() or role() == HEAD:
        return
    if pod is None or tk.get("pod") != pod:
        raise Refused(f"ticket {tk['id']} belongs to {tk.get('pod')}; role {role() or 'owner'} may not change it")


def ticket(args):
    if not args:
        raise Refused("ticket new|approve|reject|cancel|close|stop")
    cfg = paths.config()
    op = args[0]
    if op == "new":
        t = _load_json(args[1])
        pod = _pod_role(cfg)
        if pod:
            t.setdefault("pod", pod)
            if t["pod"] != pod:
                raise Refused(f"a {pod} agent may only propose {pod} tickets")
        if role() not in ("",) and not pod and t.get("arm"):
            raise Refused("only a pod's edge or the owner arms a ticket")
        if pod and pod not in phase.pods_active(cfg):
            raise Refused(f"{pod} is not active in phase {phase.current()}")
        tid, errs = tickets.new(**t)
        return {"ok": tid is not None, "id": tid, "errors": errs}
    if len(args) < 2:
        raise Refused(f"ticket {op} ID ...")
    state = tickets.fold()
    tk = state.get(args[1])
    if tk is None:
        raise Refused(f"no ticket {args[1]}")
    why = args[-1] if len(args) > 2 else ""
    st = tk.get("status")
    if op in ("approve", "reject"):
        if not (_owner() or role() == HEAD):
            raise Refused("only the head trader or the owner approves or rejects")
        if st != "proposed":
            raise Refused(f"ticket {tk['id']} is {st}, not proposed")
        if not why:
            raise Refused("give a reason")
        r = (tickets.approve if op == "approve" else tickets.reject)(tk["id"], why, by=role() or "owner")
        return {"ok": True, "id": tk["id"], "status": r["status"]}
    _own(tk, cfg)
    if op == "cancel":
        if st not in ("proposed", "approved", "placed"):
            raise Refused(f"ticket {tk['id']} is {st}; close an open ticket instead")
        tickets.cancel(tk["id"], why or "cancelled", by=role() or "owner")
        return {"ok": True, "id": tk["id"], "status": "cancelled"}
    if op == "close":
        if st != "open":
            raise Refused(f"ticket {tk['id']} is {st}, not open")
        tickets.update(tk["id"], close_request=why or "closed by " + (role() or "owner"))
        return {"ok": True, "id": tk["id"], "note": "the clock closes it on its next pass"}
    if op == "stop":
        if st != "open" or len(args) < 3:
            raise Refused("ticket stop ID PRICE \"why\" on an open ticket")
        px = float(args[2])
        cur = tk.get("sl") or tk.get("stop")
        if cur and (tk["side"] == "buy" and px <= float(cur) or tk["side"] == "sell" and px >= float(cur)):
            raise Refused(f"the stop only tightens: {px} is not better than {cur}")
        tickets.update(tk["id"], move_stop=px, why=why if len(args) > 3 else "")
        return {"ok": True, "id": tk["id"], "move_stop": px}
    raise Refused(f"unknown ticket command {op}")


# ---- triggers, kill, resume ------------------------------------------------------------------------------------------

def _kv(items):
    out = {}
    for it in items:
        k, _, v = it.partition("=")
        try:
            v = float(v) if k in ("level", "mult") else int(v) if k in ("minutes",) else v
        except ValueError:
            pass
        out[k] = v
    return out


def trigger(args):
    cfg = paths.config()
    if args and args[0] == "add":
        if len(args) < 4:
            raise Refused("trigger add POD KIND \"why\" key=value ...")
        pod, kind, why = args[1], args[2], args[3]
        mine = _pod_role(cfg)
        if mine and pod != mine:
            raise Refused(f"a {mine} agent sets only {mine} triggers")
        gid, errs = triggers.add(pod, kind, why, cfg, **_kv(args[4:]))
        return {"ok": gid is not None, "id": gid, "errors": errs}
    if args and args[0] == "remove" and len(args) > 1:
        return {"ok": triggers.remove(args[1], _pod_role(cfg))}
    raise Refused("trigger add|remove")


def kill(args):
    why = " ".join(args) or "kill switch"
    risk_gate.kill(why, by=role() or "owner")
    return {"ok": True, "halt": risk_gate.halted(), "note": "the clock closes every desk position on its next pass"}


def resume(_args):
    if not _owner():
        raise Refused("only the owner resumes the desk")
    risk_gate.resume("owner")
    return {"ok": True, "halt": risk_gate.halted()}


def alert(args):
    """alert ack "why": the owner has dealt with inbox/ALERT.md. The file moves to logs/desk/state/alerts/ with the
    why on top, and the ack is journaled, so the dashboard stops showing old alerts (owner 2026-10-27)."""
    if not args or args[0] != "ack" or not " ".join(args[1:]).strip():
        raise Refused('alert ack "why": say what was done about it')
    if not _owner():
        raise Refused("only the owner acknowledges alerts")
    why = " ".join(args[1:]).strip()
    f = paths.INBOX / "ALERT.md"
    if not f.exists():
        return {"ok": True, "archived": None, "note": "no open alert"}
    t = clocks.now()
    text = f.read_text(encoding="utf-8")
    dest = paths.STATE / "alerts" / f"ALERT_{t:%Y-%m-%d_%H%M%S}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"Acknowledged {t.isoformat(timespec='seconds')} by the owner: {why}\n\n{text}", encoding="utf-8")
    f.unlink()
    titles = [ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")]
    journal.log("alert_ack", why=why, alerts=titles, archived=str(dest))
    return {"ok": True, "acknowledged": titles, "archived": str(dest)}


COMMANDS = {"status": lambda a: status(), "view": view, "ticket": ticket, "trigger": trigger, "kill": kill,
            "resume": resume, "alert": alert}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        extras = sys.modules.get("desk.extras")
        print(__doc__ + (extras.__doc__ if extras else ""))
        return 2
    try:
        _out(COMMANDS[argv[0]](argv[1:]))
        return 0
    except Refused as e:
        _out({"ok": False, "refused": str(e)})
        return 1


def register(name, fn):
    """Later modules (board, memory, playbooks) add their commands here."""
    COMMANDS[name] = fn


if __name__ == "__main__":
    # run through desk.cli, not this __main__ copy, so the commands extras registers are the ones main sees
    from desk import cli as _cli
    try:
        from desk import extras  # noqa: F401  the Phase 1-2 commands register themselves
    except ImportError as e:
        if getattr(e, "name", "") != "desk.extras":
            raise
    sys.exit(_cli.main())
