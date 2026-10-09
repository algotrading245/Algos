"""(1) Noise-area intraday momentum (Zarattini, Aziz, Barbon 2024) on gold M15, two session anchors.
(2) Session-open drift equity in bp. (3) Daily trend with volatility targeting versus buy and hold."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

COST = 0.16
d = rd.bars("M15").reset_index(drop=True)
d["date"] = d.dt.dt.date
d["hm"] = d.dt.dt.strftime("%H:%M")
po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
pc = d.pivot_table(index="date", columns="hm", values="close", aggfunc="first")
hms = list(po.columns)
half = po.index[int(len(po) * 0.6)]

def st(x, ann=252):
    x = x.dropna()
    return f"n={len(x):4d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f} Sh {x.mean() / x.std() * np.sqrt(ann):+.2f}"

def noise(anchor, end, look=14, mult=1.0, check=2, flip=True):
    a, e = hms.index(anchor), hms.index(end)
    o0 = po[anchor]
    move = pc.iloc[:, a:e].sub(o0, axis=0).abs().div(o0, axis=0)        # |move from anchor| at each bar close
    sig = move.rolling(look).mean().shift(1) * mult                     # only earlier days
    up = (o0.to_numpy()[:, None]) * (1 + sig.to_numpy())
    dn = (o0.to_numpy()[:, None]) * (1 - sig.to_numpy())
    C = pc.iloc[:, a:e].to_numpy(); O = po.iloc[:, a:e + 1].to_numpy()
    res = np.full(len(po), np.nan); ntr = np.zeros(len(po))
    for i in range(len(po)):
        if np.isnan(up[i]).any() or np.isnan(C[i]).any() or np.isnan(O[i]).any(): continue
        pos, ep, pnl = 0, 0.0, 0.0
        for j in range(check - 1, C.shape[1] - 1, check):
            want = pos
            if C[i, j] > up[i, j]: want = 1
            elif C[i, j] < dn[i, j]: want = -1
            elif pos == 1 and C[i, j] < o0.iloc[i]: want = 0           # back through the anchor: flat
            elif pos == -1 and C[i, j] > o0.iloc[i]: want = 0
            if want != pos:
                px = O[i, j + 1]
                if pos != 0: pnl += pos * (px - ep) - COST; ntr[i] += 1
                pos, ep = want, px
        if pos != 0: pnl += pos * (O[i, -1] - ep) - COST; ntr[i] += 1
        res[i] = pnl / o0.iloc[i] * 1e4
    return pd.Series(res, index=po.index), ntr

print("noise-area intraday momentum, bp per day net of cost: all | train | test | trades/day")
for anchor, end in (("01:00", "23:30"), ("09:00", "23:30"), ("15:30", "23:30"), ("16:30", "23:30")):
    for mult in (1.0, 1.5):
        for check in (2, 4):
            x, ntr = noise(anchor, end, mult=mult, check=check)
            print(f"{anchor}-{end} mult {mult} every {check * 15}m: {st(x)} | {st(x[x.index < half])} | {st(x[x.index >= half])} | {np.nanmean(ntr):.2f}")

print("\nsession-open drift, long, bp per day net of 0.25: all | train | test, maxDD, worst day")
for a, b in (("01:00", "03:00"), ("01:00", "04:00")):
    x = ((po[b] - po[a] - 0.25) / po[a] * 1e4).dropna()
    cum = x.cumsum()
    print(f"{a}->{b}: {st(x)} | {st(x[x.index < half])} | {st(x[x.index >= half])} | total {cum.iloc[-1]:.0f} bp maxDD {(cum.cummax() - cum).max():.0f} bp worst {x.min():.0f} win {100 * (x > 0).mean():.0f}%")
    yr = pd.Series([i.year for i in x.index], index=x.index)
    print("   by year:", {k: st(v) for k, v in x.groupby(yr)})

print("\ndaily trend with volatility targeting (10% annual target, max 2x), close to close, cost 2 bp per unit turnover")
D = rd.bars("D1").reset_index(drop=True)
r = D.close.pct_change()
vol = r.ewm(span=30).std() * np.sqrt(252)
lev = (0.10 / vol).clip(upper=2.0)
def perf(name, sig):
    pos = (sig * lev).shift(1).fillna(0)
    pr = pos * r - pos.diff().abs().fillna(0) * 2e-4
    pr = pr.iloc[260:]
    cum = (1 + pr).cumprod()
    dd = (1 - cum / cum.cummax()).max()
    h = int(len(pr) * 0.6)
    sh = lambda z: z.mean() / z.std() * np.sqrt(252)
    print(f"  {name:28s} CAGR {100 * (cum.iloc[-1] ** (252 / len(pr)) - 1):5.1f}% Sharpe {sh(pr):.2f} (train {sh(pr.iloc[:h]):.2f}, test {sh(pr.iloc[h:]):.2f}) maxDD {100 * dd:.1f}% time in market {100 * (pos.iloc[260:] != 0).mean():.0f}%")
c = D.close
perf("always long (vol target)", pd.Series(1.0, index=D.index))
perf("close > MA50", (c > c.rolling(50).mean()).astype(float))
perf("close > MA100", (c > c.rolling(100).mean()).astype(float))
perf("close > MA200", (c > c.rolling(200).mean()).astype(float))
perf("TSMOM 60d long/short", np.sign(c / c.shift(60) - 1))
perf("TSMOM 120d long/short", np.sign(c / c.shift(120) - 1))
perf("TSMOM 250d long/short", np.sign(c / c.shift(250) - 1))
perf("Donchian 55 long / 20 exit", pd.Series(np.where(c >= c.rolling(55).max(), 1.0, np.where(c <= c.rolling(20).min(), 0.0, np.nan)), index=D.index).ffill().fillna(0))
