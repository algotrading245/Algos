"""Long after a volatility shock: after an extreme M15 bar (either direction), buy at the next open and hold k bars.
Compared with the unconditional long return of the same hour-of-day slots (so the session drift is removed)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

COST = 0.16
def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 5: return f"n={len(x)}"
    return f"n={len(x):4d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}"

d = rd.bars("M15").reset_index(drop=True)
c, o = d.close.to_numpy(), d.open.to_numpy()
lr = pd.Series(np.log(c)).diff()
z = (lr / lr.rolling(96).std().shift(1)).to_numpy()
d["date"] = d.dt.dt.date
hour = d.dt.dt.hour.to_numpy()
slot = (d.dt.dt.hour * 4 + d.dt.dt.minute // 15).to_numpy()
year = d.dt.dt.year.to_numpy()
n = len(d); cut = int(n * 0.6)

def run(thr, k, h0, h1, sign=0):
    fwd = np.full(n, np.nan)
    fwd[:n - k - 1] = (o[1 + k:] - o[1:n - k]) / c[:n - k - 1] * 1e4
    same = (d.date.shift(-k - 1) == d.date).to_numpy()
    fwd[~same] = np.nan
    base = pd.Series(fwd).groupby([year, slot]).transform("mean").to_numpy()      # same year, same slot
    ok = (np.abs(z) >= thr) & (hour >= h0) & (hour <= h1) & ~np.isnan(fwd)
    if sign: ok &= np.sign(z) == sign
    idx, nxt = [], -1
    for i in np.flatnonzero(ok):
        if i >= nxt: idx.append(i); nxt = i + k + 1
    i = np.array(idx, dtype=int)
    net = fwd[i] - COST / c[i] * 1e4
    return i, net, fwd[i] - base[i]

print("long after |z|>=thr bar, bp: net train | net test | excess over same-year same-slot mean (gross) train | test")
for name, (h0, h1) in {"asia 01-08": (1, 8), "london 09-14": (9, 14), "ny 15-19": (15, 19), "late 20-22": (20, 22), "all": (1, 22)}.items():
    for thr in (2.0, 3.0, 4.0):
        for k in (4, 8):
            i, net, ex = run(thr, k, h0, h1)
            tr, te = i < cut, i >= cut
            print(f"  {name:13s} thr {thr} k {k}: {st(net[tr])} | {st(net[te])} || {st(ex[tr])} | {st(ex[te])}")

print("\nasia thr 3 k 4 split by direction of the shock bar (net): train | test")
for sg, nm in ((1, "after up bar"), (-1, "after down bar")):
    i, net, ex = run(3.0, 4, 1, 8, sg)
    print(f"  {nm:15s} {st(net[i < cut])} | {st(net[i >= cut])} || excess {st(ex[i < cut])} | {st(ex[i >= cut])}")
i, net, ex = run(3.0, 4, 1, 8)
print("  by year net:", {int(k): st(v) for k, v in pd.Series(net).groupby(year[i])})
print("  by year excess:", {int(k): st(v) for k, v in pd.Series(ex).groupby(year[i])})
s = pd.Series(net).sort_values()
print("  without 5 best:", st(s.iloc[:-5]), "| win %", round(100 * (net > 0).mean()), "| worst", round(s.iloc[0]), "| best", round(s.iloc[-1]))
