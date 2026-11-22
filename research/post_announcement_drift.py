"""Does the first reaction to US payrolls (08:30 New York) and FOMC decisions (14:00) keep going?

For each event and instrument: the reaction r0 is the move from the minute before the release to k minutes after
(k = 5, 15).  The trade enters at release + k in the direction of r0 and exits H minutes later (30, 60, 120, 240),
never past 16:55 New York.  A second version trades only when |r0| is above its median over the previous 24
events of that kind.  Costs per round trip: currencies 1.5 bp (wider spreads after a release), gold 2.5 bp, the S&P
500 CFD 1.5 bp.  Bid minute bars from histdata.com on the New York clock; event dates from
research/pre_announcement_drift.py (payrolls) and research/pre_fomc_drift.py (FOMC), November 2010 on.

    python research/post_announcement_drift.py

Paper read in full for the prior: Andersen, Bollerslev, Diebold, Vega, "Micro Effects of Macro Announcements:
Real-Time Price Discovery in Foreign Exchange", American Economic Review 93(1), 2003 - the dollar jumps on the news
within five to ten minutes "and little movement thereafter".

Result (2010-11 to 2026-10, 190 payrolls, 127 FOMC days), nothing added to any EA:
  No drift.  Following the first 5 or 15 minutes for 30 minutes to 4 hours loses after cost in nearly every cell
  for the six dollar pairs, gold and the S&P 500, both halves; trading only big first moves does not change that.
  If anything the first move partly reverses: the S&P 500 after payrolls gives back about 11 bp of the 08:30-08:35
  move over 2-4 hours (t -1.5 to 2017, -2.2 from 2018), about 9 bp an event after cost, 12 events a year, Sharpe
  near 0.5 - one cell of 128, not counted as an edge.  Gold after FOMC days with a big first move drifts 8-15 bp
  (t about 1 in each half, six events a year), too thin.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overnight_intraday_reversal import NY, matrix
from pre_announcement_drift import NFP
from pre_fomc_drift import FOMC, dates

SPLIT = pd.Timestamp("2018-01-01")
SYMBOLS = {"EURUSD": 1.5, "GBPUSD": 1.5, "USDJPY": 1.5, "AUDUSD": 1.5, "USDCAD": 1.5, "USDCHF": 1.5,
           "XAUUSD": 2.5, "SPXUSD": 1.5}
EVENTS = {"NFP": (NFP, 8 * 60 + 30), "FOMC": (FOMC, 14 * 60)}
LAST = 16 * 60 + 55


def tstat(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else 0.0


def table(symbol, event):
    days, p = matrix(symbol, NY)
    p = p.astype(float)
    table_, minute = EVENTS[event]
    when = dates(table_)
    rows = []
    for d in when:
        i = days.get_indexer([d])[0]
        if i < 0:
            continue
        row = pd.Series(p[i]).ffill().to_numpy()
        before = row[minute - 1]
        if not before > 0:
            continue
        for k in (5, 15):
            e = row[minute + k]
            r0 = e / before - 1
            for h in (30, 60, 120, 240):
                x = min(minute + k + h, LAST)
                rows.append({"day": d, "k": k, "h": h, "r0": r0, "fwd": row[x] / e - 1})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    for event in EVENTS:
        print(f"=== {event}: mean bp per trade after cost, t to 2017 | from 2018 (all events; big first moves only)")
        for s, cost in SYMBOLS.items():
            if not (Path(__file__).resolve().parent.parent / "marketdata" / "histdata" / f"{s}_M1.csv.gz").exists():
                continue
            t = table(s, event)
            out = []
            for (k, h), g in t.groupby(["k", "h"]):
                g = g.sort_values("day").reset_index(drop=True)
                r = np.sign(g.r0) * g.fwd - cost * 1e-4
                big = g.r0.abs() > g.r0.abs().rolling(24, min_periods=12).median().shift(1)
                a, b = g.day < SPLIT, g.day >= SPLIT
                out.append(f"k{k:2d} h{h:3d}: {1e4 * r.mean():+5.1f} ({tstat(r[a]):+.1f}|{tstat(r[b]):+.1f}; "
                           f"big {1e4 * r[big].mean():+5.1f} {tstat(r[a & big]):+.1f}|{tstat(r[b & big]):+.1f})")
            print(f"  {s}  n={t.day.nunique()}")
            for o in out:
                print("     ", o)
