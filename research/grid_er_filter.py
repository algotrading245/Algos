"""Kaufman efficiency-ratio start filter on the AUDCAD grid (idea ml_grid_er_start_filter).
ER = |c[t]-c[t-N]| / sum|daily change| over N days, daily closes (server hour 22) of the PREVIOUS day.
A new grid cycle (q == 0) is not opened while ER > thr. Open cycles run as before.
Pre-registered: (N=10, thr=0.5) primary, (N=20, thr=0.4) robustness. Both counted.
    python research/grid_er_filter.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))
import backtest_hydra as B  # noqa: E402
from grid_crosses import hourly  # noqa: E402

CAND = ROOT / "marketdata" / "candidates"


def er_series(p, n):
    d = p[p.index.hour == 22]
    d.index = d.index.normalize()
    d = np.log(d)
    er = (d - d.shift(n)).abs() / d.diff().abs().rolling(n).sum()
    return er.shift(1)  # known before the day


def grid_f(p, ma, step, levels, cost, er, thr):
    """B.grid with a start filter: copy of the loop, new cycle skipped when er(day) > thr."""
    mult = 1.0
    wt = np.concatenate([[0.0], np.cumsum(mult ** np.arange(levels))])
    risk = sum(mult ** (k - 1) * (levels + 1 - k) for k in range(1, levels + 1))
    lp = np.log(p.to_numpy())
    avg = pd.Series(lp).rolling(ma * 22).mean().to_numpy()
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40).std() * np.sqrt(22)).shift(1).to_numpy()
    days = p.index.normalize()
    erv = er.reindex(days).to_numpy()
    out = np.zeros(len(lp))
    q, dead, unit = 0, False, 1.0
    skipped = starts = 0
    for i in range(len(lp)):
        if q:
            out[i] = np.sign(q) * wt[abs(q)] * r[i] / unit
        if np.isnan(avg[i]) or np.isnan(dv[i]) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (step * dv[i])
        az, side = abs(z), (1 if z > 0 else -1)
        if dead:
            dead = az >= 0.5
            continue
        if q == 0:
            unit = step * dv[i]
        if az >= levels + 1:
            new, dead = 0, True
        else:
            cur = abs(q) if q * side < 0 else 0
            new = -side * max(min(int(az), levels), min(cur, int(np.ceil(az))))
        if q == 0 and new != 0:
            starts += 1
            if not np.isnan(erv[i]) and erv[i] > thr:
                skipped += 1
                new = 0
        if new != q:
            out[i] -= abs(np.sign(new) * wt[abs(new)] - np.sign(q) * wt[abs(q)]) * cost * 1e-4 / 2 / unit
            q = new
    return pd.Series(out, index=p.index).groupby(days).sum() / risk, skipped, starts


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    p = hourly("AUDCAD")
    base = {c: 0.035 * B.grid(p, 5, 1.0, 4, 1.8 * c, 1.0) for c in (1, 1.5, 2)}
    b = base[1]
    print(f"base 1x: to2017 {sh(b[:'2017']):.2f} 2018+ {sh(b['2018':]):.2f}")
    for n, thr in ((10, 0.5), (20, 0.4)):
        er = er_series(p, n)
        res = {}
        for c in (1, 1.5, 2):
            g, sk, st = grid_f(p, 5, 1.0, 4, 1.8 * c, er, thr)
            res[c] = 0.035 * g
        g = res[1]
        print(f"N={n} thr={thr}: skipped {sk}/{st} starts ({sk/st:.0%}); 1x halves {sh(g[:'2017']):.2f}/{sh(g['2018':]):.2f}"
              f"  1.5x {sh(res[1.5]['2018':]):.2f}  2x {sh(res[2]['2018':]):.2f}")
        if (n, thr) == (10, 0.5):
            hy = g[g.index.dayofweek < 5]
            hy.rename("r").rename_axis("day").to_csv(CAND / "ml_grid_er_start_filter.csv")
            res[1.5][res[1.5].index.dayofweek < 5].rename("r").rename_axis("day").to_csv(
                CAND / "ml_grid_er_start_filter_stress.csv")
