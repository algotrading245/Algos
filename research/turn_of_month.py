"""Dash for cash: month-end selling pressure and its reversal (Etula, Rinne, Suominen, Vaittinen, Review of
Financial Studies 33(1), 2020).

T is the last trading day of the month.  Pensions and dividends are paid at T and T+1, and with 3-day settlement
cash for T needs a sale by the close of T-4, so institutions sell over T-8..T-4 and the market rebounds over
T-3..T-1; the payments are reinvested over T..T+3 and that reverses over T+4..T+8.  Table 1, S&P 500 July
1995-2013, mean daily return: T-8..T-4 -0.04%, T-3..T-1 0.11%, T -0.04%, T+1..T+3 0.13%, T+4..T+8 -0.03%, all
days 0.04%.  Table 2: the correlation of the T-8..T-4 and T-3..T-1 returns is -0.38 (negative in all 23 markets),
so the rebound is largest after a falling T-8..T-4.  It is 2.5 times larger when T is a Friday, and larger when
funding is tight.  The best entry is the close of T-4.  Table 3: when Europe went from 3- to 2-day settlement in
October 2014 the reversal moved a day closer to the month end.

Here: 16:00 New York closes of the index CFDs.  US stocks settle in 3 days to 2017-09-04, 2 days to 2024-05-27
and 1 day since, so the "settlement" rows move the last selling day from T-4 to T-3 and T-2.

    python research/turn_of_month.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: to 2017 the rebound is as in the paper - T-3..T-1 earns 14.3 bp a day (t 2.7) against 4.3 bp for
           every day, the correlation with T-8..T-4 is -0.39 (paper -0.38), and the three days earn 76 bp after
           a falling T-8..T-4 against 22 bp after a rising one.  From 2018 all of it is gone: 6.0 bp a day
           (t 0.9), correlation -0.01, 9 bp after a falling T-8..T-4 against 31 bp after a rising one.  By
           period the three days earn 60, 32, 57, 7 and -5 bp (2010-13, 2014-17, 2018-20, 2021-23, 2024-26).
  The selling phase is not there in either half (T-8..T-4 earns 1.0 and 2.5 bp a day), nor is the T+4..T+8
           reversal (9.0 bp a day from 2018).  Moving the days with the settlement rule changes nothing:
           rebound 14.4 bp to 2017, 6.1 bp (t 0.7) from 2018.  Friday month ends are weaker, not stronger
           (10 bp over the three days against 48 bp).
  Traded long after costs and carry: T-3..T-1 Sharpe 0.98 to 2017 and 0.22 from 2018, against 0.71 and 0.37
           for every day; the best variant from 2018, T-3..T+3 after a falling T-8..T-4, has 0.45.
  DAX and Nikkei: T-3..T-1 15.5 and 15.8 bp a day to 2017, 1.0 and 4.2 bp from 2018.  The DAX T+2 mean is a
           bad quote.
  Nothing holds in both halves.  Not tried as a Hydra leg.
"""
import numpy as np
import pandas as pd

from fomc_cycle import CARRY, cell, row, table, traded
from intraday_momentum import SPLIT, minutes
from overnight_intraday_reversal import NY, matrix

MARKETS = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0}
T2, T1 = "2017-09-05", "2024-05-28"      # first days of 2-day and 1-day settlement in the United States
PHASES = {"T-8..T-4": (-8, -4), "T-3..T-1": (-3, -1), "T": (0, 0), "T+1..T+3": (1, 3), "T+4..T+8": (4, 8)}


def frame(symbol):
    """Per trading day: close-to-close log return, nights since the previous close, the day's place around the
    turn of the month (t: 0 is T, -1 the day before, 1 the first day of the next month; NaN outside -9..10),
    the month of that T, and `last` = the last day whose sale settles by T under the US rule of the time."""
    days, p = matrix(symbol, NY)
    session = p[:, minutes("09:30"):minutes("16:00") + 1].astype(float)
    open_ = (np.isfinite(session).sum(axis=1) > 200) & (days.dayofweek < 5)
    lp = pd.DataFrame(np.log(session)).ffill(axis=1).iloc[:, -1]
    c = pd.Series(lp.values, index=days)[open_].dropna()
    r = pd.DataFrame({"r": c.diff()})
    r["nights"] = pd.Series(r.index, index=r.index).diff().dt.days.fillna(1)
    month = r.index.to_period("M")
    back = -(r.groupby(month)["r"].cumcount(ascending=False))
    fwd = r.groupby(month)["r"].cumcount() + 1
    r["t"] = np.where(back >= -9, back, np.where(fwd <= 10, fwd, np.nan))
    r["month"] = np.where(back >= -9, month, month - 1)
    r["friday"] = (r.index.dayofweek == 4) & (back == 0)
    r["last"] = np.where(r.index < pd.Timestamp(T2), -4, np.where(r.index < pd.Timestamp(T1), -3, -2))
    full = pd.Series(month, index=r.index).map(pd.Series(month).value_counts()) > 15
    return r[full.values].iloc[1:]


def months(r):
    """Per month end: the return over each phase, the same with the settlement rule of the time (`sell` = the
    five days to the last selling day, `rebound` = from there to T-1), and whether T was a Friday."""
    out = {name: r["r"][r["t"].between(a, b)].groupby(r["month"]).sum() for name, (a, b) in PHASES.items()}
    out["sell"] = r["r"][r["t"].between(r["last"] - 4, r["last"])].groupby(r["month"]).sum()
    out["rebound"] = r["r"][(r["t"] > r["last"]) & (r["t"] < 0)].groupby(r["month"]).sum()
    out["friday"] = r["friday"].groupby(r["month"]).max()
    out["end"] = pd.Series(r.index, index=r.index)[r["t"] == 0].groupby(r["month"]).last()
    return pd.DataFrame(out).dropna().set_index("end")


def corr(m, a, b):
    return "  ".join(f"{name} {x[a].corr(x[b]):5.2f} ({len(x)})"
                     for name, x in (("all", m), ("to 2017", m[:SPLIT]), ("2018+", m[SPLIT:])))


if __name__ == "__main__":
    for s, cost in MARKETS.items():
        r = frame(s)
        m = months(r)
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {cost} bp round trip")
        print("  mean daily return by day around the month end")
        for t in range(-9, 11):
            table(f"T{t:+d}" if t else "T", r["r"][r["t"] == t])
        print("  by phase, mean daily return (paper: -4, 11, -4, 13, -3; all days 4)")
        for name, (a, b) in PHASES.items():
            table(name, r["r"][r["t"].between(a, b)])
        table("every day", r["r"])
        if s != "SPXUSD":
            continue
        print("  with the settlement rule of the time")
        table("five days to the last selling day", r["r"][r["t"].between(r["last"] - 4, r["last"])])
        table("from there to T-1", r["r"][(r["t"] > r["last"]) & (r["t"] < 0)])
        print("  correlation across months (paper: -0.38 and -0.11)")
        print(f"    T-8..T-4 with T-3..T-1      {corr(m, 'T-8..T-4', 'T-3..T-1')}")
        print(f"    sell with rebound           {corr(m, 'sell', 'rebound')}")
        m["buy"] = m["T"] + m["T+1..T+3"]
        print(f"    T..T+3 with T+4..T+8        {corr(m, 'buy', 'T+4..T+8')}")
        print("  three-day return T-3..T-1 by what came before")
        table("after a falling T-8..T-4", m["T-3..T-1"][m["T-8..T-4"] < 0])
        table("after a rising T-8..T-4", m["T-3..T-1"][m["T-8..T-4"] > 0])
        table("T is a Friday", m["T-3..T-1"][m["friday"]])
        table("T is another day", m["T-3..T-1"][~m["friday"]])
        table("rebound after a falling sell phase", m["rebound"][m["sell"] < 0])
        table("rebound after a rising sell phase", m["rebound"][m["sell"] > 0])
        fell = r["month"].map(pd.Series(m["T-8..T-4"].values < 0, index=m.index.to_period("M"))).fillna(False)
        sold = r["month"].map(pd.Series(m["sell"].values < 0, index=m.index.to_period("M"))).fillna(False)
        t, last = r["t"], r["last"]
        print(f"  traded long, after {cost} bp a round trip and carry")
        row("every day", traded(r, r["r"].notna(), cost))
        row("T-3..T-1", traded(r, t.between(-3, -1), cost))
        row("T-3..T+3", traded(r, t.between(-3, 3), cost))
        row("T+1..T+3", traded(r, t.between(1, 3), cost))
        row("T-3..T-1 after a falling T-8..T-4", traded(r, t.between(-3, -1) & fell, cost))
        row("T-3..T+3 after a falling T-8..T-4", traded(r, t.between(-3, 3) & fell, cost))
        row("rebound, settlement rule", traded(r, (t > last) & (t < 0), cost))
        row("rebound to T+3, settlement rule", traded(r, (t > last) & (t <= 3), cost))
        row("rebound after a falling sell phase", traded(r, (t > last) & (t < 0) & sold, cost))
        row("all but T-8..T-4 and T+4..T+8", traded(r, ~(t.between(-8, -4) | t.between(4, 8)), cost))
        print("  T-3..T-1 by period, bp over the three days:  " + "  ".join(
            f"{a}-{b} {m['T-3..T-1'][a:b].mean() * 1e4:5.1f}" for a, b in
            (("2010", "2013"), ("2014", "2017"), ("2018", "2020"), ("2021", "2023"), ("2024", "2026"))))
