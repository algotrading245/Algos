"""Online re-weighting of the Hydra legs with the exponentiated-gradient (EG) update (Helmbold, Schapire, Singer,
Warmuth, "On-line portfolio selection using multiplicative updates", Mathematical Finance 1998).

Each leg is a sub-strategy with daily return x_i (at the EA's size).  EG keeps weights w (sum = number of legs, so
equal weights = the EA) and after each day sets w_i <- w_i exp(eta x_i / (w . x + 1)), renormalised; a floor of 0.2
and a cap of 3 per leg keep it from betting everything on one.  eta is chosen on 2010-2017 only from a short grid,
then run on through 2026.  Compared with the EA's fixed weights.

    python research/online_leg_weights.py

Result (2026-10-15): rejected.  Hydra fixed 2.60 / 3.37 (to 2017 / from 2018); EG at eta 0.5-50: 2.14-2.53 /
2.44-2.79, the eta picked on 2010-2017 (10) 2.71 from 2018.  AurumFunded fixed 2.66 / 3.24, EG 2.33-2.63 from
2018.  The multiplicative update never forgets, so it piles into the legs that have earned most so far and loses
the diversification of the equal-risk weights - the same lesson as the one-off weight refit.
"""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def eg(X, eta, floor=0.2, cap=3.0):
    n = X.shape[1]
    w = np.ones(n)
    out = np.zeros(len(X))
    for t in range(len(X)):
        x = X[t]
        out[t] = w @ x
        w = w * np.exp(eta * x / (1.0 + w @ x / n))
        w = np.clip(w / w.sum() * n, floor, cap)
        w = w / w.sum() * n
    return out


if __name__ == "__main__":
    L = pd.read_csv(CACHE, index_col=0, parse_dates=True)
    L = L[L.index.dayofweek < 5]
    for name, cols in (("Hydra", list(L)), ("AurumFunded", [c for c in L if c not in ("grid", "hold")])):
        X = L[cols].to_numpy()
        base = pd.Series(X.sum(axis=1), index=L.index)
        print(f"{name} fixed weights: to 2017 {sharpe(base[:'2017']):.2f}, 2018+ {sharpe(base['2018':]):.2f}")
        best = None
        for eta in (0.5, 1, 2, 5, 10, 20, 50):
            y = pd.Series(eg(X, eta), index=L.index)
            s17 = sharpe(y[:"2017"])
            best = max(best or (s17, eta, y), (s17, eta, y), key=lambda z: z[0])
            print(f"  EG eta {eta:4}: to 2017 {s17:.2f}, 2018+ {sharpe(y['2018':]):.2f}")
        s17, eta, y = best
        print(f"  -> eta picked on 2010-2017: {eta}, 2018+ {sharpe(y['2018':]):.2f} vs fixed {sharpe(base['2018':]):.2f}")
