"""The hourly code check (DESIGN.md section 10). Facts only: is the terminal up, does every desk position have a
ticket and a server-side stop, are the limits near, did anything error. A new problem writes desk/inbox/ALERT.md and
queues the Haiku monitor agent to look into it; the same problems an hour later do not queue it again.

python -m desk.monitor        run the check now and print what it finds
"""
import datetime as dt

from desk import clocks, executor, journal, news, paths, phase, risk_gate, tickets

FILE = paths.STATE / "monitor.json"
ALERT = paths.INBOX / "ALERT.md"


def check(b, cfg, summary=None, t=None):
    """A list of {"level": alert|warn, "what": ...}."""
    t = t or clocks.now()
    out = []

    def add(level, what):
        out.append({"level": level, "what": what})

    seen_demo = bool(phase.state().get("day0"))
    acct = b.account() if b.connected() else None
    if acct is None:
        if seen_demo:
            add("alert", f"desk terminal not connected: {getattr(b, 'why', '') or 'no account'}")
        return out
    if not acct.get("trade_allowed") or not acct.get("terminal_algo", True):
        add("alert", "Algo Trading is off on the desk terminal (or the account forbids trading)")
    if acct.get("kind") == "live" and not risk_gate.profile()[1].get("allow_live"):
        add("alert", "the desk terminal is on a LIVE account but risk.json does not allow live trading")

    state = tickets.fold()
    open_tk = {v.get("position"): v for v in state.values() if v.get("status") == "open"}
    pos = b.positions()
    if pos is None:
        add("alert", "the desk terminal did not return its positions")
    for p in pos or []:
        if not executor.desk_magic(p.get("magic"), cfg):
            continue
        if not p.get("sl"):
            add("alert", f"position {p['ticket']} {p['symbol']} has no server-side stop")
        if p["ticket"] not in open_tk:
            add("warn", f"desk position {p['ticket']} {p['symbol']} has no open ticket")
    pos_ids = {p["ticket"] for p in pos or []}
    for pid, tk in open_tk.items():
        upd = dt.datetime.fromisoformat(tk["updated"])
        if pos is not None and pid not in pos_ids and t - upd > executor.SETTLE_WAIT + dt.timedelta(minutes=5):
            add("warn", f"ticket {tk['id']} is open but its position {pid} is gone and not settled")
    cal = news.stale(t)
    if cal:
        add("alert", f"{cal}: every new entry is blocked until the calendar fetch works")

    halt = risk_gate.halted()
    if halt:
        add("alert", f"trading halted: {halt}")
    lim = risk_gate.limits()
    fl, eq = lim.get("floors") or {}, acct.get("equity")
    start = max(lim.get("day_balance", 0), lim.get("day_equity", 0))
    if fl.get("day") is not None and start > fl["day"]:
        used = (start - eq) / (start - fl["day"])
        if used >= 0.7:
            add("warn", f"{used:.0%} of today's loss room used (equity {eq:.2f}, day floor {fl['day']:.2f})")
    if fl.get("kill") is not None and lim.get("peak", 0) > fl["kill"]:
        used = (lim["peak"] - eq) / (lim["peak"] - fl["kill"])
        if used >= 0.7:
            add("warn", f"{used:.0%} of the drawdown room used (equity {eq:.2f}, kill floor {fl['kill']:.2f})")

    if summary and not summary.get("ok") and summary.get("why") not in (None, "no account"):
        add("warn", f"last executor pass failed: {summary.get('why')}")
    errs = [r for r in journal.recent(None, 1) if str(r.get("kind", "")).endswith("_error")
            and dt.datetime.fromisoformat(r["t"]) >= t - dt.timedelta(hours=1)]
    if errs:
        kinds = sorted({r["kind"] for r in errs})
        add("warn", f"{len(errs)} errors in the last hour ({', '.join(kinds)})")
    return out


def run(b, cfg, summary=None, t=None):
    """Check, alert on what is new. Returns (issues, queued_agent)."""
    from desk import jobs
    t = t or clocks.now()
    issues = check(b, cfg, summary, t)
    last = paths.read_json(FILE, {})
    key = sorted(i["what"] for i in issues)
    new = [i for i in issues if i["what"] not in set(last.get("issues", []))]
    paths.write_json(FILE, {"t": t.isoformat(timespec="seconds"), "issues": key})
    journal.log("monitor", issues=len(issues), new=len(new))
    queued = False
    if new:
        write_alert(issues, t)
        if any(i["level"] == "alert" for i in new) and not jobs.has_pending("monitor"):
            jobs.queue("monitor", t, issues=[i["what"] for i in issues])
            queued = True
    return issues, queued


def write_alert(issues, t):
    paths.INBOX.mkdir(parents=True, exist_ok=True)
    lines = [f"# Desk alert {t.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    lines += [f"- **{i['level'].upper()}** {i['what']}" for i in issues]
    lines += ["", "The desk's code check wrote this. `python -m desk.cli status` shows the desk; "
              "`python -m desk.cli kill \"why\"` closes everything."]
    old = ALERT.read_text(encoding="utf-8") if ALERT.exists() else ""
    ALERT.write_text("\n".join(lines) + "\n\n" + old[:20000], encoding="utf-8")


if __name__ == "__main__":
    from desk import broker
    cfg = paths.config()
    b = broker.connect(cfg)
    for i in check(b, cfg):
        print(i["level"], i["what"])
    b.shutdown()
