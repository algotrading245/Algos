"""(a) what the bar 'spread' column means and how wide the open was historically, (b) session-open drift with the
recorded open spread as cost, (c) hour-of-day profile, (d) daily trend with swap, (e) drift conditioned on the gap."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

def st(x):
    x = x.dropna()
    return f"n={len(x):4d} {x.mean():+6.2f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f}"

# (a) spread column vs ticks
m1 = rd.bars("M1").reset_index(drop=True)
m1i = m1.set_index("time")
print("(a) M1 bar spread column vs ticks in that minute: col | first-tick | min | median")
k = 0
for p in rd.tick_days():
    t, b, a = rd.ticks(p)
    sec = t // 1000
    for minute in (sec[0] // 60 * 60, sec[0] // 60 * 60 + 3600 * 8):
        mk = (sec >= minute) & (sec < minute + 60)
        if mk.sum() and minute in m1i.index:
            s = (a - b)[mk]
            print(f"   {pd.to_datetime(minute, unit='s')} col {m1i.spread.loc[minute]:.0f} first {100 * s[0]:.0f} min {100 * s.min():.0f} med {100 * np.median(s):.0f}")
    k += 1
    if k >= 5: break

d = rd.bars("M15").reset_index(drop=True)
d["date"] = d.dt.dt.date
d["hm"] = d.dt.dt.strftime("%H:%M")
first = d.groupby("date").first()
first = first[first.hm == "01:00"]
yr = pd.Series([i.year for i in first.index], index=first.index)
print("\n(b) spread column (points) of the 01:00 M15 bar by year: median / p90 / max")
print(first.spread.groupby(yr).agg(["median", lambda x: x.quantile(.9), "max"]).to_string())
allsp = d.spread.groupby(d.dt.dt.year).median()
print("    all-bars median by year:", allsp.to_dict())

po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
sp0 = first.spread.reindex(po.index) * 0.01
half = po.index[int(len(po) * 0.6)]
print("\n    drift 01:00->03:00, bp/day, cost = recorded open spread + 0.10: all | train | test")
for extra in (0.10, 0.20):
    x = ((po["03:00"] - po["01:00"] - sp0 - extra) / po["01:00"] * 1e4).dropna()
    print(f"    extra {extra}: {st(x)} | {st(x[x.index < half])} | {st(x[x.index >= half])}")
    print("       by year:", {k: st(v) for k, v in x.groupby(pd.Series([i.year for i in x.index], index=x.index))})

# (c) hour-of-day profile on H1, open to next open, in bp, gross
h = rd.bars("H1").reset_index(drop=True)
h["r"] = (h.open.shift(-1) / h.open - 1) * 1e4
h.loc[h.dt.shift(-1) - h.dt != pd.Timedelta(hours=1), "r"] = np.nan
cut = h.dt.iloc[int(len(h) * 0.6)]
print("\n(c) hour-of-day mean return bp (gross): all | train | test")
for hr, g in h.groupby(h.dt.dt.hour):
    print(f"   {hr:02d}: {st(g.r)} | {st(g.r[g.dt < cut])} | {st(g.r[g.dt >= cut])}")

# (d) daily trend with swap
D = rd.bars("D1").reset_index(drop=True)
c = D.close; r = c.pct_change()
vol = r.ewm(span=30).std() * np.sqrt(252)
lev = (0.10 / vol).clip(upper=2.0)
nights = np.where(D.dt.dt.dayofweek == 2, 3, 1)             # triple swap on Wednesday
swap_long = 0.7744 / c * nights; swap_short = 0.367 / c * nights
def perf(name, sig, cap=2.0, tgt=0.10):
    lv = (tgt / vol).clip(upper=cap)
    pos = (sig * lv).shift(1).fillna(0)
    sw = np.where(pos > 0, -pos * swap_long, -pos * swap_short)     # short positions earn
    pr = (pos * r - pos.diff().abs().fillna(0) * 2e-4 + sw).iloc[260:]
    cum = (1 + pr).cumprod(); dd = (1 - cum / cum.cummax()).max()
    k = int(len(pr) * 0.6); sh = lambda z: z.mean() / z.std() * np.sqrt(252)
    print(f"   {name:30s} CAGR {100 * (cum.iloc[-1] ** (252 / len(pr)) - 1):5.1f}% Sharpe {sh(pr):.2f} (train {sh(pr.iloc[:k]):.2f}, test {sh(pr.iloc[k:]):.2f}) maxDD {100 * dd:.1f}% swap/yr {100 * pd.Series(sw).iloc[260:].mean() * 252:+.1f}%")
print("\n(d) daily trend, 10% vol target, max 2x, with swap")
one = pd.Series(1.0, index=D.index)
perf("always long", one)
for n in (20, 50, 100, 200):
    perf(f"close > MA{n}", (c > c.rolling(n).mean()).astype(float))
perf("MA50 long / short", np.sign(c - c.rolling(50).mean()))
perf("Donchian 55/20", pd.Series(np.where(c >= c.rolling(55).max(), 1.0, np.where(c <= c.rolling(20).min(), 0.0, np.nan)), index=D.index).ffill().fillna(0))
perf("close > MA50, 15% target 3x", (c > c.rolling(50).mean()).astype(float), cap=3.0, tgt=0.15)

# (e) drift conditioned on the gap and the previous day
last = d.groupby("date").last()
prev_close = last.close.shift(1).reindex(po.index)
prev_open = po["01:00"].shift(1)
x = ((po["03:00"] - po["01:00"] - 0.25) / po["01:00"] * 1e4)
gap = (po["01:00"] - prev_close) / prev_close * 1e4
pday = (prev_close - prev_open) / prev_open * 1e4
print("\n(e) drift 01:00->03:00 net 0.25 by condition: all | train | test")
for name, m in (("gap up", gap > 0), ("gap down", gap < 0), ("gap > +2bp", gap > 2), ("gap < -2bp", gap < -2),
                ("prev day up", pday > 0), ("prev day down", pday < 0)):
    y = x[m]
    print(f"   {name:14s} {st(y)} | {st(y[y.index < half])} | {st(y[y.index >= half])}")
print("   gap stats bp:", st(gap), " corr(gap, drift)", round(gap.corr(x), 3))
dow = pd.Series([i.weekday() for i in x.index], index=x.index)
print("   by weekday:", {k: st(v) for k, v in x.groupby(dow)})

