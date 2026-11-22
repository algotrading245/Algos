"""2024.10, the largest tester-against-model miss in j10b (5x), j11b (3x) and j15 (4x): where does the tester's size
leave the model's?

For each of the three single-month tester runs on 2024.10 (t3b, t4b, t5b; preset settings, 23 weekdays, cap 50,
InpGoalDayVolPct 1.56) this prints, day by day:

  - the model (research/hydra_t5b_months_model.py, preset settings, edge 1.0): size-1 return, the size GoalSize()
    would ask for at the model's own equity, and the model's equity;
  - the tester: the day's closing balance from result.json, the size GoalSize() would ask for at that balance, and
    the day's net by symbol from the report's deals, in % of the day's opening balance.

The deals from 2024.10.03 on are printed in full, comment column included, to see how the month ended (stop out or
the EA).

    python research/hydra_goal_202410_compare.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import norm

import hydra_t5b_months_model as m
from hydra_j6_compare import deals_of, parse_report, pl

ROOT = Path(__file__).resolve().parent.parent
RUNS = {
    3.0: "backtests/2026-10-18_0630_AurumHydra_t3b_202410",
    4.0: "backtests/2026-10-18_0839_AurumHydra_t4b_202410",
    5.0: "backtests/2026-10-18_0428_AurumHydra_t5b_202410",
}
DAYS, CAP, VOL = 23, 50.0, 0.0156


def size_at(eq, goal, left):
    x = min(max(eq / goal, 1e-6), 1 - 1e-6)
    return min(CAP, m.SCALE * norm.pdf(norm.ppf(x)) / (x * np.sqrt(left)) / VOL)


def main():
    r = m.daily().loc["2024-10"]
    legs = m.pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    cand = m.pd.read_csv(ROOT / "marketdata" / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True)
    print("size-1 daily return by leg, 2024.10 (model file), %")
    both = legs.loc["2024-10"].join(cand.loc["2024-10"][["breakout", "noise"]].assign(noise=lambda d: 0.55 * d.noise))
    print((100 * both).round(2).to_string())
    for goal, folder in RUNS.items():
        res = json.loads((ROOT / folder / "result.json").read_text())
        dep = res["deposit"]
        curve = {d: float(v) for d, v in res["curve"]}
        deals = deals_of(folder)
        net = defaultdict(lambda: defaultdict(float))
        for d in deals:
            if d["symbol"]:
                net[d["time"][:10].replace(".", "-")][d["symbol"]] += pl(d)
        print(f"\n=== goal {goal:.0f}x, {folder}: end {res['curve'][-1][1]:,.0f} ({res['curve'][-1][1] / dep:.2f}x), "
              f"eq DD {res['eq_dd_max_pct']}%")
        print("day         size1%   model size  model eq | tester bal  tester eq/dep  size at bal | net by symbol, "
              "% of day open")
        eq, teq = 1.0, dep
        for i, (day, ret) in enumerate(r.items()):
            left = DAYS - i
            ds = day.strftime("%Y-%m-%d")
            msize = size_at(eq, goal, left) if 0.2 < eq < goal else 0.0
            eq = eq * max(0.0, 1 + msize * ret) if msize else eq
            tsize = size_at(teq / dep, goal, left)
            bal = curve.get(ds)
            sym = " ".join(f"{s} {100 * v / teq:+.1f}" for s, v in sorted(net.get(ds, {}).items(), key=lambda kv: kv[1]))
            print(f"{ds}  {100 * ret:+6.2f}   {msize:8.1f}   {eq:6.2f}x | "
                  f"{'' if bal is None else f'{bal:10,.0f}'}{'' if bal else ' ' * 10}  "
                  f"{'' if bal is None else f'{bal / dep:6.2f}x'}{'' if bal else ' ' * 7}     {tsize:6.1f}   | {sym}")
            if bal is not None:
                teq = bal
        print("deals from 2024.10.03 (time, symbol, type, direction, volume, price, profit, balance, comment):")
        for row in deal_rows(folder):
            if row[0] >= "2024.10.03":
                print("  " + "  ".join(row[i] for i in (0, 2, 3, 4, 5, 6, 10, 11, 12)))


def deal_rows(folder):
    # hydra_j6_compare.deals_of without the column cut: the comment column carries the tester's "so:" stop-out mark
    report = max((ROOT / folder).glob("*.htm"), key=lambda p: p.stat().st_size)
    text = parse_report.read(report)
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text[text.find(">Deals<"):], re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) == 13 and re.match(r"\d{4}\.\d\d\.\d\d", cells[0]):
            rows.append(cells)
    return rows


if __name__ == "__main__":
    main()
