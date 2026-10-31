"""paper_hamao_us_close_to_asia_eu_open: sign of the SPX cash-session return (16:30-23:00 server) on day t sets the
direction of GER40 / JPN225 for 4 hours from their next open (Xetra 10:00, Tokyo 02:00 server clock, next calendar day).
No trade if |US ret| < 0.3 * 60-day sd of US cash returns (past only). One cell (4h), no tuning: 1 trial.
Third market: NSXUSD signal -> same targets is not independent, so the third market is GRXEUR signalled by SPX but held
the Tokyo-free later window 14:00-18:00? No - kept simple: markets = GER40, JPN225, plus a second window for GER40 (afternoon
before the US open, 12:00-16:00) so that belief rests on 3 target legs with the same rule. Reported as is.
Size = 10% vol target / EWM daily vol (past), cap 3. Cost 1.5bp per side index.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_hamao_us_close_to_asia_eu_open"
COST = 1.5
TARGET = 0.10


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def load(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    return holdout.drop(h[["open", "close"]])


def window_ret(h, start, end):
    """per calendar day: log(open at first bar >= start / close of last bar < end)."""
    t = h.index
    m = (t.hour * 60 + t.minute >= start) & (t.hour * 60 + t.minute < end)
    w = h[m]
    g = w.groupby(w.index.normalize())
    return np.log(g.close.last() / g.open.first())


spx = load("SPXUSD")
us = window_ret(spx, 16 * 60 + 30, 23 * 60)
us = us[us.index.dayofweek < 5]
sd = us.rolling(60).std().shift(1)  # past only
sig = np.sign(us).where(us.abs() >= 0.3 * sd)  # known at 23:00 of day t

TARGETS = {"GRXEUR": (10 * 60, 14 * 60), "JPXJPY": (2 * 60, 6 * 60), "GRXEUR_pm": (12 * 60, 16 * 60)}
raw = {}
for name, (a, b) in TARGETS.items():
    h = load(name.split("_")[0])
    raw[name] = window_ret(h, a, b)
    d = h.close.groupby(h.index.normalize()).last()
    d = d[d.index.dayofweek < 5]
    raw[name + "_vol"] = np.log(d).diff().ewm(span=40).std().shift(1) * np.sqrt(252)


def leg(name, mult=1.0, control=False):
    ret = raw[name].dropna()
    days = ret.index
    # signal of the previous US day applies to next target day (next day in target series after t)
    s = sig.dropna()
    pos = pd.Series(0.0, index=days)
    for t, v in s.items():
        k = days.searchsorted(t, side="right")  # first target day > t
        if k < len(days) and (days[k] - t).days <= 4:
            pos.iloc[k] = 1.0 if control else v
    if control:
        pos = pd.Series(1.0, index=days)  # plain long every day
    vol = raw[name + "_vol"].reindex(days)
    size = (TARGET / vol).clip(upper=3)
    trade = (pos != 0).astype(float)
    pnl = size * (pos * ret - trade * 2 * COST * mult * 1e-4)
    return pnl[vol.notna()], pos


legs, l15, l2 = {}, {}, {}
for n in TARGETS:
    p, pos = leg(n)
    pc, _ = leg(n, control=True)
    legs[n], l15[n], l2[n] = p, leg(n, 1.5)[0], leg(n, 2.0)[0]
    gross = (pos * raw[n].reindex(pos.index))[pos != 0]
    print(n, "trades", int((pos != 0).sum()), "gross mean bp", round(gross.mean() * 1e4, 2), "hit", round((gross > 0).mean(), 3),
          "SR <=2017", round(sh(p[p.index < "2018"]), 2), "2018+", round(sh(p[p.index >= "2018"]), 2),
          "1.5x", round(sh(l15[n]), 2), "2x", round(sh(l2[n]), 2), "| long ctrl SR", round(sh(pc), 2), flush=True)
r = pd.concat(legs.values(), axis=1).fillna(0).mean(axis=1)
r15 = pd.concat(l15.values(), axis=1).fillna(0).mean(axis=1)
r2 = pd.concat(l2.values(), axis=1).fillna(0).mean(axis=1)
print("candidate SR <=2017", round(sh(r[r.index < "2018"]), 2), "2018+", round(sh(r[r.index >= "2018"]), 2),
      "1.5x", round(sh(r15), 2), "2x", round(sh(r2), 2), "days", len(r), "to", r.index.max().date())
for f, x in ((OUT / f"{ID}.csv", r), (OUT / f"{ID}_stress.csv", r15)):
    x.rename("r").rename_axis("day").to_csv(f)
pd.DataFrame(legs).rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
