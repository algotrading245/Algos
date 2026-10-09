"""Asian-session shock fade: after an extreme M15 bar between 01:00 and 08:59 server time, trade against it at the next
bar open and hold k bars. Robustness: thresholds, holds, long/short, by year, hour, excluding the open bar, M5 check,
random-entry benchmark at the same hours."""
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

def setup(tf, per_day):
    d = rd.bars(tf).reset_index(drop=True)
    c, o = d.close.to_numpy(), d.open.to_numpy()
    lr = pd.Series(np.log(c)).diff()
    vol = lr.rolling(per_day).std().shift(1)
    d["z"] = (lr / vol).to_numpy()
    d["date"] = d.dt.dt.date
    d["hour"] = d.dt.dt.hour
    return d, c, o

def fade(d, c, o, thr, k, h0=1, h1=8, skip_first=False, cost=COST):
    z = d.z.to_numpy()
    ok = (np.abs(z) >= thr) & (d.hour.to_numpy() >= h0) & (d.hour.to_numpy() <= h1)
    ok &= (d.date.shift(-k - 1) == d.date).to_numpy()
    if skip_first: ok &= (d.date.shift(1) == d.date).to_numpy()
    ok[-k - 2:] = False
    idx, nxt = [], -1
    for i in np.flatnonzero(ok):
        if i >= nxt: idx.append(i); nxt = i + k + 1          # one position at a time
    i = np.array(idx)
    side = -np.sign(z[i])
    bp = (side * (o[i + 1 + k] - o[i + 1]) - cost) / c[i] * 1e4
    return pd.DataFrame({"i": i, "side": side, "bp": bp, "dt": d.dt.iloc[i].to_numpy(), "z": z[i]})

d, c, o = setup("M15", 96)
cut = d.dt.iloc[int(len(d) * 0.6)]
print("M15 fade, bp net of 0.16: train | test | long | short")
for thr in (2.5, 3.0, 3.5, 4.0):
    for k in (2, 4, 6, 8, 12):
        t = fade(d, c, o, thr, k)
        print(f"  thr {thr} k {k:2d}: {st(t.bp[t.dt < cut])} | {st(t.bp[t.dt >= cut])} | L {st(t.bp[t.side > 0])} | S {st(t.bp[t.side < 0])}")

t = fade(d, c, o, 3.0, 4)
print("\nthr 3 k 4 by year:", {k: st(v) for k, v in t.bp.groupby(t.dt.dt.year)})
print("by hour of signal bar:", {k: st(v) for k, v in t.bp.groupby(t.dt.dt.hour)})
print("excluding the first bar of the day:", st(fade(d, c, o, 3.0, 4, skip_first=True).bp))
print("hours 02-08 only:", st(fade(d, c, o, 3.0, 4, h0=2).bp), "| hours 03-08:", st(fade(d, c, o, 3.0, 4, h0=3).bp))
print("cost 0.30:", st(fade(d, c, o, 3.0, 4, cost=0.30).bp), "| win %", round(100 * (t.bp > 0).mean()), "| worst", round(t.bp.min()), "best", round(t.bp.max()))
print("without the 5 best trades:", st(t.bp.sort_values().iloc[:-5]))
# bar-size in bp of the signal bars
sig = (np.abs(np.log(c[t.i] / c[t.i - 1])) * 1e4)
print("signal bar size bp: median", round(np.median(sig), 1), "| pnl by size tercile:", {str(k): st(v) for k, v in t.bp.groupby(pd.qcut(sig, 3, labels=["small", "mid", "big"]), observed=True)})

# benchmark: random side at the same bars (is it the fade or the time of day?) and always-long at the same bars
longp = ((o[t.i + 5] - o[t.i + 1]) - COST) / c[t.i] * 1e4
print("always long at the same bars:", st(longp), "| always short:", st(-longp - 2 * COST / c[t.i] * 1e4))

# other sessions with the same rule, for contrast
for name, (h0, h1) in {"09-14": (9, 14), "15-19": (15, 19), "20-22": (20, 22)}.items():
    tt = fade(d, c, o, 3.0, 4, h0, h1)
    print(f"contrast hours {name}: {st(tt.bp[tt.dt < cut])} | {st(tt.bp[tt.dt >= cut])}")

# M5 version (shorter history, independent bar construction): extreme M5 bar, hold 6/12/24 M5 bars
d5, c5, o5 = setup("M5", 288)
cut5 = d5.dt.iloc[int(len(d5) * 0.6)]
print("\nM5 fade in hours 01-08: first 60% | last 40%")
for thr in (3.0, 4.0, 5.0):
    for k in (3, 6, 12, 24):
        t5 = fade(d5, c5, o5, thr, k)
        print(f"  thr {thr} k {k:2d}: {st(t5.bp[t5.dt < cut5])} | {st(t5.bp[t5.dt >= cut5])} | L {st(t5.bp[t5.side > 0])} | S {st(t5.bp[t5.side < 0])}")

# equity of thr 3 k 4 on M15
eq = t.set_index("dt").bp.resample("D").sum(); eq = eq[eq.index.dayofweek < 5]
cum = eq.cumsum()
print(f"\nequity thr 3 k 4: total {cum.iloc[-1]:.0f} bp over {len(eq) / 252:.1f} y, {len(t) / (len(eq) / 252):.0f} trades/yr, Sharpe {eq.mean() / eq.std() * np.sqrt(252):.2f}, maxDD {(cum.cummax() - cum).max():.0f} bp")
