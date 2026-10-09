"""Scalping horizon (minutes): (1) M5 time-of-day slot scan, both halves; (2) dip-buy on M5 and M1 with ATR-style and
z definitions, all sessions; (3) the first minutes after the daily open on M1 with open-spread cost."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

COST = 0.16
def tt(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return (x.mean(), x.mean() / x.std() * np.sqrt(len(x)), len(x)) if len(x) > 5 else (np.nan, 0.0, len(x))
def st(x):
    m, t, n = tt(x)
    return f"n={n:4d} {m:+6.2f} t {t:+.1f}"

# ---------- 1. M5 slot scan
d = rd.bars("M5").reset_index(drop=True)
d["date"] = d.dt.dt.date; d["hm"] = d.dt.dt.strftime("%H:%M")
po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
half = po.index[int(len(po) * 0.6)]
cols = list(po.columns)
print(f"1. M5 slots, {len(po)} days from {po.index[0]}; long (or short) from slot open for k bars, gross bp; listed if |t|>=2.5 in both halves, same sign")
found = 0
for k in (1, 2, 3, 6, 12):
    for j in range(len(cols) - k):
        x = (po[cols[j + k]] / po[cols[j]] - 1) * 1e4
        a, b = tt(x[x.index < half]), tt(x[x.index >= half])
        if abs(a[1]) >= 2.5 and abs(b[1]) >= 2.5 and a[0] * b[0] > 0:
            found += 1
            net = abs(x.mean()) - COST / 3500 * 1e4
            print(f"   {cols[j]} +{k * 5:3d} min: train {a[0]:+.2f} (t {a[1]:+.1f}) test {b[0]:+.2f} (t {b[1]:+.1f}) | approx net of 0.16: {net:+.2f}")
print(f"   {found} slots of {5 * len(cols)} tested (chance expectation at |t|>=2.5 twice same sign: {5 * len(cols) * 0.0124 ** 2 / 2:.2f})")

# ---------- 2. dip buy at minute scale
def dip(tf, win, thrs, ks, sessions):
    d = rd.bars(tf).reset_index(drop=True)
    c, o = d.close.to_numpy(), d.open.to_numpy()
    n = len(d); cut = int(n * 0.6)
    lr = pd.Series(np.log(c)).diff()
    z = (lr / lr.rolling(win).std().shift(1)).to_numpy()
    hour = d.dt.dt.hour.to_numpy(); date = d.dt.dt.date
    print(f"2. {tf} from {d.dt.iloc[0].date()}, vol window {win}: buy after z<=-thr, hold k bars, net of 0.16: train | test || mirror (sell after up) all")
    for nm, (h0, h1) in sessions.items():
        for thr in thrs:
            for k in ks:
                f = np.full(n, np.nan)
                f[:n - k - 1] = (o[1 + k:] - o[1:n - k]) / c[:n - k - 1] * 1e4
                f[~(date.shift(-k - 1) == date).to_numpy()] = np.nan
                cb = COST / c * 1e4
                res = []
                for side in (-1, 1):
                    ok = (side * z >= thr) & (hour >= h0) & (hour <= h1) & ~np.isnan(f)
                    idx, nxt = [], -1
                    for i in np.flatnonzero(ok):
                        if i >= nxt: idx.append(i); nxt = i + k + 1
                    res.append(np.array(idx, dtype=int))
                i = res[0]; j = res[1]
                print(f"   {nm:11s} thr {thr} k {k:2d}: {st(f[i[i < cut]] - cb[i[i < cut]])} | {st(f[i[i >= cut]] - cb[i[i >= cut]])} || {st(-f[j] - cb[j])}")
ses = {"asia 01-08": (1, 8), "london 9-14": (9, 14), "ny 15-19": (15, 19), "late 20-22": (20, 22)}
dip("M5", 288, (4.0, 5.0, 6.0), (1, 3, 6, 12), ses)
dip("M1", 1380, (5.0, 7.0), (2, 5, 15, 30), ses)

# ---------- 3. first minutes of the day on M1
d = rd.bars("M1").reset_index(drop=True)
d["date"] = d.dt.dt.date; d["hm"] = d.dt.dt.strftime("%H:%M")
po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
po = po[po["01:00"].notna()]
h = po.index[int(len(po) * 0.6)]
print(f"3. M1 daily open, {len(po)} days from {po.index[0]}: long 01:00 -> t, net of 0.25: all | first 60% | last 40%")
for b in ("01:01", "01:02", "01:03", "01:05", "01:10", "01:15", "01:30", "02:00", "03:00"):
    x = (po[b] - po["01:00"] - 0.25) / po["01:00"] * 1e4
    print(f"   -> {b}: {st(x)} | {st(x[x.index < h])} | {st(x[x.index >= h])}")
d5 = rd.bars("M5").reset_index(drop=True); d5["date"] = d5.dt.dt.date; d5["hm"] = d5.dt.dt.strftime("%H:%M")
p5 = d5.pivot_table(index="date", columns="hm", values="open", aggfunc="first"); p5 = p5[p5["01:00"].notna()]
h5 = p5.index[int(len(p5) * 0.6)]
print(f"   M5, {len(p5)} days from {p5.index[0]}:")
for b in ("01:05", "01:10", "01:15", "01:30", "02:00", "03:00"):
    x = (p5[b] - p5["01:00"] - 0.25) / p5["01:00"] * 1e4
    q = [x[(x.index >= p5.index[int(len(p5) * a)]) & (x.index <= p5.index[min(int(len(p5) * (a + .25)), len(p5) - 1)])].mean() for a in (0, .25, .5, .75)]
    print(f"   -> {b}: {st(x)} | {st(x[x.index < h5])} | {st(x[x.index >= h5])} | quarters " + " ".join(f"{v:+.1f}" for v in q))
