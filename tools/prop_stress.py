"""Stress test of AurumFunded's FTMO 2-Step challenge on the daily Hydra legs it trades (all but grid and hold).

Unlike the tables of tools/backtest_prop.py, a challenge still open at the time limit counts as not passed, so the
numbers below are the share passed within that many trading days, next to the share failed.  Two stresses:
  edge  the mean daily result is cut to this share of the backtest (1/2, 1/3), the swings are kept
  dip   any day that closes below -dip % is booked as a hit of the 3% day stop (x1.2 slip): a pessimistic stand-in
        for days that fell through the stop during the day and recovered by the close, which daily data cannot see
The EA's rules are on: day stop 3%, sizes shrink within 6.5% of the final stop (not below 0.3), 4 trading days a
phase, a tenth of the size once the target is reached early.

    python tools/prop_stress.py

Result (2010-06 to 2026-10, a challenge started every third day), pass % / failed %:
  within 250 days   edge 1      1/2        1/2,dip 1.5  1/3        1/3,dip 1.5
  size 0.3          71.7/0.0    22.6/0.0   22.5/0.0     15.4/0.0   14.8/0.0
  size 0.5          96.4/0.0    54.7/0.0   46.2/0.2     37.2/0.4   34.0/2.5
  size 0.7          98.1/0.0    69.4/1.7   53.6/12.4    49.3/11.0  37.8/24.8
  size 1.0          99.3/0.0    74.0/14.6  58.1/27.2    52.1/31.0  42.8/48.9
  within 500 days
  size 0.5         100.0/0.0    89.1/0.0   81.9/3.8     65.9/9.6   60.1/16.3
  size 1.0         100.0/0.0    80.7/18.9  64.7/34.1    57.4/41.0  43.5/56.5
FTMO has no time limit, so an open challenge costs time and a failed one the fee: size 0.5 (the EA's default) keeps
failures near zero under every stress but the harshest; larger sizes pass sooner only when the edge holds.
"""
import numpy as np

import backtest_prop as B

TARGETS, DAILY, MOST = (10.0, 5.0), 5.0, 10.0
COLUMNS = ((1.0, None), (0.5, None), (0.5, 1.5), (0.33, None), (0.33, 1.5))


def shares(x, limit, every=3):
    o = np.array([B.challenge(x, s, TARGETS, DAILY, MOST, False, 3.0, limit=limit, room=6.5, least=0.3, days=4,
                              coast=0.1)[0] for s in range(0, len(x) - limit, every)])
    return (o == 1).mean() * 100, (o < 0).mean() * 100


if __name__ == "__main__":
    f = B.legs() * 100
    b = f.drop(columns=["grid", "hold"]).sum(axis=1)
    b = b[b.index.dayofweek < 5]
    print("columns: edge 1 | 1/2 | 1/2, dip 1.5 | 1/3 | 1/3, dip 1.5   (passed % / failed %)")
    for limit in (250, 500):
        print(f"within {limit} trading days")
        for size in (0.3, 0.5, 0.7, 1.0):
            row = []
            for edge, dip in COLUMNS:
                x = (b - b.mean() * (1 - edge)) * size
                if dip:
                    x = x.where(x > -dip, -3.0)
                p, fail = shares(x.to_numpy(), limit)
                row.append(f"{p:5.1f}/{fail:4.1f}")
            print(f"  size {size}: " + "   ".join(row))
