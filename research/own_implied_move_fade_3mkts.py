"""own_implied_move_fade_3mkts: fade intraday moves beyond k x option-implied daily sigma (VIX/GVZ/EVZ lagged 1 day).
Server clock (histdata, NY+7): signal 21:00 (=14:00 NY), exit 23:00 (16:00 NY; avoids the 23-01 rollover, lesson 9).
Day open: SPX cash open 16:30, XAU/EUR 01:00 server. move = ln(p21:00 / open); sigma = idx/100/sqrt(252) (previous day's fix).
|move| > k*sigma -> trade against it; stop at 2*sigma adverse from entry (M1 high/low). k=1.0 main, 1.5 second (2 trials).
Size = 10% vol target / EWM daily vol (past), cap 3. Cost per side bp: SPX 1.5, XAU 2.0, EUR 0.7; stress 1.5x / 2x.
EVZ file ends 2025-03: EURUSD only to there."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "own_implied_move_fade_3mkts"
TARGET = 0.10
M = {"SPXUSD": ("VIXCLS", 1.5, 16 * 60 + 30), "XAUUSD": ("GVZCLS", 2.0, 60), "EURUSD": ("EVZCLS", 0.7, 60)}
SIG, EXIT = 21 * 60, 23 * 60


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def prep(sym):
    idx, cost, openm = M[sym]
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "high", "low", "close"]])
    h = h[h.index.dayofweek < 5]
    m = h.index.hour * 60 + h.index.minute
    day = h.index.normalize()
    o = h[m == openm].groupby(day[m == openm]).open.first()
    s = h[m == SIG].groupby(day[m == SIG]).close.first()
    w = h[(m > SIG) & (m <= EXIT)]
    wd = w.index.normalize()
    g = w.groupby(wd)
    e = h[m == EXIT].groupby(day[m == EXIT]).close.first()
    hi, lo = g.high.max(), g.low.min()
    d = pd.DataFrame({"o": o, "s": s, "e": e, "hi": hi, "lo": lo}).dropna()
    # daily close series for vol (22:00 server)
    c = h[m == 22 * 60].groupby(day[m == 22 * 60]).close.first()
    vol = np.log(c).diff().ewm(span=40).std().shift(1) * np.sqrt(252)
    d["vol"] = vol.reindex(d.index)
    v = pd.read_csv(ROOT / "marketdata" / "fred" / f"{idx}.csv", parse_dates=["observation_date"], index_col="observation_date")
    v = pd.to_numeric(v.iloc[:, 0], errors="coerce").dropna()
    # lagged one day: value known for the previous trading day
    d["iv"] = v.shift(1).reindex(d.index, method="ffill", tolerance=pd.Timedelta("5D"))
    d["sig"] = d.iv / 100 / np.sqrt(252)
    d["move"] = np.log(d.s / d.o)
    return d.dropna()


D = {s: prep(s) for s in M}


def leg(s, k, mult=1.0):
    d = D[s]
    cost = M[s][1] * mult * 1e-4
    side = -np.sign(d.move) * (d.move.abs() > k * d.sig)
    stop = 2 * d.sig
    # long: adverse = low; short: adverse = high
    adv = np.where(side > 0, np.log(d.lo / d.s), np.log(d.hi / d.s) * -1)  # adverse return in position direction (negative=bad)
    hit = (side != 0) & (adv < -stop)
    ret = np.where(hit, -stop, side * np.log(d.e / d.s))
    size = (TARGET / d.vol).clip(upper=3)
    pnl = size * (ret - (side != 0) * 2 * cost)
    return pd.Series(np.asarray(pnl), index=d.index), side


def comb(k, mult=1.0):
    return pd.concat([leg(s, k, mult)[0] for s in M], axis=1).fillna(0).mean(axis=1)


main = None
for k in (1.0, 1.5):
    print("== k", k)
    for s in M:
        p, side = leg(s, k)
        p15 = leg(s, k, 1.5)[0]
        print(s, "trades", int((side != 0).sum()), "SR<=2017", round(sh(p[p.index < "2018"]), 2), "2018+",
              round(sh(p[p.index >= "2018"]), 2), "1.5x", round(sh(p15), 2), "from", D[s].index.min().date(),
              "to", D[s].index.max().date(), flush=True)
    r, r15, r2 = comb(k), comb(k, 1.5), comb(k, 2.0)
    print("combo SR<=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
          "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2), "days", len(r))
    if k == 1.0:
        main = (r, r15, pd.DataFrame({s: leg(s, k)[0] for s in M}))

r, r15, mk = main
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
mk.rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
