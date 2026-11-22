"""How many of AurumHydra's 63 single-month tester runs (t3b, t4b, t5b on 2024.01-2025.09) ended in a broker stop out?

research/hydra_goal_202410_compare.py found that 2024.10, the largest tester-against-model miss at every goal, is a
stop out: at 05:35 on 2024.10.08 the margin level fell below 50% ("so 49.6%" in the deal comment), the tester closed
the AUDCAD grid and the gold hold at the low, and the test ended ("end of test"). The model has no margin, so it rides
the same day out (size-1 day -0.04%) and reaches the goal.

This scans every single-month run's deals for the "so " mark and prints, per goal and month: the tester multiple,
the model multiple (research/hydra_t5b_months_model.py, preset settings, edge 1.0), the stop-out time and margin
level, and the stop-out loss by symbol in % of the balance before it.

    python research/hydra_stopout_scan.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import hydra_t5b_months_model as m
from hydra_goal_202410_compare import deal_rows
from hydra_j6_compare import parse_report

ROOT = Path(__file__).resolve().parent.parent
TOL = 0.997


def num(s):
    return parse_report.num(s) or 0.0


def main():
    r = m.daily()
    tot = defaultdict(lambda: defaultdict(int))
    for goal in (3, 4, 5):
        m.GOAL = float(goal)
        print(f"\n=== goal {goal}x")
        print("month    tester   model  | stop out            margin  loss at stop out, % of balance before")
        for res_path in sorted(ROOT.glob(f"backtests/2026-10-18_*_AurumHydra_t{goal}b_20????/result.json")):
            folder = res_path.parent
            month = folder.name[-6:]
            res = json.loads(res_path.read_text())
            dep = res["deposit"]
            mult = res["curve"][-1][1] / dep if res["curve"] else 1.0
            p = r.loc[f"{month[:4]}-{month[4:]}"].to_numpy()
            model = m.one_round(p, 23, 50.0, 0.0156)
            rows = deal_rows(folder.relative_to(ROOT))
            so = [x for x in rows if x[12].startswith("so ")]
            line = f"{month}   {mult:5.2f}x  {model:5.2f}x  | "
            if so:
                t = so[0][0]
                hit = [x for x in rows if x[0] == t and x[4] == "out"]
                first = rows.index(hit[0])
                before = num(rows[first - 1][11]) if first else dep
                loss = defaultdict(float)
                for x in hit:
                    loss[x[2]] += num(x[10]) + num(x[8]) + num(x[9])
                level = re.search(r"so ([\d.]+)%", so[0][12]).group(1)
                line += f"{t}  {level:>6s}%  " + " ".join(f"{s} {100 * v / before:+.1f}" for s, v in
                                                          sorted(loss.items(), key=lambda kv: kv[1]))
            print(line)
            k = tot[goal]
            k["months"] += 1
            k["so"] += bool(so)
            k["reach"] += mult >= goal * TOL
            k["model_reach"] += model >= goal * TOL
            k["so_model_reach"] += bool(so) and model >= goal * TOL
            k["so_reach"] += bool(so) and mult >= goal * TOL
            k.setdefault("so_mults", [])
            if so:
                k["so_mults"].append(mult)
    print("\ngoal  months  stop outs  tester reach  model reach  stop-out months the model reached  "
          "tester multiple after a stop out")
    for goal, k in tot.items():
        sm = k["so_mults"]
        print(f"{goal}x    {k['months']:4d}    {k['so']:6d}      {k['reach']:6d}       {k['model_reach']:6d}          "
              f"{k['so_model_reach']:6d}                         "
              f"{'' if not sm else f'median {np.median(sm):.2f}x, range {min(sm):.2f}-{max(sm):.2f}x'}")


if __name__ == "__main__":
    main()
