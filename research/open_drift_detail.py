"""(1) where inside the first hours the open drift sits (M5, M1), (2) weekday split by half, (3) session-conditioned
fade/follow of large M15 bars, (4) range-compression breakout on H1."""
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
    return f"n={len(x):5d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}"

def piv(tf):
    d = rd.bars(tf).reset_index(drop=True)
    d["date"] = d.dt.dt.date; d["hm"] = d.dt.dt.strftime("%H:%M")
    return d, d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")

print("(1) open-drift legs, gross bp")
for tf, legs in (("M5", ("01:00", "01:05", "01:10", "01:15", "01:30", "02:00", "03:00", "04:00")),
                 ("M1", ("01:00", "01:01", "01:02", "01:03", "01:05", "01:10", "01:15"))):
    d, po = piv(tf)
    po = po[po["01:00"].notna()]
    h = po.index[int(len(po) * 0.6)]
    print(f"  {tf}: {len(po)} days from {po.index[0]}")
    for a, b in zip(legs[:-1], legs[1:]):
        x = (po[b] / po[a] - 1) * 1e4
        print(f"    {a}->{b}: {st(x)} | first 60% {st(x[x.index < h])} | last 40% {st(x[x.index >= h])}")

d, po = piv("M15")
half = po.index[int(len(po) * 0.6)]
x = ((po["03:00"] - po["01:00"] - 0.25) / po["01:00"] * 1e4).dropna()
dow = pd.Series([i.weekday() for i in x.index], index=x.index)
print("\n(2) drift net 0.25 by weekday: train | test")
for k in range(5):
    y = x[dow == k]
    print(f"   {'Mon Tue Wed Thu Fri'.split()[k]}: {st(y[y.index < half])} | {st(y[y.index >= half])}")
# longer M15 legs: is the whole Asian morning positive?
print("   legs net 0 cost:", {f"{a}->{b}": st((po[b] / po[a] - 1) * 1e4) for a, b in (("01:00", "01:15"), ("01:15", "02:00"), ("02:00", "03:00"), ("03:00", "05:00"), ("05:00", "09:00"))})

# (3) large M15 bars: follow or fade over the next k bars, by session
c, o = d.close.to_numpy(), d.open.to_numpy()
lr = pd.Series(np.log(c)).diff()
vol = lr.rolling(96).std().shift(1)
z = (lr / vol).to_numpy()
hour = d.dt.dt.hour.to_numpy()
n = len(d); cut = int(n * 0.6)
same_day = lambda k: (d.date.shift(-k - 1) == d.date).to_numpy()
print("\n(3) after a |z|>=thr M15 bar, FOLLOW for k bars, bp net of 0.16 (fade = minus this minus 2 x cost): train | test")
sessions = {"asia 01-08": (1, 8), "london 09-14": (9, 14), "ny 15-19": (15, 19), "late 20-22": (20, 22)}
for name, (h0, h1) in sessions.items():
    for thr in (2.0, 3.0):
        for k in (1, 4, 8):
            fwd = (np.roll(o, -k - 1) - np.roll(o, -1))
            ok = (np.abs(z) >= thr) & (hour >= h0) & (hour <= h1) & same_day(k)
            ok[-k - 2:] = False
            pnl = (np.sign(z) * fwd - COST) / c * 1e4
            i = np.flatnonzero(ok)
            costbp = COST / c * 1e4
            tr, te = i[i < cut], i[i >= cut]
            fade = lambda j: -pnl[j] - 2 * costbp[j]
            print(f"   {name:13s} thr {thr} k {k}: follow {st(pnl[tr])} | {st(pnl[te])}   fade {st(fade(tr))} | {st(fade(te))}")

# (4) H1 range compression then breakout
h = rd.bars("H1").reset_index(drop=True)
hc, ho, hh, hl = (h[k].to_numpy() for k in ("close", "open", "high", "low"))
atr = pd.Series(hh - hl).rolling(24).mean()
ratio = (atr / atr.rolling(240).mean()).shift(1).to_numpy()
hi = pd.Series(hh).rolling(12).max().shift(1).to_numpy(); lo = pd.Series(hl).rolling(12).min().shift(1).to_numpy()
hcut = int(len(h) * 0.6)
print("\n(4) H1: close breaks the 12-bar range while ATR24/ATR240 < q; follow for k bars, bp net: train | test")
for q in (0.7, 0.85, 1.0, 9.9):
    for k in (4, 12, 24):
        side = np.where(hc > hi, 1, np.where(hc < lo, -1, 0))
        ok = (side != 0) & (ratio < q); ok[-k - 2:] = False
        i = np.flatnonzero(ok)
        # non-overlapping
        keep, nxt = [], -1
        for j in i:
            if j >= nxt: keep.append(j); nxt = j + k
        i = np.array(keep)
        pnl = (side[i] * (ho[i + 1 + k] - ho[i + 1]) - COST) / hc[i] * 1e4
        lg = side[i] > 0
        print(f"   q<{q} k {k:2d}: {st(pnl[i < hcut])} | {st(pnl[i >= hcut])}   long {st(pnl[lg])} short {st(pnl[~lg])}")
