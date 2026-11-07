"""variant_asian_range_london_fade_eurusd: fade of the London-open excursion beyond the Asian range (M1, server clock).
Asian range = high/low of 01:00-08:59. At 11:00 (open of the 11:00 bar) if price > high + k*range -> short, if
< low - k*range -> long. Target = range midpoint, stop = entry +/- 0.75*range, time exit 17:00 (close of 16:59 bar).
Stop checked before target inside a bar (conservative). Main k 0.25, second cell 0.5 (2 trials).
Markets EURUSD, GBPUSD, USDCHF, same parameters. Cost per side (bp): 0.8 / 1.0 / 1.3 (conservative, charged on both
sides), stress 1.5x / 2x. Size = 10% vol target / EWM daily vol (past), cap 3.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "variant_asian_range_london_fade_eurusd"
COSTS = {"EURUSD": 0.8, "GBPUSD": 1.0, "USDCHF": 1.3}
TARGET = 0.10
STOPK = 0.75


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def prep(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "high", "low", "close"]])
    h = h[h.index.dayofweek < 5]
    m = h.index.hour * 60 + h.index.minute
    dc = h.close.groupby(h.index.normalize()).last()
    vol = np.log(dc).diff().ewm(span=40).std().shift(1) * np.sqrt(252)
    asia = h[(m >= 60) & (m < 540)].groupby(h[(m >= 60) & (m < 540)].index.normalize())
    ar = pd.DataFrame({"hi": asia.high.max(), "lo": asia.low.min(), "n": asia.size()})
    day = h[(m >= 660) & (m < 1020)]
    days = {k: g for k, g in day.groupby(day.index.normalize())}
    return ar, days, vol


D = {s: prep(s) for s in COSTS}


def trades(sym, k):
    ar, days, vol = D[sym]
    rows = []
    for d, g in days.items():
        if d not in ar.index or len(g) < 300:
            continue
        a = ar.loc[d]
        if a.n < 300:
            continue
        rng = a.hi - a.lo
        if rng <= 0:
            continue
        p0 = g.open.iloc[0]
        if p0 > a.hi + k * rng:
            side = -1
        elif p0 < a.lo - k * rng:
            side = 1
        else:
            continue
        mid = (a.hi + a.lo) / 2
        stop = p0 - side * STOPK * rng
        ex = g.close.iloc[-1]
        for hi, lo, cl in zip(g.high.values, g.low.values, g.close.values):
            if side == -1:
                if hi >= stop:
                    ex = stop; break
                if lo <= mid:
                    ex = mid; break
            else:
                if lo <= stop:
                    ex = stop; break
                if hi >= mid:
                    ex = mid; break
        rows.append((d, side * np.log(ex / p0)))
    t = pd.Series(dict(rows), dtype=float)
    return t, vol


def leg(sym, k, mult=1.0):
    t, vol = trades(sym, k)
    v = vol.reindex(t.index)
    size = (TARGET / v).clip(upper=3)
    pnl = size * (t - 2 * COSTS[sym] * mult * 1e-4)
    return pnl[v.notna()], t


def comb(k, mult=1.0):
    return pd.concat([leg(s, k, mult)[0] for s in COSTS], axis=1).fillna(0).mean(axis=1)


for k in (0.25, 0.5):
    print("== k", k)
    for s in COSTS:
        p, t = leg(s, k)
        print(s, "trades", len(t), "gross bp", round(t.mean() * 1e4, 2), "hit", round((t > 0).mean(), 3),
              "SR<=2017", round(sh(p[p.index < "2018"]), 2), "2018+", round(sh(p[p.index >= "2018"]), 2),
              "1.5x", round(sh(leg(s, k, 1.5)[0]), 2), flush=True)
    r, r15, r2 = comb(k), comb(k, 1.5), comb(k, 2.0)
    print("combo SR<=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
          "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2), "days", len(r), "to", r.index.max().date())
    if k == 0.25:
        main = (r, r15)
        mk = pd.DataFrame({s: leg(s, k)[0] for s in COSTS})

r, r15 = main
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
mk.rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
