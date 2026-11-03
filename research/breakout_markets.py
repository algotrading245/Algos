"""Belief check for the USD/JPY London breakout: the same rules and parameters (london_breakout.run, both sides,
stop at the range's other side, exit 18:00, range 01-09, entry 10-18) on other markets, at each market's real
round-trip cost in bp. No per-market tuning. Writes marketdata/candidates/breakout_markets.csv (day + one column
per market, daily R net of cost, x0.003 scale not applied - R units).

    python research/breakout_markets.py
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import london_breakout as lb
import holdout

OUT = Path(__file__).resolve().parent.parent / "marketdata" / "candidates" / "breakout_markets.csv"
# round-trip cost in bp (from london_breakout.py notes): USDJPY 1.2 real ticks; others their spreads
MK = {"USDJPY": 1.2, "EURJPY": 1.4, "GBPJPY": 2.0, "CADJPY": 2.0, "AUDJPY": 2.0, "XAUUSD": 1.0,
      "EURUSD": 0.8, "GBPUSD": 1.0, "AUDUSD": 1.0}


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


cols = {}
for s, c in MK.items():
    T = lb.run(s, both=True)
    r = T.r - c * 1e-4 / T.rel
    d = pd.Series(r.to_numpy(), index=T.day).groupby(level=0).sum()
    cols[s] = d
    print(f"{s}: {len(T)} trades, net Sharpe {sh(d):+.2f} (to2017 {sh(d[:'2017']):+.2f}, 2018+ {sh(d['2018':]):+.2f})")
df = pd.DataFrame(cols).fillna(0.0)
df.index.name = "day"
df = df[df.index <= "2025-10-12"]
df.to_csv(OUT)
