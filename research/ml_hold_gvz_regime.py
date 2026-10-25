"""ml_hold_gvz_regime: one pre-registered rule on the gold hold leg (thresholds fixed before any run).
Flat the next day when GVZ 250d percentile (GVZ lagged 1 day) > 0.8 AND sign(20d gold ret) != sign(60d gold ret).
Hold leg reproduced as in ml_regime_filter_gold_hold.py (target 0.107, swap 6.8%/yr, 0.8 bp round trip).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

TARGET, SWAP, COST = 0.107, 0.068, 0.8
OUT = ROOT / "marketdata" / "candidates"


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


g = pd.read_csv(ROOT / "marketdata" / "histdata" / "XAUUSD_H1.csv.gz")
g.index = pd.to_datetime(g.time, unit="s")
g = holdout.drop(g[["close"]])
D = g.close[g.index.hour == 22]
D.index = D.index.normalize()
R = np.log(D).diff()
vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
sig = (sum(np.sign(D / D.shift(k) - 1) for k in (20, 60, 120, 250)) / 4).clip(lower=0)
pos0 = (sig * TARGET / vol).clip(-3, 3).shift(1)


def leg(pos, m=1.0):
    return pos * R - pos.diff().abs() * COST * m * 1e-4 / 2 - pos.clip(lower=0) * SWAP * m / 252


gv = pd.read_csv(ROOT / "marketdata" / "volidx" / "GVZ.csv", index_col=0, parse_dates=True).close
gv = gv.reindex(D.index.union(gv.index)).ffill().reindex(D.index).shift(1)
gvp = gv.rolling(250, min_periods=250).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
dis = np.sign(D / D.shift(20) - 1) != np.sign(D / D.shift(60) - 1)
bad = (gvp > 0.8) & dis
flag = (~bad).astype(float)
pos = pos0 * flag.shift(-1).fillna(1.0)   # decision at close t scales the position of day t+1
base, base15 = leg(pos0), leg(pos0, 1.5)
r, r15 = leg(pos), leg(pos, 1.5)
print("GVZ first day", gv.first_valid_index().date())
valid = gvp.notna() & (sig > 0)
print("flagged share of signal-on days", round(float((bad & valid).sum() / valid.sum()), 3))
for lab, a, b in (("to 2017", "2008-07", "2018"), ("2018+", "2018", "2100")):
    s = lambda x: sh(x[(x.index >= a) & (x.index < b)])
    print(lab, "base", round(s(base), 2), "filtered", round(s(r), 2), "1.5x base", round(s(base15), 2), "filt", round(s(r15), 2))
# random-keep control at same flag rate
rng = np.random.default_rng(0)
idx = np.where((valid & (D.index >= "2008-07")).to_numpy())[0]
rate = float((bad & valid).sum() / valid.sum())
sr = []
for _ in range(500):
    sk = pd.Series(False, index=D.index)
    sk.iloc[idx[rng.random(len(idx)) < rate]] = True
    x = leg(pos0 * (~sk).astype(float).shift(-1).fillna(1.0))
    sr.append(sh(x[x.index >= "2018"]))
sr = np.array(sr)
print("random-keep 2018+ SR mean", round(sr.mean(), 2), "p95", round(np.percentile(sr, 95), 2))
ms = lambda s_: s_.groupby(s_.index.to_period("M")).sum()
mb, mf = ms(base), ms(r)
for m in ("2021-11", "2023-05"):
    print(m, "base", round(float(mb.get(pd.Period(m), np.nan)) * 100, 2), "filtered", round(float(mf.get(pd.Period(m), np.nan)) * 100, 2))
r = r[r.index >= "2008-07"]
r15 = r15[r15.index >= "2008-07"]
for f, s in ((OUT / "ml_hold_gvz_regime.csv", r), (OUT / "ml_hold_gvz_regime_stress.csv", r15)):
    s.dropna().rename("r").rename_axis("day").to_csv(f)
