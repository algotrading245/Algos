"""paper_nagel_vix_reversal_index: Nagel (NBER 17653) VIX-conditioned short-term reversal, index-level adaptation.
At the daily close t: if VIX close(t) > trailing 252d 70th percentile (past only, incl. t), position = -sign(L-day return),
held H days (H overlapping tranches), else flat. Vol-targeted 10%. Markets: SPXUSD, NSXUSD, XAUUSD, EURUSD (same params).
Settings grid (L in 1,5 ; H in 1,3) chosen on <=2017 only; every cell is a trial. Costs per unit turnover (bp) and swap.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_nagel_vix_reversal_index"
COST = {"SPXUSD": 1.0, "NSXUSD": 1.5, "XAUUSD": 0.8, "EURUSD": 0.6}  # bp per unit of turnover
SWAP = 0.03  # annual, on |pos| held
TARGET = 0.10


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def daily(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz", usecols=["time", "close"])
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["close"]])
    h = h[h.index.hour < 21]  # close ~ 20:59 UTC, before rollover
    d = h.close.groupby(h.index.normalize()).last()
    return d[d.index.dayofweek < 5]


vix = pd.read_csv(ROOT / "marketdata" / "vixidx" / "^VIX.csv", parse_dates=["date"], index_col="date").close
vix = holdout.drop(vix.to_frame("close")).close
hi = vix > vix.rolling(252).quantile(0.7)


def run(D, sym, L, H, mult=1.0):
    R = np.log(D).diff()
    vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
    flag = hi.reindex(D.index).ffill().fillna(False).astype(bool)
    sig = (-np.sign(np.log(D / D.shift(L)))).where(flag, 0.0)
    pos_t = (sig * TARGET / vol).clip(-3, 3)
    pos = pos_t.rolling(H).mean().shift(1)  # tranches opened on last H closes
    c = COST[sym] * mult * 1e-4
    return pos * R - pos.diff().abs() * c - pos.abs() * SWAP * mult / 252, pos


data = {s: daily(s) for s in COST}
for s, d in data.items():
    print(s, d.index[0].date(), d.index[-1].date(), len(d))

res = {}
print("grid (SPXUSD+NSXUSD avg), SR <=2017 | 2018+")
for L in (1, 5):
    for H in (1, 3):
        rs = pd.concat([run(data[s], s, L, H)[0] for s in ("SPXUSD", "NSXUSD")], axis=1).mean(axis=1)
        res[(L, H)] = rs
        print(L, H, round(sh(rs[rs.index < "2018"]), 2), round(sh(rs[rs.index >= "2018"]), 2))
# choose on <=2017 only
best = max(res, key=lambda k: sh(res[k][res[k].index < "2018"]))
L, H = best
print("chosen on <=2017:", best, " trials 4 grid")

legs = {s: run(data[s], s, L, H)[0] for s in COST}
legs15 = {s: run(data[s], s, L, H, 1.5)[0] for s in COST}
legs2 = {s: run(data[s], s, L, H, 2.0)[0] for s in COST}
for s in COST:
    a = legs[s]
    print(s, "SR <=2017", round(sh(a[a.index < "2018"]), 2), "2018+", round(sh(a[a.index >= "2018"]), 2),
          "1.5x", round(sh(legs15[s]), 2), "2x", round(sh(legs2[s]), 2))

main = ("SPXUSD", "NSXUSD")
r = pd.concat([legs[s] for s in main], axis=1).mean(axis=1).dropna()
r15 = pd.concat([legs15[s] for s in main], axis=1).mean(axis=1).dropna()
r2 = pd.concat([legs2[s] for s in main], axis=1).mean(axis=1).dropna()
print("candidate SR <=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
      "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2))
ms = r.groupby(r.index.to_period("M")).sum()
print("losing months", int((ms < 0).sum()), "of", len(ms))
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
pd.DataFrame(legs).dropna(how="all").rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
