"""Settle the Asian dip-buy lead: random-entry baseline matched on year and hour, alternative shock definitions that do
not hinge on one volatility window, 15-minute slot and weekday breakdown, leave-one-year-out, max-statistic permutation
over the whole threshold x hold grid (multiple-testing aware)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

rng = np.random.default_rng(7)
COST = 0.16
def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 5: return f"n={len(x)}"
    return f"n={len(x):3d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}"

d = rd.bars("M15").reset_index(drop=True)
c, o, hi, lo = (d[k].to_numpy() for k in ("close", "open", "high", "low"))
n = len(d)
lr = pd.Series(np.log(c)).diff()
date = d.dt.dt.date
hour = d.dt.dt.hour.to_numpy()
year = d.dt.dt.year.to_numpy()
slot = (d.dt.dt.hour * 60 + d.dt.dt.minute).to_numpy()
dow = d.dt.dt.dayofweek.to_numpy()
cut = int(n * 0.6)

def fwd_k(k):
    f = np.full(n, np.nan)
    f[:n - k - 1] = (o[1 + k:] - o[1:n - k] - COST) / c[:n - k - 1] * 1e4
    f[~(date.shift(-k - 1) == date).to_numpy()] = np.nan
    return f

def pick(ok, k):
    idx, nxt = [], -1
    for i in np.flatnonzero(ok):
        if i >= nxt: idx.append(i); nxt = i + k + 1
    return np.array(idx, dtype=int)

asia = (hour >= 1) & (hour <= 8)
z96 = (lr / lr.rolling(96).std().shift(1)).to_numpy()
F4 = fwd_k(4)

# --- 1. random-entry baseline: same number of entries per (year, hour), 5000 draws
i0 = pick((z96 <= -3) & asia & ~np.isnan(F4), 4)
obs = F4[i0].mean()
pools = {}
valid = asia & ~np.isnan(F4)
for y in np.unique(year):
    for h in range(1, 9):
        pools[(y, h)] = np.flatnonzero(valid & (year == y) & (hour == h))
need = pd.Series(1, index=pd.MultiIndex.from_arrays([year[i0], hour[i0]])).groupby(level=[0, 1]).sum()
draws = np.empty(5000)
for r in range(5000):
    tot = 0.0
    for (y, h), m in need.items():
        tot += F4[rng.choice(pools[(y, h)], m, replace=False)].sum()
    draws[r] = tot / len(i0)
print(f"1. dip-buy thr 3 k 4: observed {obs:+.2f} bp (n={len(i0)}); random entries matched on year x hour: mean {draws.mean():+.2f}, "
      f"sd {draws.std():.2f}, p(random >= observed) = {(draws >= obs).mean():.4f}")
for nm, m in (("train", i0 < cut), ("test", i0 >= cut)):
    print(f"   {nm}: {st(F4[i0[m]])}")

# --- 2. max-statistic over the grid: permute which Asian bars are 'signals' within year x hour, keep the best t of the grid
grid = [(thr, k) for thr in (2.5, 3.0, 3.5, 4.0) for k in (2, 4, 8, 16)]
Fk = {k: fwd_k(k) for k in (2, 4, 8, 16)}
def tstat(x): return x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 5 else 0.0
obs_t = {g: tstat(Fk[g[1]][pick((z96 <= -g[0]) & asia & ~np.isnan(Fk[g[1]]), g[1])]) for g in grid}
best_obs = max(obs_t.values())
key = year * 100 + hour
order = np.argsort(key, kind="stable")
bounds = np.flatnonzero(np.diff(key[order])) + 1
groups = np.split(order, bounds)
mx = np.empty(1000)
for r in range(1000):
    zp = z96.copy()
    for g in groups:
        zp[g] = z96[rng.permutation(g)]            # shuffle shocks among bars of the same year and hour
    mx[r] = max(tstat(Fk[k][pick((zp <= -thr) & asia & ~np.isnan(Fk[k]), k)]) for thr, k in grid)
print(f"2. grid t-stats observed: best {best_obs:.2f} ({max(obs_t, key=obs_t.get)}); permutation max-t: mean {mx.mean():.2f}, 95% {np.quantile(mx, .95):.2f}, "
      f"p(max >= observed best) = {(mx >= best_obs).mean():.4f}; thr 3 k 4 t {obs_t[(3.0, 4)]:.2f} -> p = {(mx >= obs_t[(3.0, 4)]).mean():.4f}")

# --- 3. alternative shock definitions (thr tuned to give a similar count), k = 4: train | test
print("3. alternative definitions, hold 4 bars: train | test")
def show(nm, ok):
    i = pick(ok & asia & ~np.isnan(F4), 4)
    print(f"   {nm:44s} {st(F4[i[i < cut]])} | {st(F4[i[i >= cut]])} | all {st(F4[i])}")
show("z96 <= -3 (reference)", z96 <= -3)
ewm = (lr / np.sqrt((lr ** 2).ewm(halflife=96).mean()).shift(1)).to_numpy()
for t in (3.0, 3.5): show(f"EWMA vol (hl 96) z <= -{t}", ewm <= -t)
# same-slot volatility: std of this 15-min slot's return over the previous 20 days
ss = lr.groupby(slot).transform(lambda x: x.rolling(20).std().shift(1)).to_numpy()
for t in (2.5, 3.0, 3.5): show(f"same-slot 20-day vol z <= -{t}", (lr.to_numpy() / ss) <= -t)
# range-based: bar range and drop relative to 20-day median daily range
dr = d.groupby(date).agg(h=("high", "max"), l=("low", "min"))
adr = (dr.h - dr.l).rolling(20).median().shift(1)
adr_bar = date.map(adr).to_numpy()
drop = (o - c) / adr_bar
for t in (0.2, 0.25, 0.3, 0.4): show(f"bar drop >= {t} x 20-day median daily range", drop >= t)
# ATR-based (classic retail): drop >= x ATR(14) of M15
tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(c, 1)), np.abs(lo - np.roll(c, 1))))
atr = pd.Series(tr).rolling(14).mean().shift(1).to_numpy()
for t in (2.0, 2.5, 3.0): show(f"bar drop >= {t} x ATR14", (o - c) / atr >= t)
atr96 = pd.Series(tr).rolling(96).mean().shift(1).to_numpy()
for t in (2.5, 3.0, 4.0): show(f"bar drop >= {t} x ATR96", (o - c) / atr96 >= t)

# --- 4. where it sits
t = pd.DataFrame({"i": i0, "net": F4[i0], "slot": slot[i0], "dow": dow[i0], "hour": hour[i0], "year": year[i0]})
print("4. by weekday:", {("Mon", "Tue", "Wed", "Thu", "Fri")[k] + str(k): st(v) for k, v in t.net.groupby(t.dow)})
print("   by hour train:", {int(k): st(v) for k, v in t.net[t.i < cut].groupby(t.hour)})
print("   by hour test: ", {int(k): st(v) for k, v in t.net[t.i >= cut].groupby(t.hour)})
print("   excluding hour 03:", st(t.net[t.hour != 3]), "| train", st(t.net[(t.hour != 3) & (t.i < cut)]), "| test", st(t.net[(t.hour != 3) & (t.i >= cut)]))
print("   leave one year out:", {int(y): st(t.net[t.year != y]) for y in np.unique(t.year)})
# size of the dip vs rebound
zz = z96[i0]
print("   by shock size:", {str(k): st(v) for k, v in t.net.groupby(pd.cut(-zz, [3, 3.5, 4, 5, 99]), observed=True)})
# rebound share: forward return as a fraction of the drop
dropbp = -lr.to_numpy()[i0] * 1e4
print(f"   median drop {np.median(dropbp):.1f} bp, mean rebound {t.net.mean():+.1f} bp = {100 * t.net.mean() / dropbp.mean():.0f}% of mean drop")
# path: cumulative mean after entry, bar by bar (gross)
path = [np.nanmean((o[np.minimum(i0 + 1 + k, n - 1)] - o[i0 + 1]) / c[i0] * 1e4) for k in range(1, 17)]
print("   mean gross path by bar 1..16:", " ".join(f"{p:+.1f}" for p in path))
