"""USD/JPY London breakout (research/london_breakout.py, both sides) on real bid and ask ticks, to check the cost
the minute-bar test assumes (0.8 bp a round trip).

Ticks from histdata.com (tools/download_histdata_ticks.py, server minutes 600-1080 kept, server = New York + 7).
Range from the bid minute bars of 01:00-09:00 as in the EA; a buy stop fills at the first ask at or above the range
high (at that ask), a sell stop at the first bid at or below the range low; a long's stop fills at the first bid at
or below the range low (at that bid), a short's at the first ask at or above the high; open trades leave at the
last bid / ask before 18:00.  Commission on top: FTMO's $2.50 a lot a side, ~0.5 bp a round trip.  The same days
by the minute-bar rule with 0.8 bp for comparison.

    python research/breakout_ticks.py <tick folder>

Result (2024-01 to 2026-09, 33 months of ticks): 777 trades, +0.052 R a trade, Sharpe 0.78 on real fills with
commission; the minute-bar rule at 0.8 bp on the same days +0.058 R, 0.90.  Spread at the entry tick: median 0.34
bp, mean 0.53 bp.  The tick fills cost about 1.2 bp a round trip all in, not 0.8.  At 1.2 bp over 2010-2026 the leg
is 1.18 to 2017 and 0.83 from 2018; in AurumFunded at its volatility with 0.125% a trade 3.24 -> 3.30 from 2018
(drawdown 11.4% -> 10.8%); Hydra with the noise leg and the breakout at 0.5% 3.63 (3.71 at 0.8 bp).  The candidate
holds at the real cost, with a smaller margin.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from london_breakout import DATA, run  # noqa: E402

COMM = 0.5e-4


def ranges():
    m = pd.read_csv(DATA / "USDJPY_M1.csv.gz")
    t = pd.to_datetime(m.time, unit="s")
    m = m[(t.dt.dayofweek < 5) & (t >= "2023-09-01")]
    t = pd.to_datetime(m.time, unit="s")
    h = t.dt.hour
    a = m[(h >= 1) & (h < 9)]
    g = a.groupby(pd.to_datetime(a.time, unit="s").dt.normalize()).agg(hi=("high", "max"), lo=("low", "min"),
                                                                        last=("close", "last"), n=("close", "size"))
    g["w"] = (g.hi - g.lo) / g["last"]
    avg = g.w.rolling(60, min_periods=30).mean().shift(1)
    g["ok"] = (g.n >= 300) & (g.w >= 0.25 * avg) & (g.w <= 3 * avg)
    return g


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    G = ranges()
    rows = []
    for f in sorted(folder.glob("USDJPY_*.pkl")):
        T = pd.read_pickle(f)
        T["day"] = pd.to_datetime(T.srv).dt.normalize() if not np.issubdtype(T.srv.dtype, np.number) else \
            pd.to_datetime(T.srv, unit="s").dt.normalize()
        for day, d in T.groupby("day"):
            if day not in G.index or not G.loc[day, "ok"]:
                continue
            hi, lo = G.loc[day, "hi"], G.loc[day, "lo"]
            bid, ask = d.bid.to_numpy(), d.ask.to_numpy()
            for side in (1, -1):
                if side > 0:
                    k = np.flatnonzero(ask >= hi)
                    if not len(k):
                        continue
                    e = ask[k[0]]
                    s = np.flatnonzero(bid[k[0]:] <= lo)
                    x = bid[k[0] + s[0]] if len(s) else bid[-1]
                else:
                    k = np.flatnonzero(bid <= lo)
                    if not len(k):
                        continue
                    e = bid[k[0]]
                    s = np.flatnonzero(ask[k[0]:] >= hi)
                    x = ask[k[0] + s[0]] if len(s) else ask[-1]
                R = hi - lo
                rows.append((day, side, (side * (x - e) - COMM * e) / R, R / e, (ask[k[0]] - bid[k[0]]) / e))
    D = pd.DataFrame(rows, columns=["day", "side", "r", "rel", "spread"])
    first, last = D.day.min(), D.day.max()
    M = run("USDJPY", "side", both=True)
    M = M[(M.day >= first) & (M.day <= last)]
    m = M.r - 0.8e-4 / M.rel
    sh = lambda x: x.mean() / x.std() * np.sqrt(252)
    dt = D.groupby("day").r.sum()
    dm = pd.Series(m.to_numpy(), index=M.day).groupby(level=0).sum()
    print(f"{first.date()} to {last.date()}: ticks {len(D)} trades, {D.r.mean():+.3f} R, Sharpe {sh(dt):.2f}; spread at "
          f"entry median {D.spread.median() * 1e4:.2f} bp (mean {D.spread.mean() * 1e4:.2f}); minute bars at 0.8 bp: "
          f"{len(M)} trades, {m.mean():+.3f} R, Sharpe {sh(dm):.2f}")
    imp = (D.r.mean() - (M.r.mean())) * D.rel.median() * 1e4
    print(f"implied round-trip cost of the tick fills incl. commission vs the cost-free minute model: {-imp:.2f} bp")
