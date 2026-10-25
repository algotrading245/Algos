"""prebuilt_ger40_evening_coil (MQL5 CodeBase 78380): long after an NR7 coil in calm vol, late-session window, flat by exit hour.
H1 bars from histdata M1 (file clock = server clock). Rule: stdev(last 10 H1 returns) < 1.6*stdev(last 100), an NR7 bar
within the last 13 bars, bar start hour in the window -> buy next bar open; stop 3.5 ATR14, target 4.5 ATR14; flat at exit hour.
One trade a day. Tick-volume conditions dropped (no volume in histdata). Markets: SPXUSD, GRXEUR (NSXUSD missing), same params.
Two window cells (trials): A = session-matched late window, B = author's 18-20 / exit 23. Chosen on <=2017. Plain long control.
Daily return = trade return * size, size = 10% annual vol target / EWM daily vol (past), capped 3. Cost bp per side, doubled round trip.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "prebuilt_ger40_evening_coil"
COST = {"SPXUSD": 1.0, "GRXEUR": 1.5}  # bp per side
TARGET = 0.10
CELLS = {"A": {"SPXUSD": ((20, 21), 23), "GRXEUR": ((15, 16, 17), 18)},
         "B": {"SPXUSD": ((18, 19, 20), 23), "GRXEUR": ((18, 19, 20), 23)}}


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def load(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "high", "low", "close"]])
    b = h.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return b


def trades(b, win, exit_h, control=False):
    r = np.log(b.close).diff()
    rng = b.high - b.low
    nr7 = rng <= rng.rolling(7).min()
    coil_recent = nr7.rolling(13).max().fillna(0) > 0
    calm = r.rolling(10).std() < 1.6 * r.rolling(100).std()
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    sig = (coil_recent & calm) if not control else pd.Series(True, index=b.index)
    # signal is known at bar close; enter next bar open; "bar start hour of the entry bar" in window
    O, H, L, C = b.open.values, b.high.values, b.low.values, b.close.values
    idx = b.index
    hr = idx.hour.values
    day = idx.normalize().values
    sg = sig.values
    at = atr.values
    out = {}
    taken = set()
    for i in range(1, len(b) - 1):
        j = i + 1  # entry bar
        if day[j] != day[i] or hr[j] not in win or day[j] in taken:
            continue
        if control and hr[j] != win[0]:
            continue
        if not sg[i] or np.isnan(at[i]):
            continue
        entry = O[j]
        stop, tgt = entry - 3.5 * at[i], entry + 4.5 * at[i]
        if control:
            stop, tgt = -1e18, 1e18
        ex = None
        k = j
        while k < len(b) and day[k] == day[j] and hr[k] < exit_h:
            if L[k] <= stop:
                ex = stop; break
            if H[k] >= tgt:
                ex = tgt; break
            k += 1
        if ex is None:
            kk = min(k, len(b) - 1)
            ex = O[kk] if (kk < len(b) and day[kk] == day[j]) else C[kk - 1]
        taken.add(day[j])
        out[pd.Timestamp(day[j])] = np.log(ex / entry)
    return pd.Series(out).sort_index()


def leg(sym, cell, mult=1.0, control=False, bars={}):
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
    print("cell", c, "SR <=2017", round(sh(rs[rs.index < "2018"]), 2), "2018+", round(sh(rs[rs.index >= "2018"]), 2))
    for s in COST:
        p, t = leg(s, c)
        pc, tc = leg(s, c, control=True)
        print("  ", s, "trades", len(t), "mean ret bp", round(t.mean() * 1e4, 2), "win", round((t > 0).mean(), 3),
              "| control trades", len(tc), "mean bp", round(tc.mean() * 1e4, 2),
              "SR sig", round(sh(p), 2), "SR ctrl", round(sh(pc), 2))
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
