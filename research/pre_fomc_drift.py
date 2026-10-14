"""Pre-FOMC announcement drift (Lucca, Moench, NY Fed Staff Report 512 / Journal of Finance 2015; Kurov, Wolfe,
Gilbert 2021, "The Disappearing Pre-FOMC Announcement Drift", Finance Research Letters 40).

The S&P 500 rose 49 bp in the 24 hours ending 15 minutes before scheduled FOMC statements in 1994-2011 (Sharpe
1.1, 1.4 from the previous close).  Kurov et al.: 4.7 bp in April 2011-2019; from the previous day's open 44 bp
before press-conference meetings in 2011-2015 and 9 bp in 2016-2019; larger when the VIX two days before is high.
Windows here, all ending 15 minutes before the statement (New York clock), one round trip each:

    24h     same minute the day before        close   16:00 the day before
    open    9:30 the day before (Kurov)       day     9:30 on the day
    after   statement - 15 min -> 16:00 (placebo, both papers find nothing)

    python research/pre_fomc_drift.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: from the previous close 14 bp a meeting after 1 bp, Sharpe 0.66 (0.52 to 2017, 0.76 from 2018); 24 bp and
           1.0 when the volatility known two days before is above its median, 0.3 when below, as Kurov et al. say.
           By period: 13 bp 2011-2015, 6 bp 2016-2019, 45 bp 2020-2022, 5 bp 2023-2026 - it came back with the
           uncertainty of 2020-2022 and has faded again.  Nothing on the day itself or after the statement.
  DAX, Nikkei: the same size and shape (Sharpe 0.5-0.7).  Gold, USDJPY: nothing.  EURUSD: gone since 2018.
  As a Hydra leg (8 trades a year, uncorrelated with the others) the combined Sharpe goes from 3.01 to 3.06 at
           best, and falls once the leg is sized large enough to matter.  Too few trades to earn a place.
"""
import numpy as np
import pandas as pd

from intraday_momentum import SPLIT, at, minutes
from overnight_intraday_reversal import NY, matrix

# statement days of scheduled meetings; March 2020 was replaced by two unscheduled cuts
FOMC = {2010: "1103 1214", 2011: "0126 0315 0427 0622 0809 0921 1102 1213",
        2012: "0125 0313 0425 0620 0801 0913 1024 1212", 2013: "0130 0320 0501 0619 0731 0918 1030 1218",
        2014: "0129 0319 0430 0618 0730 0917 1029 1217", 2015: "0128 0318 0429 0617 0729 0917 1028 1216",
        2016: "0127 0316 0427 0615 0727 0921 1102 1214", 2017: "0201 0315 0503 0614 0726 0920 1101 1213",
        2018: "0131 0321 0502 0613 0801 0926 1108 1219", 2019: "0130 0320 0501 0619 0731 0918 1030 1211",
        2020: "0129 0429 0610 0729 0916 1105 1216", 2021: "0127 0317 0428 0616 0728 0922 1103 1215",
        2022: "0126 0316 0504 0615 0727 0921 1102 1214", 2023: "0201 0322 0503 0614 0726 0920 1101 1213",
        2024: "0131 0320 0501 0612 0731 0918 1107 1218", 2025: "0129 0319 0507 0618 0730 0917 1029 1210",
        2026: "0128 0318 0429 0617 0729 0916"}
# press conference: listed meetings to 2018, every meeting from 2019
PRESS = {2011: "0427 0622 1102", 2012: "0125 0425 0620 0913 1212", 2013: "0320 0619 0918 1218",
         2014: "0319 0618 0917 1217", 2015: "0318 0617 0917 1216", 2016: "0316 0615 0921 1214",
         2017: "0315 0614 0920 1213", 2018: "0321 0613 0926 1219"}
WINDOWS = ("24h", "close", "open", "day", "after")
MARKETS = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0, "XAUUSD": 0.8, "EURUSD": 0.85, "USDJPY": 0.85}


def dates(table):
    return pd.DatetimeIndex([f"{y}-{d[:2]}-{d[2:]}" for y, days in table.items() for d in days.split()])


def events():
    e = pd.DataFrame(index=dates(FOMC))
    e["press"] = e.index.isin(dates(PRESS)) | (e.index.year >= 2019)
    early = e.index < "2011-04-01"
    middle = (e.index >= "2011-04-01") & (e.index < "2013-03-01")
    e["minute"] = np.where(early | (middle & ~e["press"]), minutes("14:15"),
                           np.where(middle, minutes("12:30"), minutes("14:00"))) - 15
    return e


def one(lp, row, minute):
    return at(lp[[row]], minute)[0]


def windows(symbol):
    """Log return over each window for every meeting, the 24h return of other days, and the volatility known
    two days before (20 closes, as the papers' VIX at the close two days before)."""
    days, p = matrix(symbol, NY)
    lp = np.log(p.astype(float))
    week = np.flatnonzero(days.dayofweek < 5)
    e = events()
    out = {}
    for d, (press, m) in e.iterrows():
        k = np.searchsorted(days[week], d)
        if k == 0 or k >= len(week) or days[week[k]] != d:
            continue
        i, j = week[k], week[k - 1]
        end = one(lp, i, m)
        out[d] = {"24h": end - one(lp, j, m), "close": end - one(lp, j, minutes("16:00")),
                  "open": end - one(lp, j, minutes("09:30")), "day": end - one(lp, i, minutes("09:30")),
                  "after": one(lp, i, minutes("16:00")) - end}
    r = pd.DataFrame(out).T.join(e["press"])
    c = pd.Series(at(lp, minutes("16:00")), index=days)[days.dayofweek < 5].dropna()
    vol = c.diff().rolling(20).std().shift(2)
    r["vol"] = vol.reindex(r.index)
    r["high"] = (vol > vol.rolling(500, min_periods=120).median()).reindex(r.index).fillna(False).astype(bool)
    x = pd.Series(at(lp, minutes("13:45")), index=days)[days.dayofweek < 5].dropna().diff()
    return r, x[~x.index.isin(e.index)]


def stat(x, per=8):
    x = x.dropna()
    if len(x) < 12:
        return f"   n/a          ({len(x):3d})"
    return f"{x.mean() * 1e4:6.1f} bp sh {x.mean() / x.std() * np.sqrt(per):5.2f} ({len(x):3d})"


def row(name, x):
    print(f"    {name:26s} all {stat(x)}   to 2017 {stat(x[:SPLIT])}   2018+ {stat(x[SPLIT:])}"
          f"   win {(x.dropna() > 0).mean() * 100:4.1f}%")


if __name__ == "__main__":
    R = {}
    for s, cost in MARKETS.items():
        r, other = windows(s)
        R[s] = r
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} meetings, {cost} bp round trip"
              f"   other days 24h: {other.mean() * 1e4:.1f} bp, sd {other.std() * 1e4:.0f} bp")
        for w in WINDOWS:
            row(f"{w}, before costs", r[w])
        for w in ("24h", "close", "open"):
            net = r[w] - cost * 1e-4
            print(f"  {w}, after costs")
            row("every meeting", net)
            row("press conference", net[r["press"]])
            row("no press conference", net[~r["press"]])
            row("volatility high", net[r["high"]])
            row("volatility low", net[~r["high"]])
            ma = net.rolling(8).mean().shift(1)
            row("last 8 meetings positive", net[ma > 0])
    r = R["SPXUSD"]
    print("\nS&P 500, 24h window by period (paper: 49 bp 1994-2011, 4.7 bp Apr 2011-2019)")
    for a, b in (("2010-11", "2011-03"), ("2011-04", "2015-12"), ("2016-01", "2019-12"), ("2020-01", "2022-12"),
                 ("2023-01", "2026-12")):
        print(f"    {a} to {b}   24h {stat(r['24h'][a:b])}   close {stat(r['close'][a:b])}"
              f"   open {stat(r['open'][a:b])}")
