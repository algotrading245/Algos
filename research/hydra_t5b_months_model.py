"""j10b step 16: the Python goal model on the same 21 calendar months the tester ran (2024.01-2025.09).

The tester (backtests/2026-10-18_0401_AurumHydra_t5b_months) gave 5x in 2 of 21 fresh-deposit months, against about
40% of rounds in tools/target_odds.py (every weekday from 2010 a round).  This runs the model's goal round once per
tester month, starting on the month's first weekday, so the two can be compared month by month:

  - "odds": target_odds' settings (21 weekdays, cap 20, day vol = whole-history std at size 1)
  - "preset": AurumHydra_target5x_FTMO.set (23 weekdays or month end, cap 50, InpGoalDayVolPct 1.56)

Both at edge 1.0 (the backtest as it is) and 0.7.  The month-end boost (InpMonthEndBoost 2.0) is not modelled: the
daily file has no fix-day flag per leg.  If the model also gives few 5x on these months, the gap is the window; if it
gives many, the gap is the tester against the model (fidelity).

    python research/hydra_t5b_months_model.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

RUN = ROOT / "backtests" / "2026-10-18_0401_AurumHydra_t5b_months" / "months_result.json"
GOAL, SCALE, RUIN = 5.0, 2.5, 0.2


def daily():
    a = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    b = pd.read_csv(ROOT / "marketdata" / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True)
    b = b.reindex(a.index).fillna(0.0)
    r = a.sum(axis=1) + b.breakout + 0.55 * b.noise
    return holdout.drop(r)


def one_round(path, days, cap, vol):
    eq = 1.0
    for d in range(min(days, len(path))):
        left = days - d
        x = min(max(eq / GOAL, 1e-6), 1 - 1e-6)
        z = norm.ppf(x)
        size = min(cap, SCALE * norm.pdf(z) / (x * np.sqrt(left)) / vol)
        eq *= max(0.0, 1.0 + size * path[d])
        if eq >= GOAL or eq <= RUIN:
            break
    return min(eq, GOAL)


def summary(m):
    m = np.asarray(m)
    return (np.mean(m >= 3 - 1e-9), np.mean(m >= 4 - 1e-9), np.mean(m >= GOAL - 1e-9), np.mean(m <= RUIN + 1e-9),
            np.median(m))


def main():
    r = daily()
    print(f"daily file {r.index.min().date()} .. {r.index.max().date()}, {len(r)} days, history std "
          f"{100 * r.std():.2f}%")
    tester = {m["month"]: m["multiple"] for m in json.loads(RUN.read_text())["months"]}
    months = sorted(tester)
    rows = []
    for edge in (1.0, 0.7):
        rr = r - (1.0 - edge) * r.mean()
        vol_hist = rr.std()
        for m in months:
            y, mo = m.split(".")
            p = rr.loc[f"{y}-{mo}"]
            if len(p) == 0:
                continue
            # preset: the round runs 23 weekdays but the tester month ends first; feed only the month's days
            rows.append(dict(edge=edge, month=m, days=len(p), tester=tester[m],
                             odds=one_round(p.to_numpy(), 21, 20.0, vol_hist),
                             preset=one_round(p.to_numpy(), 23, 50.0, 0.0156),
                             month_ret=float(p.sum()), month_vol=float(p.std())))
    df = pd.DataFrame(rows)
    for edge, g in df.groupby("edge", sort=False):
        print(f"\nedge {edge}: {len(g)} months")
        print("month    days  size-1 sum  size-1 vol   model odds  model preset   tester")
        for _, x in g.iterrows():
            print(f"{x.month}   {x.days:3d}   {100 * x.month_ret:7.2f}%    {100 * x.month_vol:6.2f}%     "
                  f"{x.odds:6.2f}x      {x.preset:6.2f}x     {x.tester:5.2f}x")
        print("                     P(3x)   P(4x)   P(5x)   P(ruin)  median")
        for col in ("odds", "preset", "tester"):
            s = summary(g[col])
            print(f"  {col:16s}  {100 * s[0]:5.1f}%  {100 * s[1]:5.1f}%  {100 * s[2]:5.1f}%  {100 * s[3]:6.1f}%   "
                  f"{s[4]:.2f}x")
        for col in ("odds", "preset"):
            lm, lt = np.log(g[col].clip(lower=0.01)), np.log(g.tester.clip(lower=0.01))
            print(f"  corr log({col}) vs log(tester) {np.corrcoef(lm, lt)[0, 1]:.2f}; "
                  f"tester keeps {lt.sum() / lm.sum() if lm.sum() != 0 else float('nan'):.2f} of model log growth "
                  f"(sum log model {lm.sum():.2f}, tester {lt.sum():.2f})")
    # the whole-history base rate of month-start rounds, for the window question
    print("\nbase rate, month-start rounds 2010 on (odds settings), against these 21 months:")
    for edge in (1.0, 0.7):
        rr = r - (1.0 - edge) * r.mean()
        vol_hist = rr.std()
        ends = [one_round(g.to_numpy(), 21, 20.0, vol_hist) for _, g in rr.groupby(rr.index.to_period("M"))
                if len(g) >= 15]
        s = summary(ends)
        print(f"  edge {edge}: {len(ends)} months, P(5x) {100 * s[2]:.1f}%, P(3x) {100 * s[0]:.1f}%, "
              f"median {s[4]:.2f}x")


if __name__ == "__main__":
    main()
