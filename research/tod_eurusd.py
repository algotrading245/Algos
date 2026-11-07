"""Breedon & Ranaldo time-of-day rule on EURUSD: short 07:00-13:00 GMT, long 13:00-21:00 GMT, one trade each per
weekday. Hours fixed from the paper (no tuning). Histdata clock = New York + 7h (server). GMT is derived with the US
DST rule. The long leg is cut at server 22:55 (before the 23:00 rollover) when 21:00 GMT falls after it (US summer).
Cost: round trip 0.8 bp per trade (EURUSD, as in london_breakout.py); stress 1.5x; 2x reported too.

    python research/tod_eurusd.py
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import holdout

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "marketdata" / "candidates"
COST = 0.8e-4

m = pd.read_csv(ROOT / "marketdata" / "histdata" / "EURUSD_M1.csv.gz")
srv = pd.to_datetime(m.time, unit="s")
ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
ok = ny.notna()
m, srv, ny = m[ok], srv[ok], ny[ok]
gmt = ny.dt.tz_convert("UTC").dt.tz_localize(None)
s = pd.Series(m.close.to_numpy(), index=gmt.to_numpy())
s = s[~s.index.duplicated()]
sh_ = pd.Series(srv.dt.hour * 60 + srv.dt.minute).to_numpy()
srvmin = pd.Series(sh_, index=gmt.to_numpy())
srvmin = srvmin[~srvmin.index.duplicated()]

days = pd.DatetimeIndex(sorted(set(s.index.normalize())))
days = days[days.dayofweek < 5]


def px(day, hh, mm=0):
    t = day + pd.Timedelta(hours=hh, minutes=mm)
    # last close at or before t, within 10 minutes
    i = s.index.searchsorted(t, side="right") - 1
    if i < 0 or t - s.index[i] > pd.Timedelta(minutes=10):
        return np.nan
    return s.iloc[i]


rows = []
for d in days:
    p7, p13, p21 = px(d, 7), px(d, 13), px(d, 21)
    # rollover guard: if 21:00 GMT is past server 22:55, exit at server 22:55 = GMT 19:55 (US summer)
    i = s.index.searchsorted(d + pd.Timedelta(hours=21), side="right") - 1
    if i >= 0 and srvmin.iloc[i] < 23 * 60 and srvmin.iloc[i] >= 12 * 60:
        pass
    else:
        p21 = px(d, 19, 55)
    if np.isnan([p7, p13, p21]).any():
        continue
    rows.append((d, -(p13 / p7 - 1), (p21 / p13 - 1)))
T = pd.DataFrame(rows, columns=["day", "short", "long"]).set_index("day")
T = holdout.drop(T)


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def series(k):
    return T["short"] + T["long"] - 2 * COST * k


for name, f in (("short only", lambda k: T["short"] - COST * k), ("long only", lambda k: T["long"] - COST * k),
                ("both", series)):
    for k in (0, 1, 1.5, 2):
        x = f(k)
        print(f"{name} {k}x cost: Sharpe {sh(x):+.2f} (to2017 {sh(x[:'2017']):+.2f}, 2018+ {sh(x['2018':]):+.2f}) mean {x.mean()*1e4:+.2f} bp")
x = series(1)
print("by year (1x):", {y: round(sh(g), 2) for y, g in x.groupby(x.index.year)})
print("days", len(T), T.index[0].date(), T.index[-1].date(), "daily vol", round(x.std() * 100, 3), "%")
for k, nm in ((1, ""), (1.5, "_stress")):
    o = series(k).rename("r")
    o.index.name = "day"
    o.to_csv(OUT / f"tod_eurusd{nm}.csv")
