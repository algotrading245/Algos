"""Auction dip (short 12:20 -> 12:35 server): by month, weekday, DST-mismatch weeks, outliers, conditioning on the
morning move, real bid/ask on ticks, and stop behaviour on M1/M5 highs."""
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

d = rd.bars("M5").reset_index(drop=True)
d["date"] = pd.to_datetime(d.dt.dt.date); d["hm"] = d.dt.dt.strftime("%H:%M")
po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
ph = d.pivot_table(index="date", columns="hm", values="high", aggfunc="first")
x = ((po["12:20"] - po["12:35"] - COST) / po["12:20"] * 1e4).dropna()
print("M5 short 12:20->12:35 net 0.16 by month:")
print("  " + " ".join(f"{k[0] % 100}-{k[1]:02d}:{v.mean():+.1f}({100 * (v > 0).mean():.0f}%)" for k, v in x.groupby([x.index.year, x.index.month])))
print("  by weekday:", {("Mon", "Tue", "Wed", "Thu", "Fri")[k]: st(v) for k, v in x.groupby(x.index.dayofweek)})
s = x.sort_values()
print("  without 10 best:", st(s.iloc[:-10]), "| without 30 best:", st(s.iloc[:-30]), "| median", round(s.median(), 2), "| worst", round(s.iloc[0], 1), "best", round(s.iloc[-1], 1))
print("  cost 0.30:", st(x - 0.14 / po["12:20"].reindex(x.index) * 1e4), "| cost 0.50:", st(x - 0.34 / po["12:20"].reindex(x.index) * 1e4))
# DST mismatch: 2025-10-26..2025-11-01 (EU off, US on) and 2026-03-08..2026-03-28 (US on, EU off)
mis = ((x.index >= "2025-10-26") & (x.index <= "2025-11-01")) | ((x.index >= "2026-03-08") & (x.index <= "2026-03-28"))
print(f"  DST-mismatch days n={mis.sum()}: gross short per slot start (15 min):")
for a, b in (("11:20", "11:35"), ("12:20", "12:35"), ("13:20", "13:35")):
    y = ((po[a] - po[b]) / po[a] * 1e4).reindex(x.index)
    print(f"    {a}: mismatch {st(y[mis])} | other {st(y[~mis])}")
# conditioning on the move since the daily open and over the previous hour
am = ((po["12:20"] / po["01:00"] - 1) * 1e4).reindex(x.index)
h1 = ((po["12:20"] / po["11:20"] - 1) * 1e4).reindex(x.index)
print("  by morning move 01:00->12:20 tercile:", {str(k): st(v) for k, v in x.groupby(pd.qcut(am, 3), observed=True)})
print("  by last hour move tercile:", {str(k): st(v) for k, v in x.groupby(pd.qcut(h1, 3), observed=True)})
# stop on bar highs (short): stop x bp above entry
hi = ph[["12:20", "12:25", "12:30"]].max(axis=1).reindex(x.index)
adv = (hi / po["12:20"].reindex(x.index) - 1) * 1e4
print("  max adverse move (bp) quantiles 50/90/99/max:", np.round(np.quantile(adv.dropna(), [.5, .9, .99, 1]), 1))
for sb in (10, 15, 20, 30):
    y = x.where(adv < sb, -sb - COST / po["12:20"].reindex(x.index) * 1e4)
    print(f"    stop {sb} bp: {st(y)} worst {y.min():.1f}")
eq = x.cumsum()
print(f"  cumulative {eq.iloc[-1]:.0f} bp over {len(x)} days; maxDD {(eq.cummax() - eq).max():.0f} bp; daily Sharpe {x.mean() / x.std() * np.sqrt(252):.2f}")

# ticks: real bid/ask
print("\nticks: sell at bid at 12:20:00, buy back at ask at 12:35:00")
rows = []
for p in rd.tick_days():
    ms, bid, ask = rd.ticks(p)
    t = pd.DataFrame({"bid": bid, "ask": ask}, index=pd.to_datetime(ms, unit="ms")).sort_index()
    day = t.index[0].normalize()
    def at(hm):
        w = t.loc[day + pd.Timedelta(hm):day + pd.Timedelta(hm) + pd.Timedelta("60s")]
        return (w.bid.iloc[0], w.ask.iloc[0]) if len(w) else (np.nan, np.nan)
    for a, b in (("12:20:00", "12:35:00"), ("12:15:00", "12:32:00"), ("12:25:00", "12:32:00")):
        (b0, a0), (b1, a1) = at(a), at(b)
        rows.append((day.date(), a + ">" + b, b0, a1, a0 - b0, a1 - b1, (b0 - a1) / b0 * 1e4))
r = pd.DataFrame(rows, columns=["day", "leg", "sell", "buy", "sp_in", "sp_out", "net_bp"]).dropna()
for leg, g in r.groupby("leg"):
    print(f"  {leg}: {st(g.net_bp)} | win {100 * (g.net_bp > 0).mean():.0f}% | spread in {g.sp_in.mean():.2f} out {g.sp_out.mean():.2f} | " + " ".join(f"{v:+.0f}" for v in g.net_bp))
