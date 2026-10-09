"""Stress test of the H1 -> next-23-hours LightGBM lead: seeds, fold starts, by year, long-only versus random long
entries with the same count (is it more than gold drift?), feature importance, daily equity."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

COST = 0.16
H = 23

def feats(d, per_day):
    c, o, h, l = d.close, d.open, d.high, d.low
    lr = np.log(c).diff()
    f = pd.DataFrame(index=d.index)
    vol = lr.rolling(96).std()
    for k in (1, 2, 4, 8, 16, 32, 96, 288):
        f[f"r{k}"] = np.log(c / c.shift(k)) / (vol * np.sqrt(k))
    for k in (8, 32, 96):
        hi, lo = h.rolling(k).max(), l.rolling(k).min()
        f[f"pos{k}"] = (c - lo) / (hi - lo + 1e-9)
        f[f"er{k}"] = (c - c.shift(k)).abs() / lr.abs().rolling(k).sum().mul(c).add(1e-9)
    f["volr"] = lr.rolling(8).std() / vol
    f["volr2"] = vol / lr.rolling(per_day * 10).std()
    f["rng"] = (h - l) / (c * vol)
    f["body"] = (c - o) / (h - l + 1e-9)
    f["tv"] = d.tick_volume / d.tick_volume.rolling(96).mean()
    f["tod"] = d.dt.dt.hour * 60 + d.dt.dt.minute
    f["dow"] = d.dt.dt.dayofweek
    dopen = o.groupby(d.dt.dt.date).transform("first")
    f["sess"] = np.log(c / dopen) / vol
    f["vol"] = vol
    return f

d = rd.bars("H1").reset_index(drop=True)
X = feats(d, 23)
entry, exit_ = d.open.shift(-1), d.open.shift(-1 - H)
y = (exit_ - entry) / (d.close * X.vol)
pnl1 = (exit_ - entry)
ret1 = pnl1 / entry * 1e4                       # bp, so 2022 and 2026 trades weigh the same
ok = X.notna().all(axis=1) & y.notna()
idx = np.flatnonzero(ok.to_numpy())
n = len(d)
rng = np.random.default_rng(0)

def walk(start=0.4, folds=6, q=0.9, seed=0, cols=None, verbose=False):
    cols = cols or list(X.columns)
    edges = np.linspace(int(n * start), n, folds + 1).astype(int)
    T, imp = [], np.zeros(len(cols))
    for a, b in zip(edges[:-1], edges[1:]):
        tr = idx[idx < a - H - 1]; te = idx[(idx >= a) & (idx < b)]
        cut = int(len(tr) * 0.85)
        m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.02, num_leaves=15, min_child_samples=200, subsample=0.7,
                              subsample_freq=1, colsample_bytree=0.7, reg_lambda=5, verbose=-1, random_state=seed)
        m.fit(X[cols].iloc[tr[:cut]], y.iloc[tr[:cut]], eval_set=[(X[cols].iloc[tr[cut:]], y.iloc[tr[cut:]])],
              callbacks=[lgb.early_stopping(40, verbose=False)])
        imp += m.booster_.feature_importance("gain")
        thr = np.quantile(np.abs(m.predict(X[cols].iloc[tr[cut:]])), q)
        p = m.predict(X[cols].iloc[te]); nxt = -1
        for j, i in enumerate(te):
            if i < nxt or abs(p[j]) < thr: continue
            T.append((i, np.sign(p[j]))); nxt = i + H
    t = pd.DataFrame(T, columns=["i", "side"])
    t["pnl"] = t.side * pnl1.iloc[t.i].to_numpy() - COST
    t["bp"] = t.side * ret1.iloc[t.i].to_numpy() - COST / d.close.iloc[t.i].to_numpy() * 1e4
    t["dt"] = d.dt.iloc[t.i].to_numpy()
    return t, pd.Series(imp, index=cols).sort_values(ascending=False), edges

def ts(x):
    return f"n={len(x):4d} {x.mean():+7.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}" if len(x) > 3 else f"n={len(x)}"

t, imp, edges = walk()
print("base: $", ts(t.pnl), "| bp", ts(t.bp), "| long share", round((t.side > 0).mean(), 2))
print("by year (bp):", {k: ts(v) for k, v in t.bp.groupby(t.dt.dt.year)})
print("long (bp):", ts(t.bp[t.side > 0]), " short (bp):", ts(t.bp[t.side < 0]))
print("importance:", (imp / imp.sum()).round(3).head(10).to_dict())

# Benchmark: random long entries, same count per fold, non-overlapping not enforced (mean is what matters)
lo = t[t.side > 0]
pool = idx[idx >= edges[0]]
sims = []
for _ in range(2000):
    fold_of = np.searchsorted(edges, lo.i.to_numpy(), side="right")
    m = 0.0
    for f in np.unique(fold_of):
        pf = pool[(pool >= edges[f - 1]) & (pool < edges[f])]
        pick = rng.choice(pf, size=int((fold_of == f).sum()), replace=False)
        m += ret1.iloc[pick].sum()
    sims.append(m / len(lo) - (COST / d.close.iloc[lo.i].to_numpy() * 1e4).mean())
sims = np.array(sims)
print(f"long trades mean {lo.bp.mean():+.2f} bp vs random long entries in the same folds: mean {sims.mean():+.2f}, p95 {np.quantile(sims, .95):+.2f}, share above ours {100 * (sims >= lo.bp.mean()).mean():.1f}%")

# same hour-of-day benchmark: is it just 'buy at a certain hour'?
print("entry hour of trades:", t.dt.dt.hour.value_counts().sort_index().to_dict())

print("\nseeds / fold layouts / thresholds (bp per trade):")
for kw in ({"seed": 1}, {"seed": 2}, {"seed": 3}, {"start": 0.3}, {"start": 0.5}, {"folds": 12}, {"folds": 3}, {"q": 0.8}, {"q": 0.95}):
    tt, _, _ = walk(**kw)
    print(f"  {kw}: {ts(tt.bp)} | long {ts(tt.bp[tt.side > 0])} | short {ts(tt.bp[tt.side < 0])}")

print("\nfeature groups dropped:")
for name, drop in (("no time", ["tod", "dow"]), ("no vol", ["vol", "volr", "volr2"]), ("no long returns", ["r96", "r288"]),
                   ("only tod/dow/vol", None)):
    cols = ["tod", "dow", "vol", "volr2"] if drop is None else [c for c in X.columns if c not in drop]
    tt, _, _ = walk(cols=cols)
    print(f"  {name}: {ts(tt.bp)} | long share {(tt.side > 0).mean():.2f}")

# equity: 1 unit of notional per trade, bp returns
eq = t.set_index("dt").bp.resample("D").sum()
eq = eq[eq.index.dayofweek < 5]
cum = eq.cumsum()
print(f"\nequity (1x notional): total {cum.iloc[-1]:.0f} bp over {len(eq) / 252:.1f} y, Sharpe {eq.mean() / eq.std() * np.sqrt(252):.2f}, maxDD {(cum.cummax() - cum).max():.0f} bp, trades/yr {len(t) / (len(eq) / 252):.0f}")
bh = (d.close.iloc[-1] / d.close.iloc[edges[0]] - 1) * 1e4
print(f"buy and hold over the same span: {bh:.0f} bp")
