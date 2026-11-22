"""paper_rapach_us_lead_weekly_indices: sign of (SPX week return - trailing 52-week median of weekly returns), known at
Friday close, sets long/short of GER40 and JPN225 (and NSXUSD as third, same rule) for the next week (Mon first open to
Fri last close). Main cell: 1-week return; second cell: 4-week return vs its 52-week median. 2 cells = 2 trials.
Size = 10% vol target / EWM daily vol (past), cap 3. Cost 1.5bp per side. UK100 not in our data.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_rapach_us_lead_weekly_indices"
COST, TARGET = 1.5, 0.10


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def load(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["open", "close"]])
    g = h.groupby(h.index.normalize())
    d = pd.DataFrame({"o": g.open.first(), "c": g.close.last()})
    return d[d.index.dayofweek < 5]


def weekly(d):
    wk = d.index.to_period("W-SUN")
    g = d.groupby(wk)
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "n": g.size()})


spx = weekly(load("SPXUSD"))
spx = spx[spx.n >= 3]


def signal(lb):
    r = np.log(spx.c).diff(lb)
    med = r.rolling(52).median()
    return np.sign(r - med).shift(0)  # known at the close of week t; applies to week t+1


def leg(sym, lb, mult=1.0):
    d = load(sym)
    w = weekly(d)
    dvol = np.log(d.c).diff().ewm(span=40).std() * np.sqrt(252)
    s = signal(lb)
    pnl = {}
    periods = w.index
    for i in range(1, len(periods)):
        p, prev = periods[i], periods[i - 1]
        if prev not in s.index or np.isnan(s.get(prev, np.nan)) or s[prev] == 0 or prev != p - 1:
            continue
        if w.n.iloc[i] < 3:
            continue
        days = d[d.index.to_period("W-SUN") == p]
        first = days.index[0]
        v = dvol[:first].iloc[-2] if len(dvol[:first]) > 1 else np.nan  # vol known before the week
        if np.isnan(v) or v <= 0:
            continue
        size = min(TARGET / v, 3)
        ret = np.log(w.c.iloc[i] / w.o.iloc[i])
        net = size * (s[prev] * ret - 2 * COST * mult * 1e-4)
        pnl[days.index[-1]] = net
    return pd.Series(pnl)


def control(sym):
    d = load(sym)
    w = weekly(d)
    return np.log(w.c / w.o)


MARK = ["GRXEUR", "JPXJPY", "NSXUSD"]
for lb in (1, 4):
    legs, l15, l2 = {}, {}, {}
    for m in MARK:
        legs[m], l15[m], l2[m] = leg(m, lb), leg(m, lb, 1.5), leg(m, lb, 2.0)
        p = legs[m]
        print(f"lb{lb}", m, "weeks", len(p), "SR<=2017", round(sh(p[p.index < "2018"]) / np.sqrt(252) * np.sqrt(52), 2),
              "2018+", round(sh(p[p.index >= "2018"]) / np.sqrt(252) * np.sqrt(52), 2),
              "1.5x", round(sh(l15[m]) / np.sqrt(252) * np.sqrt(52), 2), flush=True)
    r = pd.concat(legs.values(), axis=1).fillna(0).mean(axis=1)
    r15 = pd.concat(l15.values(), axis=1).fillna(0).mean(axis=1)
    f = np.sqrt(52 / 252)
    print(f"lb{lb} combined weekly SR <=2017", round(sh(r[r.index < '2018']) * f, 2), "2018+", round(sh(r[r.index >= '2018']) * f, 2),
          "1.5x", round(sh(r15) * f, 2), "n", len(r), flush=True)
    if lb == 1:
        R, R15, L = r, r15, legs

# daily series for gates: weekly pnl placed on Friday, zeros elsewhere
for f_, x in ((OUT / f"{ID}.csv", R), (OUT / f"{ID}_stress.csv", R15)):
    idx = pd.bdate_range(x.index.min(), x.index.max())
    x.reindex(idx).fillna(0).rename("r").rename_axis("day").to_csv(f_)
idx = pd.bdate_range(R.index.min(), R.index.max())
pd.DataFrame(L).reindex(idx).fillna(0).rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
