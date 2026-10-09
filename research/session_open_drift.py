"""Session-open drift: where inside the first hour, what conditions it, and how it compares to any other window."""
import sys
import numpy as np
import pandas as pd
import realdata as rd

def stat(r):
    r = r.dropna()
    return f"n={len(r):4d} mean {r.mean():+.3f} t {r.mean() / r.std() * np.sqrt(len(r)):+.1f} win {100 * (r > 0).mean():.0f}%"

# fine structure: M5 (17 months) and M1 (3.5 months), price units per oz
for tf, mins in (("M5", 5), ("M1", 1)):
    d = rd.bars(tf)
    d["date"] = d.dt.dt.date
    d["k"] = (d.time % 86400 - 3600) // (mins * 60)
    d["ret"] = d.close - d.open
    print(f"\n{tf}: bar open->close per oz by bar number after 01:00 ({d.date.nunique()} days)")
    for k in list(range(0, 12)) + ([15, 30, 45, 59] if mins == 1 else []):
        print(f"  +{k * mins:3d} min: {stat(d[d.k == k].ret)}  spread med {d[d.k == k].spread.median():.2f}")
    po = d.pivot_table(index="date", columns="k", values="open", aggfunc="first")
    pc = d.pivot_table(index="date", columns="k", values="close", aggfunc="first")
    for a, b_ in ((0, 15), (0, 45), (0, 60), (1, 45), (2, 45), (5, 45), (5, 60), (15, 60)):
        ka, kb = a // mins, b_ // mins - 1
        if a % mins == 0:
            print(f"  long {a:2d}->{b_:2d} min: {stat(pc[kb] - po[ka])}")

# conditioning on M15 over 4 years
d = rd.bars("M15")
d["date"] = d.dt.dt.date
d["hm"] = d.dt.dt.strftime("%H:%M")
po = d.pivot_table(index="date", columns="hm", values="open", aggfunc="first")
pc = d.pivot_table(index="date", columns="hm", values="close", aggfunc="first")
day = d.groupby("date").agg(o=("open", "first"), c=("close", "last"), h=("high", "max"), l=("low", "min"))
r = (pc["01:45"] - po["01:00"]) / po["01:00"] * 1e4
prev = ((day.c - day.o) / day.o * 1e4).shift()
gap = (day.o - day.c.shift()) / day.c.shift() * 1e4
prev5 = (day.c.shift() / day.c.shift(6) - 1) * 1e4
late = ((pc["23:45"] - po["20:00"]) / po["20:00"] * 1e4).shift()
print("\n01:00->01:45 long in bp, conditioned (4 years)")
print("  all            ", stat(r))
print("  prev day up    ", stat(r[prev > 0]), "| down", stat(r[prev < 0]))
print("  prev 5d up     ", stat(r[prev5 > 0]), "| down", stat(r[prev5 < 0]))
print("  gap up         ", stat(r[gap > 0]), "| down", stat(r[gap < 0]))
print("  late-NY up     ", stat(r[late > 0]), "| down", stat(r[late < 0]))
print("  |prev| big     ", stat(r[prev.abs() > prev.abs().median()]), "| small", stat(r[prev.abs() <= prev.abs().median()]))
# every other 45-minute window, for scale
allw = []
cols = list(po.columns)
for i in range(len(cols) - 2):
    x = ((pc[cols[i + 2]] - po[cols[i]]) / po[cols[i]] * 1e4).dropna()
    allw.append((cols[i], x.mean(), x.mean() / x.std() * np.sqrt(len(x))))
allw = pd.DataFrame(allw, columns=["start", "mean", "t"])
print("\nall 45-min windows: mean of means %.2f bp, sd of t %.2f; top 5 by |t|:" % (allw["mean"].mean(), allw.t.std()))
print(allw.reindex(allw.t.abs().sort_values(ascending=False).index).head(6).round(2).to_string(index=False))
# equity of the plain rule, in price units, net of cost
cost = 0.25
net = (pc["01:45"] - po["01:00"]).dropna() - cost
yr = pd.Series([x.year for x in net.index], index=net.index)
print("\nplain rule net of %.2f per oz, per trade, by year:" % cost)
print(pd.DataFrame({"n": net.groupby(yr).size(), "mean": net.groupby(yr).mean().round(2), "sum": net.groupby(yr).sum().round(1),
                    "sd": net.groupby(yr).std().round(2), "worst": net.groupby(yr).min().round(1), "win%": (100 * (net > 0).groupby(yr).mean()).round(0)}).to_string())
half = len(net) // 2
print("first half:", stat(net.iloc[:half]), "| second half:", stat(net.iloc[half:]))
