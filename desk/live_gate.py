"""The live gate (DESIGN.md section 9): whether the desk has earned live money, judged on the demo.

All must hold, counted from the start of phase 3 (day 28):
  8 weeks; at least 100 desk trades; net profit factor 1.2 or more on money after costs; maximum drawdown 8% or less
  (the risk gate's record, which a resume does not reset); no limit breach from a code fault; and the AI pods together
  beating the shadow benchmark on R a trade.
A code fault is an orphan position or order (a fill the desk did not ask for or lost track of), a failed close, or a
closed ticket that lost more than 1.5R (its server-side stop did not hold).

The gate only reports. Going live is the owner's yes in chat and their edit of risk.json; this module never does it.
evaluate() returns the verdict; write() also saves reports/live_gate.md and journals it.
"""
import datetime as dt

from desk import clocks, journal, paths, phase, risk_gate, scorekeeper, systematic, tickets

WEEKS, MIN_TRADES, MIN_PF, MAX_DD_PCT, FAULT_R = 8, 100, 1.2, 8.0, -1.5
FAULTS = ("orphan_position", "orphan_order", "close_fail")
REPORT = paths.REPORTS / "live_gate.md"


def _phase3_start(s=None):
    return phase.phase3_start(s)


def _pf(pnls):
    wins, losses = sum(p for p in pnls if p > 0), -sum(p for p in pnls if p < 0)
    return round(wins / losses, 3) if losses else (None if not wins else float("inf"))


def evaluate(t=None, state=None):
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    p3 = _phase3_start()
    since = p3.isoformat() if p3 else None
    closed = [v for v in tickets.by_status("closed", state) if since and v.get("updated", "") >= since]
    ai = [v for v in closed if v.get("pod") != systematic.POD and not v.get("arm") and v.get("R") is not None]
    ai_r = round(sum(float(v["R"]) for v in ai) / len(ai), 3) if ai else None
    shadow = scorekeeper.shadow_r_per_trade()
    weeks = round((t - p3).days / 7, 1) if p3 and t > p3 else 0.0
    pf = _pf([float(v.get("pnl") or 0) for v in closed])
    dd = (risk_gate.limits().get("record") or {}).get("max_dd_pct")
    faults = [r for r in journal.recent(list(FAULTS), max(1, (t - p3).days + 1) if p3 else 1)
              if since and r.get("t", "") >= since]
    faults += [{"kind": "stop_failed", "id": v["id"], "R": v["R"]} for v in closed
               if v.get("R") is not None and float(v["R"]) < FAULT_R]
    checks = {
        "weeks": {"need": WEEKS, "have": weeks, "ok": weeks >= WEEKS},
        "trades": {"need": MIN_TRADES, "have": len(closed), "ok": len(closed) >= MIN_TRADES},
        "profit_factor": {"need": MIN_PF, "have": pf, "ok": pf is not None and pf >= MIN_PF},
        "max_drawdown_pct": {"need": MAX_DD_PCT, "have": dd, "ok": dd is not None and dd <= MAX_DD_PCT},
        "code_faults": {"need": 0, "have": len(faults), "ok": not faults, "list": faults[:20]},
        "ai_beats_shadow": {"need": f"> {shadow} R a trade", "have": ai_r,
                            "ok": ai_r is not None and shadow is not None and ai_r > shadow},
    }
    passed = bool(p3) and all(c["ok"] for c in checks.values())
    if passed:
        verdict = "PASS: ask the owner for their yes; live starts at half risk for a month"
    elif p3 is None:
        verdict = "not started: the desk has not traded a demo yet"
    elif t < p3:
        verdict = f"not started: phase 3 begins {p3.date()}"
    elif checks["weeks"]["ok"] and not checks["ai_beats_shadow"]["ok"]:
        verdict = ("FAIL on the AI pods: fall back to the systematic pod and the bridge (DESIGN.md section 13)"
                   if all(c["ok"] for k, c in checks.items() if k != "ai_beats_shadow") else "FAIL")
    else:
        verdict = "running" if not checks["weeks"]["ok"] else "FAIL"
    return {"t": t.isoformat(timespec="seconds"), "since": since, "passed": passed, "verdict": verdict,
            "checks": checks}


def _report(g):
    lines = [f"# Live gate, {g['t'][:10]}", "", f"**{g['verdict']}**", "",
             f"Counted from {g['since'][:10] if g['since'] else '(not started)'}.", "",
             "| check | need | have | ok |", "|---|---|---|---|"]
    for k, c in g["checks"].items():
        lines.append(f"| {k} | {c['need']} | {c['have']} | {'yes' if c['ok'] else 'no'} |")
    lines += ["", "The gate only reports. Live money needs the owner's yes and their edit of desk/risk.json."]
    return "\n".join(lines) + "\n"


def write(t=None):
    g = evaluate(t)
    paths.REPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(_report(g), encoding="utf-8")
    journal.log("live_gate", passed=g["passed"], verdict=g["verdict"])
    return g


if __name__ == "__main__":
    import json
    print(json.dumps(write(), indent=1, default=str))
