"""Asian dip buy: after an extreme DOWN M15 bar in Asian hours, buy the next open, hold k bars.
Stress: threshold x hold by half, by year, by hour, excess over same-year same-slot baseline, outliers, cost,
vol-window choice, M5 replication, simple equity."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 5: return f"n={len(x)}"
    return f"n={len(x):3d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}"

def load(tf, win):
    d = rd.bars(tf).reset_index(drop=True)
    c, o = d.close.to_numpy(), d.open.to_numpy()
    lr = pd.Series(np.log(c)).diff()
    z = (lr / lr.rolling(win).std().shift(1)).to_numpy()
    return d, c, o, z

def run(d, c, o, z, thr, k, h0=1, h1=8, cost=0.16, side=-1):
    n = len(d)
    date = d.dt.dt.date
    hour = d.dt.dt.hour.to_numpy()
    slot = (d.dt.dt.hour * 60 + d.dt.dt.minute).to_numpy()
    year = d.dt.dt.year.to_numpy()
    fwd = np.full(n, np.nan)
    fwd[:n - k - 1] = (o[1 + k:] - o[1:n - k]) / c[:n - k - 1] * 1e4
    fwd[~(date.shift(-k - 1) == date).to_numpy()] = np.nan
    base = pd.Series(fwd).groupby([year, slot]).transform("mean").to_numpy()
    ok = (side * z >= thr) & (hour >= h0) & (hour <= h1) & ~np.isnan(fwd)
    idx, nxt = [], -1
    for i in np.flatnonzero(ok):
        if i >= nxt: idx.append(i); nxt = i + k + 1
    i = np.array(idx, dtype=int)
    return pd.DataFrame({"i": i, "dt": d.dt.iloc[i].to_numpy(), "net": fwd[i] - cost / c[i] * 1e4, "ex": fwd[i] - base[i]})

d, c, o, z = load("M15", 96)
cut = d.dt.iloc[int(len(d) * 0.6)]
print("M15 buy after z<=-thr in 01-08, net 0.16: train | test || excess train | test")
for thr in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
    for k in (1, 2, 4, 8, 16):
        t = run(d, c, o, z, thr, k)
        a, b = t.dt < cut, t.dt >= cut
        print(f"  thr {thr} k {k:2d}: {st(t.net[a])} | {st(t.net[b])} || {st(t.ex[a])} | {st(t.ex[b])}")

t = run(d, c, o, z, 3.0, 4)
print("\nthr 3 k 4 by year:", {k: st(v) for k, v in t.net.groupby(t.dt.dt.year)})
print("by hour:", {k: st(v) for k, v in t.net.groupby(t.dt.dt.hour)})
s = t.net.sort_values()
print("without 5 best:", st(s.iloc[:-5]), "| without 10 best:", st(s.iloc[:-10]), "| median", round(s.median(), 1), "| win %", round(100 * (s > 0).mean()), "| worst", round(s.iloc[0]), "best", round(s.iloc[-1]))
print("cost 0.30:", st(run(d, c, o, z, 3.0, 4, cost=0.30).net), "| cost 0.50:", st(run(d, c, o, z, 3.0, 4, cost=0.50).net))
print("mirror (sell after up shock):", st(-run(d, c, o, z, 3.0, 4, side=1).net - 2 * 0.16 / 3000 * 1e4))
for nm, (h0, h1) in {"09-14": (9, 14), "15-19": (15, 19), "20-22": (20, 22)}.items():
    tt = run(d, c, o, z, 3.0, 4, h0, h1)
    print(f"dip buy in hours {nm}: {st(tt.net[tt.dt < cut])} | {st(tt.net[tt.dt >= cut])}")
print("\nvol window sensitivity (thr 3 k 4): train | test")
for win in (48, 96, 192, 480, 960):
    dd, cc, oo, zz = load("M15", win)
    tt = run(dd, cc, oo, zz, 3.0, 4)
    print(f"  win {win}: {st(tt.net[tt.dt < cut])} | {st(tt.net[tt.dt >= cut])}")
print("\nabsolute-size rule instead of z (bar return <= -x bp): train | test")
lrbp = np.log(c / np.roll(c, 1)) * 1e4
for x in (15, 20, 30, 40):
    tt = run(d, c, o, -lrbp / x, 1.0, 4, side=1)
    print(f"  drop >= {x} bp: {st(tt.net[tt.dt < cut])} | {st(tt.net[tt.dt >= cut])}")

d5, c5, o5, z5 = load("M5", 288)
cut5 = d5.dt.iloc[int(len(d5) * 0.6)]
print("\nM5 replication (from 2025-05): first 60% | last 40%")
for thr in (3.0, 4.0, 5.0):
    for k in (3, 6, 12, 24):
        tt = run(d5, c5, o5, z5, thr, k)
        print(f"  thr {thr} k {k:2d}: {st(tt.net[tt.dt < cut5])} | {st(tt.net[tt.dt >= cut5])} || excess all {st(tt.ex)}")

eq = t.set_index("dt").net.resample("D").sum(); eq = eq[eq.index.dayofweek < 5]
cum = eq.cumsum()
print(f"\nequity thr 3 k 4: {cum.iloc[-1]:.0f} bp in {len(eq) / 252:.1f} y, {len(t) / (len(eq) / 252):.0f} trades/yr, Sharpe {eq.mean() / eq.std() * np.sqrt(252):.2f}, maxDD {(cum.cummax() - cum).max():.0f} bp")
