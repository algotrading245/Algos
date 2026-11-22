"""variant_index_open_gap_fade_4mkts: cash-open gap fade on SPX, NSX, GRX, JPX (histdata M1, server clock).
gap = cash open / previous cash close - 1; z = gap / sd of the previous 60 gaps (past only); z <= -thr long, z >= thr
short at the open, exit at the same day's cash close. Main cell thr 1.0, second cell 1.5 (2 trials).
Sessions (server clock, as in the hamao script): SPX/NSX 16:30-23:00, GRX 10:00-18:30, JPX 02:00-08:00.
Size = 10% vol target / EWM daily vol (past), cap 3. Cost 1.5bp per side (index CFD), stress 1.5x / 2x.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "variant_index_open_gap_fade_4mkts"
COST = 1.5
TARGET = 0.10
SESS = {"SPXUSD": (16 * 60 + 30, 23 * 60), "NSXUSD": (16 * 60 + 30, 23 * 60),
        "GRXEUR": (10 * 60, 18 * 60 + 30), "JPXJPY": (2 * 60, 8 * 60)}


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def prep(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "close"]])
    a, b = SESS[sym]
    m = h.index.hour * 60 + h.index.minute
    w = h[(m >= a) & (m < b) & (h.index.dayofweek < 5)]
    g = w.groupby(w.index.normalize())
    d = pd.DataFrame({"o": g.open.first(), "c": g.close.last(), "n": g.size()})
    d = d[d.n > 60]
    d["gap"] = np.log(d.o / d.c.shift(1))
    d["sd"] = d.gap.rolling(60).std().shift(1)
    d["z"] = d.gap / d.sd
    d["intra"] = np.log(d.c / d.o)
    d["vol"] = np.log(d.c).diff().ewm(span=40).std().shift(1) * np.sqrt(252)
    # skip gaps spanning more than 5 calendar days (data holes)
    d["span"] = pd.Series(d.index, index=d.index).diff().dt.days
    return d


D = {s: prep(s) for s in SESS}


def leg(s, thr, mult=1.0, sign=-1):
    d = D[s]
    pos = pd.Series(0.0, index=d.index)
    pos[d.z <= -thr] = -sign
    pos[d.z >= thr] = sign
    pos[d.span > 5] = 0
    size = (TARGET / d.vol).clip(upper=3)
    pnl = size * (pos * d.intra - (pos != 0) * 2 * COST * mult * 1e-4)
    return pnl[d.vol.notna() & d.sd.notna()], pos


def comb(thr, mult=1.0):
    return pd.concat([leg(s, thr, mult)[0] for s in SESS], axis=1).fillna(0).mean(axis=1)


for thr in (1.0, 1.5):
    print("== thr", thr)
    for s in SESS:
        p, pos = leg(s, thr)
        g = (pos * D[s].intra)[pos != 0]
        print(s, "trades", int((pos != 0).sum()), "gross bp", round(g.mean() * 1e4, 2), "hit", round((g > 0).mean(), 3),
              "SR<=2017", round(sh(p[p.index < "2018"]), 2), "2018+", round(sh(p[p.index >= "2018"]), 2),
              "1.5x", round(sh(leg(s, thr, 1.5)[0]), 2), "from", D[s].index.min().date(), flush=True)
    r, r15, r2 = comb(thr), comb(thr, 1.5), comb(thr, 2.0)
    print("combo SR<=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
          "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2), "days", len(r), "to", r.index.max().date())
    if thr == 1.0:
        main = (r, r15)
        mk = pd.DataFrame({s: leg(s, thr)[0] for s in SESS})

r, r15 = main
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
mk.rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
