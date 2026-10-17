"""Summary of a month-by-month tester series (tools/run-months.ps1): each month's end multiple of its fresh deposit,
the share of months that reached the goal, the median, and the share that lost more than half.  Writes
months_result.json next to months.json.

    python tools/months_summary.py backtests/<date>_AurumHydra_5x_months

A month's multiple is the report's final balance over its deposit (1 + net / deposit), so a round that reached the
goal and then gave some back before the month's end counts at its end value; the EA's own "goal round ended" line in
each month's summary.txt gives the multiple at the moment the round ended, and is shown when present.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ROUND = re.compile(r"goal round of \S+ ended, equity [\d.]+ from [\d.]+ \(([\d.]+)x")
# Orders the broker's own margin or volume limits refused. On Terminal 16 the symbols carry FTMO's margins, not a
# 1:500 broker's, so a month with refusals is a month where the 5x sizes did not fit; with none, the account's
# 1:500 tester leverage was the only margin in play and the month stands for a 1:500 broker too.
MARGIN = re.compile(r"no money|not enough money|invalid volume|volume limit", re.I)


def main(folder):
    d = Path(folder) if Path(folder).is_absolute() else ROOT / folder
    state = json.loads((d / "months.json").read_text(encoding="utf-8-sig"))
    goal = float(state.get("Goal", 5.0))
    rows = []
    for m in state["Done"] if isinstance(state["Done"], list) else [state["Done"]]:
        f = ROOT / m["Folder"] if m.get("Folder") else None
        res = f / "result.json" if f else None
        if not res or not res.exists():
            rows.append({"month": m["Month"], "multiple": None, "round": None, "status": m.get("Status", "no report")})
            continue
        r = json.loads(res.read_text())
        mult = 1 + r["net"] / r["deposit"]
        log = f / "summary.txt"
        text = log.read_text(errors="ignore") if log.exists() else ""
        hit = ROUND.findall(text)
        rows.append({"month": m["Month"], "multiple": round(mult, 3), "round": float(hit[0]) if hit else None,
                     "trades": r.get("trades"), "eq_dd_pct": r.get("eq_dd_max_pct"),
                     "margin_refusals": len(MARGIN.findall(text)), "status": "done"})
    x = np.array([r["multiple"] for r in rows if r["multiple"] is not None])
    best = np.array([max(r["multiple"], r["round"] or 0) for r in rows if r["multiple"] is not None])
    out = {"goal": goal, "months_planned": len(state["Months"]), "months_run": int(len(x)),
           "share_goal_at_month_end": float((x >= goal).mean()) if len(x) else None,
           "share_goal_reached": float((best >= goal).mean()) if len(x) else None,
           "median_multiple": float(np.median(x)) if len(x) else None,
           "share_below_half": float((x < 0.5).mean()) if len(x) else None,
           "months_with_margin_refusals": sum(1 for r in rows if r.get("margin_refusals")), "months": rows}
    (d / "months_result.json").write_text(json.dumps(out, indent=1) + "\n")
    for r in rows:
        mult = "-" if r["multiple"] is None else f"{r['multiple']:.2f}x"
        print(f"  {r['month']}  {mult:>8}  round {r['round'] or '-'}  {r['status']}")
    if len(x):
        print(f"{len(x)} of {len(state['Months'])} months run; goal {goal}x reached in {out['share_goal_reached']:.0%} "
              f"(held to month end {out['share_goal_at_month_end']:.0%}), median {out['median_multiple']:.2f}x, "
              f"below 0.5x {out['share_below_half']:.0%}; months with margin refusals "
              f"{out['months_with_margin_refusals']}")
    print(f"wrote {d / 'months_result.json'}")


if __name__ == "__main__":
    main(sys.argv[1])
