"""Lesson 21 check for the month-reversal leg: which exits the AurumFunded book has that research/graziani_reversal.py
lacks, and how often they would cut a hold. Uses the same signal/holds (variant 0, daily closes before 16:00 file clock,
holdout dropped). Per hold and index: notional multiple m = SizeMult(0.5) x InpGrzMult(0.5) x min(3, 10% / vol60), as
the EA sizes it at 10k. Reports (closes only, so intraday lows are not seen and the counts are lower bounds):
  - broker stop 5% of equity: stop distance = min(0.5, 0.05 / m) below entry; holds whose close path reaches it
  - worst single-day equity loss of the leg (m x worst daily return) against the 5% FTMO day stop share
  - worst hold-to-date equity loss (m x worst cumulative return) against the open-loss stop
Run: python research/graziani_book_exits.py
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "research")
import graziani_reversal as g

SIZE = 0.5 * 0.5
for s, c in {s: g.daily(s) for s in g.SPEC}.items():
    ret = np.log(c).diff()
    vol60 = ret.rolling(60).std() * np.sqrt(252)
    idx = c.index
    per = idx.to_period("M")
    months = per.unique()
    rows = []
    for i in range(len(months) - 1):
        a = np.where(per == months[i])[0]
        b = np.where(per == months[i + 1])[0]
        if len(a) < 15 or len(b) < 15:
            continue
        fr = [j for j in a if idx[j].dayofweek == 4]
        if len(fr) < 4:
            continue
        if not c.iloc[a[-1]] / c.iloc[fr[3]] - 1 < 0:
            continue
        e, x = a[-1], b[-1]
        m = SIZE * min(3.0, 0.10 / vol60.iloc[e])
        path = c.iloc[e + 1: x + 1] / c.iloc[e] - 1
        dstop = min(0.5, 0.05 / m)
        dret = c.iloc[e + 1: x + 1].pct_change()
        dret.iloc[0] = c.iloc[e + 1] / c.iloc[e] - 1
        rows.append((idx[e], m, dstop, path.min(), dret.min() * m, path.min() * m))
    d = pd.DataFrame(rows, columns=["entry", "m", "stop_dist", "min_path", "worst_day_eq", "worst_hold_eq"]).set_index("entry")
    print(f"== {s}: {len(d)} holds, mean m {d.m.mean():.2f}, mean stop distance {d.stop_dist.mean()*100:.1f}%")
    print(f"  holds whose closes reach the broker stop: {(d.min_path <= -d.stop_dist).sum()}")
    print(f"  worst day equity loss {d.worst_day_eq.min()*100:.2f}% ; days worse than -1% of equity: {(d.worst_day_eq < -0.01).sum()}")
    print(f"  worst hold-to-date equity loss {d.worst_hold_eq.min()*100:.2f}% ; holds worse than -2%: {(d.worst_hold_eq < -0.02).sum()}")
    w = d[(d.index >= "2024-01-01")]
    print(f"  2024.01-2025.09: {len(w)} holds, worst hold-to-date {w.worst_hold_eq.min()*100:.2f}%, worst day {w.worst_day_eq.min()*100:.2f}%")
