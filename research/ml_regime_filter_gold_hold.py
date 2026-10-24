"""ml_regime_filter_gold_hold: walk-forward skip filter on the gold hold leg.

Hold leg = tools/backtest_hydra.hold with the EA settings (target 0.107, swap 6.8%/yr, cost 0.8 bp round trip).
Label: sign of the leg's next-20-trading-day P&L (after cost), on days the trend signal is long.
Features (past-only, known at the day's hour-22 close; GVZ and DGS10 lagged one day):
  gold 20d and 60d return, 20d vol / 250d vol, GVZ level, GVZ 60d percentile, DGS10 20d change, distance from 200d mean in vol units.
Model: depth-2 GBM (3 seeds) and logistic regression; refit each year on all earlier data, purge 20 days.
Rule fixed before testing: skip (flat) when P(win) < 0.45. Random-keep control at the same skip rate (500 draws).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

TARGET, SWAP, COST = 0.107, 0.068, 0.8
THR, FIRST_TEST, PURGE, H = 0.45, 2013, 20, 20
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


def leg(pos, mult=1.0):
    return pos * R - pos.diff().abs() * COST * mult * 1e-4 / 2 - pos.clip(lower=0) * SWAP * mult / 252


base, base15 = leg(pos0), leg(pos0, 1.5)
book = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).hold
print("reproduction corr with book hold:", round(base.corr(book), 3), "sharpe", round(sh(base), 2), "book", round(sh(book), 2))

# features
fr = {}
fr["r20"] = D / D.shift(20) - 1
fr["r60"] = D / D.shift(60) - 1
v20, v250 = R.rolling(20).std(), R.rolling(250).std()
fr["vr"] = v20 / v250
gv = pd.read_csv(ROOT / "marketdata" / "fred" / "GVZCLS.csv", index_col=0, parse_dates=True).iloc[:, 0]
gv = pd.to_numeric(gv, errors="coerce").reindex(D.index.union(gv.index)).ffill().reindex(D.index).shift(1)
# GVZ missing early on / late: fall back to realised vol (annualised %) so rows are never dropped
rv = R.rolling(20).std() * np.sqrt(252) * 100
fr["gvz"] = gv.fillna(rv)
fr["gvzp"] = fr["gvz"].rolling(60).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
y10 = pd.read_csv(ROOT / "marketdata" / "fred" / "DGS10.csv", index_col=0, parse_dates=True).iloc[:, 0]
y10 = pd.to_numeric(y10, errors="coerce").reindex(D.index.union(y10.index)).ffill().reindex(D.index).shift(1)
fr["dy"] = y10.diff(20)
fr["d200"] = (np.log(D) - np.log(D.rolling(200).mean())) / (v20 * np.sqrt(20))
X = pd.DataFrame(fr)
print("GVZ coverage", round(float(gv.notna().mean()), 3), "last", gv.last_valid_index().date())

# label: next-H-day leg P&L from the unfiltered path (days t+1..t+H)
fwd = base[::-1].rolling(H).sum()[::-1].shift(-1)
y = (fwd > 0).astype(float).where(fwd.notna())
on = (sig > 0) & X.notna().all(axis=1) & (pos0.shift(-1) > 0)
print("signal-on days:", int(on.sum()), "win share", round(float(y[on].mean()), 3))

yrs = sorted(set(D.index.year))
P = {}  # model -> series of out-of-sample probabilities
for name in ("gbm0", "gbm1", "gbm2", "logit"):
    P[name] = pd.Series(np.nan, index=D.index)
for yr in range(FIRST_TEST, max(yrs) + 1):
    te = on & (D.index.year == yr)
    cut = pd.Timestamp(f"{yr}-01-01")
    tr = on & (D.index < cut - pd.tseries.offsets.BDay(PURGE)) & y.notna()
    if te.sum() == 0 or tr.sum() < 200:
        continue
    for s in range(3):
        m = GradientBoostingClassifier(max_depth=2, n_estimators=100, learning_rate=0.05, subsample=0.8, random_state=s)
        m.fit(X[tr], y[tr])
        P[f"gbm{s}"][te] = m.predict_proba(X[te])[:, 1]
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=500))
    m.fit(X[tr], y[tr])
    P["logit"][te] = m.predict_proba(X[te])[:, 1]

test = on & (D.index.year >= FIRST_TEST) & y.notna()
print("test days", int(test.sum()), "base win share", round(float(y[test].mean()), 3))
res = {}
for name, p in P.items():
    auc = roc_auc_score(y[test], p[test])
    skip = (p < THR) & on
    flag = (~skip).astype(float)             # decision at close t scales position of day t+1
    pos = pos0 * flag.shift(-1).fillna(1.0)  # pos0[t+1] was set at close t: multiply by flag[t]
    r, r15 = leg(pos), leg(pos, 1.5)
    skr = float(skip[test].mean())
    res[name] = (r, r15, skr)
    sel = lambda s_, a, b: sh(s_[(s_.index >= a) & (s_.index < b)])
    print(f"{name}: AUC {auc:.3f} skip {skr:.2%} | filtered SR 2013-17 {sel(r,'2013','2018'):.2f} (base {sel(base,'2013','2018'):.2f}) "
          f"2018+ {sel(r,'2018','2100'):.2f} (base {sel(base,'2018','2100'):.2f}) | 1.5x {sh(r15[r15.index>='2013']):.2f}")

# random-keep control at the gbm0 skip rate
name = "gbm0"
rng = np.random.default_rng(0)
skr = res[name][2]
idx = np.where(test.to_numpy())[0]
sr18 = []
for _ in range(500):
    sk = pd.Series(False, index=D.index)
    sk.iloc[idx[rng.random(len(idx)) < skr]] = True
    pos = pos0 * (~sk).astype(float).shift(-1).fillna(1.0)
    r = leg(pos)
    sr18.append(sh(r[r.index >= "2018"]))
sr18 = np.array(sr18)
r, _, _ = res[name]
print(f"random-keep 2018+ SR mean {sr18.mean():.2f} sd {sr18.std():.2f} p95 {np.percentile(sr18,95):.2f}; filtered {sh(r[r.index>='2018']):.2f}")

# write candidate (gbm0; before FIRST_TEST the unfiltered leg)
r, r15, _ = res["gbm0"]
for f, s in ((OUT / "ml_regime_filter_gold_hold.csv", r), (OUT / "ml_regime_filter_gold_hold_stress.csv", r15)):
    s.dropna().rename("r").rename_axis("day").to_csv(f)
# losing months
ms = lambda s_: s_.groupby(s_.index.to_period("M")).sum()
mb, mf = ms(base), ms(r)
for m in ("2021-11", "2023-05", "2024-05", "2024-07"):
    print(m, "base", round(float(mb.get(pd.Period(m), np.nan)) * 100, 2), "filtered", round(float(mf.get(pd.Period(m), np.nan)) * 100, 2), "% of equity")
