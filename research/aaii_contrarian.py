"""AAII bull-bear spread contrarian on US500/US100.
Rule (fixed, no tuning): spread = bull% - bear%; z = (spread - mean)/sd over the trailing 260 weekly readings (past only,
including the current reading). Survey is reported Thursday; act at that Thursday's NY close (16:00), long if z<=-1.5,
short if z>=+1.5, hold 20 trading days (a new same-side trigger resets the clock, an opposite one flips). Flat otherwise.
Size = 0.01 / trailing 20-day sd of daily returns, cap 4. Cost per position change: US500 0.5 bp, US100 0.75 bp per side
(1 / 1.5 bp round trip); 1.5x, 2x shown.  Halves: to 2017, 2018 on.  Holdout dropped.
    python research/aaii_contrarian.py [write]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import holdout
from overnight_intraday_reversal import NY, matrix
import biff_read

SPLIT = pd.Timestamp("2018-01-01")
root = Path(__file__).resolve().parent.parent / "marketdata"
MK = {"SPXUSD": 0.5, "NSXUSD": 0.75}


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def rep(l, x):
    print(f"{l:30s} all {sh(x):+.2f}  to2017 {sh(x[:SPLIT]):+.2f}  2018+ {sh(x[SPLIT:]):+.2f}  active={int((x != 0).sum())}")


def survey():
    sh0 = biff_read.read(str(root / "aaii" / "sentiment.xls"))[0]
    rows = []
    for r in sorted(set(r for r, c in sh0)):
        dt, bu, be = sh0.get((r, 0)), sh0.get((r, 1)), sh0.get((r, 3))
        if isinstance(dt, float) and isinstance(bu, float) and isinstance(be, float):
            rows.append((pd.Timestamp("1899-12-30") + pd.Timedelta(days=dt), bu - be))
    s = pd.Series(dict(rows)).sort_index()
    z = (s - s.rolling(260).mean()) / s.rolling(260).std()
    return s, z.dropna()


def leg(sym, z, mult, thr=1.5, hold=20, sign=1):
    d, p = matrix(sym, NY)
    cl = pd.Series(p[:, 960], index=d).dropna()
    cl = cl[cl.index.dayofweek < 5]
    ret = cl.pct_change()
    vol = ret.rolling(20).std().shift(1)
    sig = pd.Series(0.0, index=cl.index)
    for t, v in z.items():
        # Thursday report; map to that day's close (or next trading day if missing)
        i = cl.index.searchsorted(t)
        if i < len(cl) and abs(v) >= thr:
            sig.iloc[i] = -np.sign(v) * sign
    pos = np.zeros(len(cl))
    cur, left = 0.0, 0
    for i in range(len(cl)):
        pos[i] = cur  # position held over the NEXT day's return is set at close i
        if sig.iloc[i] != 0:
            cur, left = sig.iloc[i], hold
        elif left > 0:
            left -= 1
            if left == 0:
                cur = 0.0
        pos[i] = cur
    pos = pd.Series(pos, index=cl.index)
    held = pos.shift(1).fillna(0)           # position carried into day t
    size = (0.01 / vol).clip(upper=4)
    chg = (pos - pos.shift(1).fillna(0)).abs()   # trades at close t
    cost = chg * MK[sym] * mult * 1e-4
    out = (held * ret - cost) * size
    return holdout.drop(out.dropna())


if __name__ == "__main__":
    s, z = survey()
    print("survey", s.index[0].date(), s.index[-1].date(), len(s), "z weeks", len(z), " |z|>=1.5:", int((z.abs() >= 1.5).sum()))
    res, strs, mk = {}, {}, {}
    for sym in MK:
        for m in (1.0, 1.5, 2.0):
            x = leg(sym, z, m)
            rep(f"{sym} {m}x", x)
            if m == 1.0:
                res[sym] = x
            if m == 1.5:
                strs[sym] = x
        rep(f"{sym} no cost", leg(sym, z, 0.0))
        rep(f"{sym} same-sign (control)", leg(sym, z, 1.0, sign=-1))
        rep(f"{sym} thr1.0 (info)", leg(sym, z, 1.0, thr=1.0))
        mk[sym] = res[sym]
    cand = (res["SPXUSD"] + res["NSXUSD"]) / 2
    cs = (strs["SPXUSD"] + strs["NSXUSD"]) / 2
    rep("US500+US100 1x", cand)
    rep("US500+US100 1.5x", cs)
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        cand.rename("r").rename_axis("day").to_csv(root / "candidates" / "aaii_contrarian.csv")
        cs.rename("r").rename_axis("day").to_csv(root / "candidates" / "aaii_contrarian_stress.csv")
        pd.DataFrame(mk).rename_axis("day").to_csv(root / "candidates" / "aaii_contrarian_markets.csv")
