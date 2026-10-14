"""Stock returns over the FOMC cycle (Cieslak, Morse, Vissing-Jorgensen, draft of February 2018 / Journal of
Finance 2019).

Day 0 is the scheduled statement day, weekends dropped, holidays kept with a zero return.  Week 0 is days -1..3,
week 1 days 4..8 and so on; days -6..-2 before the next meeting are week -1, days past 33 are dropped.  1994-2016:
the excess return of US stocks is 14 bp a day in week 0, 11 bp in weeks 2, 4 and 6 and -2.5 bp in the odd weeks
(Table 1); holding stocks only in even weeks has Sharpe 0.92 against 0.45 for every day.  Table 7, the "Fed put":
on days whose previous five-day return is in the lowest quintile the even weeks earn 35-36 bp a day and the odd
weeks -5.5 bp; on the other days the even weeks earn 5-9 bp.  Half of the even-week return is that rebound.

Here: 16:00 New York closes of the index CFDs (price index, so the long pays carry = rate + markup - dividends).

    python research/fomc_cycle.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: to 2017 the paper's pattern is there - even weeks 8.6 bp a day (t 2.8), odd weeks 0.6 bp; 2014-2016
           11.3 against -5.4, as its Table 1.  From 2018 it is reversed: even 2.2 bp, odd 6.9 bp (2017-2019 -0.4
           against 9.4, 2020-2022 -1.8 against 5.8).  Week 0 itself earns nothing in either half.  Long in even
           weeks after costs and carry: Sharpe 0.98 to 2017 and 0.06 from 2018, against 0.44 for every day.
  Fed put: to 2017 even-week days after a lowest-quintile week earn 27 bp (t 2.9) and odd-week ones 5 bp, as
           Table 7; from 2018 5 bp and 12 bp.  Traded: Sharpe 1.01 to 2017, 0.10 from 2018.
  Nikkei:  the same story (even 9.6 bp to 2017, 4.0 from 2018; Fed put 36 bp then 0).  DAX: the closes before
           2018 are 17:30 Frankfurt and a few bad quotes dominate its means; nothing to read from it.
  The pattern stopped about when the paper was published.  Not tried as a Hydra leg.
"""
import numpy as np
import pandas as pd

from intraday_momentum import SPLIT, minutes
from overnight_intraday_reversal import NY, matrix, stats
from pre_fomc_drift import FOMC, dates

# the scheduled March 2020 meeting (replaced by the cut of March 15) and the meetings after the data ends
EXTRA = ["2020-03-18", "2026-10-28", "2026-12-09"]
MARKETS = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0}
# what a long index CFD pays a year, percent: policy rate + 2.5 markup - dividend yield (SPXUSD only)
CARRY = {2010: 0.7, 2011: 0.6, 2012: 0.5, 2013: 0.6, 2014: 0.7, 2015: 0.6, 2016: 0.8, 2017: 1.6, 2018: 2.5,
         2019: 2.8, 2020: 1.2, 2021: 1.2, 2022: 2.7, 2023: 6.0, 2024: 6.3, 2025: 5.5, 2026: 5.0}
EVEN, ODD = (0, 2, 4, 6), (-1, 1, 3, 5)


def cycle(days):
    """Day and week of the FOMC cycle for each weekday in `days` (NaN past day 33)."""
    meetings = dates(FOMC).append(pd.DatetimeIndex(EXTRA)).sort_values()
    cal = pd.bdate_range(meetings[0] - pd.Timedelta(days=14), meetings[-1])
    pos = np.searchsorted(cal, meetings)
    k = np.arange(len(cal))
    nxt = np.searchsorted(pos, k, side="left")
    ahead = np.where(nxt < len(pos), pos[np.minimum(nxt, len(pos) - 1)] - k, 99)
    prev = np.where(nxt > 0, k - pos[np.maximum(nxt - 1, 0)], 99)
    on = np.isin(k, pos)
    day = np.where(on, 0, np.where(ahead <= 6, -ahead, prev)).astype(float)
    day[day > 33] = np.nan
    d = pd.Series(day, index=cal).reindex(days)
    return d, np.floor((d + 1) / 5)


def frame(symbol):
    """Per weekday: close-to-close log return (zero on holidays), cycle day and week, and the quintile-1 flags
    of Table 7 from trailing quantiles (750 days) of the 5, 22 and 65 day returns ending the day before."""
    days, p = matrix(symbol, NY)
    lp = pd.DataFrame(np.log(p[:, :minutes("16:00") + 1].astype(float))).ffill(axis=1).iloc[:, -1]
    week = days.dayofweek < 5
    c = pd.Series(lp.values, index=days)[week].ffill()
    r = pd.DataFrame({"r": c.diff()})
    r["day"], r["week"] = cycle(r.index)
    r["nights"] = pd.Series(r.index, index=r.index).diff().dt.days.fillna(1)
    for n in (5, 22, 65):
        past = (c - c.shift(n)).shift(1)
        r[f"q{n}"] = past < past.rolling(750, min_periods=250).quantile(0.2).shift(1)
    return r.iloc[1:]


def cell(x):
    x = x.dropna()
    if len(x) < 20:
        return f"   n/a           ({len(x):4d})"
    return f"{x.mean() * 1e4:6.1f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):5.2f}, {len(x):4d})"


def table(name, x):
    print(f"    {name:38s} all {cell(x)}   to 2017 {cell(x[:SPLIT])}   2018+ {cell(x[SPLIT:])}")


def row(name, x):
    x = x.dropna()
    print(f"    {name:38s} all {stats(x)}   to 2017 {stats(x[:SPLIT])}   2018+ {stats(x[SPLIT:])}"
          f"   in market {(x != 0).mean() * 100:4.1f}%")


def traded(r, on, cost, carry=True):
    """Daily series of being long on the flagged days: half the round trip at each change of position, carry
    for every night held."""
    on = on.reindex(r.index).fillna(False).astype(bool)
    pay = pd.Series(r.index.year, index=r.index).map(CARRY) / 100 / 360 * r["nights"] if carry else 0.0
    turn = on.astype(int).diff().abs().fillna(0)
    return (r["r"] - pay) * on - turn * cost / 2 * 1e-4


if __name__ == "__main__":
    for s, cost in MARKETS.items():
        r = frame(s)
        even, odd = r["week"].isin(EVEN), r["week"].isin(ODD)
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {cost} bp round trip")
        print("  mean daily return by week of the cycle (paper: week 0 +14, weeks 2/4/6 +11, odd weeks -2.5)")
        for w in range(-1, 7):
            table(f"week {w:2d}", r["r"][r["week"] == w])
        table("even weeks", r["r"][even])
        table("weeks 2, 4, 6", r["r"][r["week"].isin((2, 4, 6))])
        table("odd weeks", r["r"][odd])
        table("every day", r["r"])
        print("  by period, even / odd weeks")
        for a, b in (("2010", "2013"), ("2014", "2016"), ("2017", "2019"), ("2020", "2022"), ("2023", "2026")):
            x = r[a:b]
            print(f"    {a}-{b}   even {cell(x['r'][x['week'].isin(EVEN)])}   odd {cell(x['r'][x['week'].isin(ODD)])}")
        print("  Fed put: days after a lowest-quintile 5 day return (paper: even +35, odd -5.5; other days +5-9, -2)")
        for name, q in (("q1 week", r["q5"]), ("q1 week and month", r["q5"] & r["q22"]),
                        ("q1 week, month, 3 months", r["q5"] & r["q22"] & r["q65"])):
            table(f"{name}, even weeks", r["r"][q & even])
            table(f"{name}, odd weeks", r["r"][q & odd])
        table("not q1, even weeks", r["r"][~r["q5"] & even])
        table("not q1, odd weeks", r["r"][~r["q5"] & odd])
        if s != "SPXUSD":
            continue
        print(f"  traded long, after {cost} bp a round trip and carry")
        row("every day", traded(r, r["r"].notna(), cost))
        row("even weeks", traded(r, even, cost))
        row("odd weeks", traded(r, odd, cost))
        row("week 0", traded(r, r["week"] == 0, cost))
        row("q1 week, any week", traded(r, r["q5"], cost))
        row("q1 week, even weeks", traded(r, r["q5"] & even, cost))
        row("q1 week, odd weeks", traded(r, r["q5"] & odd, cost))
        row("q1 week and month, even weeks", traded(r, r["q5"] & r["q22"] & even, cost))
        row("q1 week and month, any week", traded(r, r["q5"] & r["q22"], cost))
