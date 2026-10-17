"""The AUDCAD grid leg of AurumHydra (tools/backtest_hydra.py `grid`, 5-month average, 1-sigma steps, 4 levels)
run unchanged on the other range-bound crosses in the minute data, to see whether more grids add to Hydra.

Hourly closes on the server clock as in `hourly`; costs in bp per round trip from typical raw-spread quotes plus
commission; swaps unknown for most pairs, so the run is without swap and again with -0.5 bp per night on both
sides (a pessimistic carry).  Sizes as the AUDCAD leg (0.035 of the loss at the stop-out); the weight of an added
grid is picked on 2010-2017 and checked on 2018-2026.

    python research/grid_crosses.py

Result (2026-10-15): rejected, AUDCAD stays the only grid.  Grid Sharpe without swap 2010-17 / 2018-26: AUDCAD
1.01 / 0.94; next best NZDCAD 0.86 / 0.03, EURCHF 0.60 / 0.07, AUDUSD 0.60 / 0.32, USDCAD 0.22 / 0.23; AUDNZD,
EURGBP, GBPCHF, EURAUD, the yen crosses, EURUSD, USDCHF, NZDUSD at or below zero in one period or both.  Added to
Hydra with the weight best to 2017, no pair lifts 2018-26 above 3.37-3.38 (NZDCAD, the one the 2017 fit picks at
size, takes it to 3.11-3.24).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import backtest_hydra as B  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "marketdata" / "histdata"
CACHE = Path(__file__).resolve().parents[1] / "marketdata" / "hydra_legs_daily.csv.gz"
COST = {"AUDCAD": 1.8, "AUDNZD": 2.0, "NZDCAD": 2.6, "EURGBP": 1.2, "EURCHF": 1.6, "GBPCHF": 2.4, "EURAUD": 2.0,
        "AUDJPY": 1.6, "CADJPY": 2.0, "EURJPY": 1.4, "GBPJPY": 2.4, "AUDUSD": 1.0, "NZDUSD": 1.4, "EURUSD": 0.8,
        "USDCHF": 1.2, "USDCAD": 1.2}


def hourly(s):
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
    x = m.sort_values("time").groupby(m.time // 3600).close.last()
    x.index = pd.to_datetime(x.index.to_numpy() * 3600, unit="s")
    x = x[(x.index.dayofweek < 5) & (x.index.hour >= 1) & (x.index.hour <= 22)]
    return x.loc["2009-06-01":]


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    L = pd.read_csv(CACHE, index_col=0, parse_dates=True)
    hy = L.sum(axis=1)
    hy = hy[hy.index.dayofweek < 5]
    print(f"Hydra as is: 2010-17 {sharpe(hy[:'2017']):.2f}  2018-26 {sharpe(hy['2018':]):.2f}")
    for s, c in COST.items():
        p = hourly(s)
        for sw in (0.0, -0.5):
            g = (0.035 * B.grid(p, 5, 1.0, 4, c, 1.0, swap=(sw, sw))).reindex(hy.index).fillna(0.0)
            cor = g.corr(L["grid"].reindex(hy.index).fillna(0))
            best, wb = -9, 0
            for w in (0.25, 0.5, 1.0, 1.5, 2.0):
                v = sharpe((hy + w * g)[:"2017"])
                if v > best:
                    best, wb = v, w
            add = hy + wb * g
            print(f"{s} swap {sw:+.1f}: grid Sharpe 2010-17 {sharpe(g[:'2017']):+.2f} 2018-26 {sharpe(g['2018':]):+.2f}"
                  f"  corr AUDCAD grid {cor:+.2f}  | Hydra + {wb} x: 2010-17 {sharpe(add[:'2017']):.2f} "
                  f"2018-26 {sharpe(add['2018':]):.2f}", flush=True)
