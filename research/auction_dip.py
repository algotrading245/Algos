"""LBMA auction drift: gold falls into the 10:30 London AM auction (12:30 server). Check on M15 since 2022 by year,
weekday, the PM auction (15:00 London = 17:00 server), M5 leg detail, M1 minute path, and a short trade net of cost."""
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

def piv(tf):
    d = rd.bars(tf).reset_index(drop=True)
    d["date"] = pd.to_datetime(d.dt.dt.date); d["hm"] = d.dt.dt.strftime("%H:%M")
    return d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")

p15 = piv("M15")
print(f"M15 {len(p15)} days from {p15.index[0].date()}: SHORT a -> b, net of 0.16 bp")
def short(p, a, b, cost=COST):
    return ((p[a] - p[b] - cost) / p[a] * 1e4).dropna()
for a, b in (("12:00", "12:15"), ("12:15", "12:30"), ("12:30", "12:45"), ("12:15", "12:45"), ("12:00", "12:45"), ("12:45", "13:00"),
             ("16:30", "16:45"), ("16:45", "17:00"), ("17:00", "17:15"), ("16:45", "17:15")):
    x = short(p15, a, b)
    h = x.index[int(len(x) * 0.6)]
    print(f"  {a}->{b}: all {st(x)} | train {st(x[x.index < h])} | test {st(x[x.index >= h])} | by year " +
          " ".join(f"{y}:{v.mean():+.1f}" for y, v in x.groupby(x.index.year)))
x = short(p15, "12:15", "12:45")
print("  12:15->12:45 by weekday:", {("Mon", "Tue", "Wed", "Thu", "Fri")[k]: st(v) for k, v in x.groupby(x.index.dayofweek)})
print("  by half-year:", " ".join(f"{k}:{v.mean():+.1f}(t{v.mean() / v.std() * np.sqrt(len(v)):+.1f})" for k, v in x.groupby([x.index.year, (x.index.month > 6).astype(int)])))
# DST mismatch: weeks where US and EU DST differ (mid-Mar..end-Mar, last week Oct) - does the slot move?
m = x.index.month; dd = x.index.day
mis = ((m == 3) & (dd >= 8) & (dd <= 31)) | ((m == 10) & (dd >= 25)) | ((m == 11) & (dd <= 7))
print("  DST-mismatch weeks:", st(x[mis]), "| other:", st(x[~mis]))
for a, b in (("11:15", "11:45"), ("13:15", "13:45")):
    y = short(p15, a, b)
    print(f"  mismatch weeks, slot {a}->{b}: {st(y[mis[:len(y)]] if len(y) == len(x) else y)}")
s = x.sort_values()
print("  without 10 best:", st(s.iloc[:-10]), "| without 20 best:", st(s.iloc[:-20]), "| median", round(s.median(), 2), "| win %", round(100 * (s > 0).mean()))
# same slot baseline: all other 30-min slots between 09:00 and 20:00
cols = [c for c in p15.columns if "09:00" <= c <= "20:00"]
ts = []
for j in range(len(cols) - 2):
    y = ((p15[cols[j]] - p15[cols[j + 2]]) / p15[cols[j]] * 1e4).dropna()
    ts.append((cols[j], y.mean(), y.mean() / y.std() * np.sqrt(len(y))))
ts = pd.DataFrame(ts, columns=["slot", "gross", "t"]).sort_values("t")
print("  all 30-min short slots 09-20, gross: most extreme t:", ts.tail(3).to_string(index=False, header=False).replace("\n", " ; "), "| lowest:", ts.head(2).to_string(index=False, header=False).replace("\n", " ; "))

p5 = piv("M5")
print(f"\nM5 {len(p5)} days from {p5.index[0].date()}: gross SHORT per 5-min bar around the auction")
cs = [c for c in p5.columns if "11:45" <= c <= "13:10"]
for j in range(len(cs) - 1):
    y = ((p5[cs[j]] - p5[cs[j + 1]]) / p5[cs[j]] * 1e4).dropna()
    print(f"  {cs[j]}: {st(y)}")
for a, b in (("12:20", "12:35"), ("12:15", "12:35"), ("12:20", "12:40"), ("12:25", "12:35"), ("12:10", "12:40")):
    y = short(p5, a, b); h = y.index[int(len(y) * 0.6)]
    q = [y.iloc[int(len(y) * f):int(len(y) * (f + .25))].mean() for f in (0, .25, .5, .75)]
    print(f"  net {a}->{b}: all {st(y)} | train {st(y[y.index < h])} | test {st(y[y.index >= h])} | quarters " + " ".join(f"{v:+.1f}" for v in q) + f" | win {100 * (y > 0).mean():.0f}%")

p1 = piv("M1")
print(f"\nM1 {len(p1)} days from {p1.index[0].date()}: mean cumulative gross move from 12:15 (bp), every minute")
cs = [c for c in p1.columns if "12:15" <= c <= "12:50"]
base = p1["12:15"]
print("  " + " ".join(f"{c[3:]}:{((p1[c] / base - 1) * 1e4).mean():+.1f}" for c in cs))
