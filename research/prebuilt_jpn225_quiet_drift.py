"""prebuilt_jpn225_quiet_drift (MQL5 CodeBase 78027): M15, long only, flat by exit hour.
Signal at an M15 bar close in the window: close > 34-bar mean + 0.5 sd AND MACD(12,26,9) hist / ATR14 < 0.2 -> buy next open.
Stop 4 ATR, target 3.5 ATR. Tick-volume condition dropped (no volume in histdata). One trade a day.
Markets JPXJPY, GRXEUR, SPXUSD (NSXUSD missing), same parameters, windows matched to each session's open (server clock
EET: Tokyo opens 02:00, Xetra 10:00, NY cash 16:30). Two window cells = 2 trials, chosen on <=2017.
Plain long-in-window control (no signal, no stops) printed alongside. Size = 10% vol target / EWM daily vol (past), cap 3.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "prebuilt_jpn225_quiet_drift"
COST = {"JPXJPY": 1.5, "GRXEUR": 1.5, "SPXUSD": 1.0}  # bp per side
TARGET = 0.10
CELLS = {"A": {"JPXJPY": ((4, 5, 6, 7), 9), "GRXEUR": ((12, 13, 14, 15), 17), "SPXUSD": ((18, 19, 20, 21), 22)},
         "B": {"JPXJPY": ((3, 4, 5), 8), "GRXEUR": ((11, 12, 13), 16), "SPXUSD": ((17, 18, 19), 21)}}


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def load(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "high", "low", "close"]])
    return h.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def signals(b):
    c = b.close
    m = c.rolling(34).mean()
    sd = c.rolling(34).std()
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    sig = (c > m + 0.5 * sd) & (hist / atr < 0.2)
    return sig.values, atr.values


def trades(b, win, exit_h, control=False, cache={}):
    key = id(b)
    if key not in cache:
        cache[key] = signals(b)
    sg, at = cache[key]
    O, H, L, C = b.open.values, b.high.values, b.low.values, b.close.values
    idx = b.index
    hr = idx.hour.values
    day = idx.normalize().values
    out = {}
    taken = set()
    n = len(b)
    for i in range(1, n - 1):
        j = i + 1
        if day[j] != day[i] or hr[j] not in win or day[j] in taken:
            continue
        if control:
            if not (hr[j] == win[0] and idx[j].minute == 0):
                continue
        elif not sg[i] or np.isnan(at[i]):
            continue
        entry = O[j]
        stop, tgt = (-1e18, 1e18) if control else (entry - 4 * at[i], entry + 3.5 * at[i])
        ex = None
        k = j
        while k < n and day[k] == day[j] and hr[k] < exit_h:
            if L[k] <= stop:
                ex = stop; break
            if H[k] >= tgt:
                ex = tgt; break
            k += 1
        if ex is None:
            ex = O[k] if (k < n and day[k] == day[j]) else C[k - 1]
        taken.add(day[j])
        out[pd.Timestamp(day[j])] = np.log(ex / entry)
    return pd.Series(out).sort_index()


bars = {}


def leg(sym, cell, mult=1.0, control=False):
    if sym not in bars:
        bars[sym] = load(sym)
    b = bars[sym]
    win, ex = CELLS[cell][sym]
    t = trades(b, win, ex, control)
    d = b.close.groupby(b.index.normalize()).last()
    d = d[d.index.dayofweek < 5]
    vol = np.log(d).diff().ewm(span=40).std().shift(1) * np.sqrt(252)
    size = (TARGET / vol).clip(upper=3).reindex(t.index)
    pnl = size * (t - 2 * COST[sym] * mult * 1e-4)
    return pnl.reindex(d.index).fillna(0.0)[vol.notna().reindex(d.index).fillna(False)], t


res = {}
for c in CELLS:
    rs = pd.concat([leg(s, c)[0] for s in COST], axis=1).mean(axis=1)
    res[c] = rs
    print("cell", c, "SR <=2017", round(sh(rs[rs.index < "2018"]), 2), "2018+", round(sh(rs[rs.index >= "2018"]), 2), flush=True)
    for s in COST:
        p, t = leg(s, c)
        pc, tc = leg(s, c, control=True)
        print("  ", s, "trades", len(t), "mean bp", round(t.mean() * 1e4, 2), "win", round((t > 0).mean(), 3),
              "| control trades", len(tc), "mean bp", round(tc.mean() * 1e4, 2),
              "SR sig", round(sh(p), 2), "SR ctrl", round(sh(pc), 2), flush=True)
best = max(res, key=lambda k: sh(res[k][res[k].index < "2018"]))
print("chosen on <=2017:", best, "(2 cells = 2 trials)")

legs = {s: leg(s, best)[0] for s in COST}
l15 = {s: leg(s, best, 1.5)[0] for s in COST}
l2 = {s: leg(s, best, 2.0)[0] for s in COST}
for s in COST:
    a = legs[s]
    print(s, "SR <=2017", round(sh(a[a.index < "2018"]), 2), "2018+", round(sh(a[a.index >= "2018"]), 2),
          "1.5x", round(sh(l15[s]), 2), "2x", round(sh(l2[s]), 2))
r = pd.concat(legs.values(), axis=1).mean(axis=1).dropna()
r15 = pd.concat(l15.values(), axis=1).mean(axis=1).dropna()
r2 = pd.concat(l2.values(), axis=1).mean(axis=1).dropna()
print("candidate SR <=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
      "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2), "days", len(r))
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
pd.DataFrame(legs).dropna(how="all").rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
