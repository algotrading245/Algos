"""Quoted gold spread by time of day and in fast minutes, from the Vantage XAUUSD.pc ticks in marketdata/ticks
(2026-09-21 to 2026-10-08, server time, gold near 4,170).

The backtests charge gold 0.17 USD/oz a round trip at the bell and 0.22 in the Asian session (spread, slippage and
commission together).  This checks the quoted part only; slippage on a fill is not in the quotes.

    python research/gold_spread_by_time.py

Result: the spread is 0.10-0.11 at every hour the legs trade (dip window 01:15-07:45, Europe, New York, the bell
at 23:00), 0.16-0.17 only at the 01:00 reopen and the 23:55-00:10 rollover, which no leg uses.  In the fastest 1% of
minutes (a range above 6 USD) the median spread stays 0.11 and the widest quote in the minute is 0.14-0.15.  So
the quoted spread is about half the cost the backtests assume; FTMO's spread and commission on gold must be
checked in its terminal (the Strategy Tester run uses them).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata" / "ticks"
WINDOWS = {"reopen 01:00-01:15": (60, 75), "dip window 01:15-07:45": (75, 465), "Europe 09:00-15:00": (540, 900),
           "New York 15:00-22:00": (900, 1320), "bell 22:45-23:15": (1365, 1395), "rollover 23:55-24:00": (1435, 1440)}

if __name__ == "__main__":
    d = pd.concat(pd.read_csv(f, usecols=["time_msc", "bid", "ask"]) for f in sorted(ROOT.glob("XAUUSD.pc_*.csv.gz")))
    d = d[(d.bid > 0) & (d.ask > 0)]
    t = pd.to_datetime(d.time_msc, unit="ms")
    d["mod"], d["s"], d["t"] = t.dt.hour * 60 + t.dt.minute, d.ask - d.bid, t.dt.floor("min")
    for name, (a, b) in WINDOWS.items():
        x = d[(d["mod"] >= a) & (d["mod"] < b)].s
        print(f"{name:24s} spread median {x.median():.3f}, 90% {x.quantile(0.9):.3f}")
    m = d.groupby("t").agg(hi=("bid", "max"), lo=("bid", "min"), s=("s", "median"), widest=("s", "max"),
                           mod=("mod", "first"))
    m = m[(m["mod"] >= 75) & (m["mod"] < 1435)]
    m["rng"] = m.hi - m.lo
    q = m.rng.quantile([0.9, 0.99, 0.999]).to_list()
    for lo, hi in zip([0.0] + q, q + [float("inf")]):
        x = m[(m.rng >= lo) & (m.rng < hi)]
        print(f"minutes with a range {lo:5.2f}-{hi:5.2f}: {len(x):5d}, spread median {x.s.median():.3f}, widest quote "
              f"median {x.widest.median():.3f}, 90% {x.widest.quantile(0.9):.3f}")
