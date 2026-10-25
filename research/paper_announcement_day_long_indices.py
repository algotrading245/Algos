"""Savor-Wilson 2013 announcement-day premium: long SPXUSD 09:30-16:00 NY on NFP / GDP / ISM / FOMC days.

Calendar from pre_announcement_drift.py (NFP, GDP, ISM first business day, FOMC). CPI/PPI dates are not in
our data, so the set is the four we hold. Cost 1 bp round trip (1x), 1.5 bp stress. Intraday only, no swap.
Writes marketdata/candidates/paper_announcement_day_long_indices.csv and _stress.csv (day, r; every weekday).

    python research/paper_announcement_day_long_indices.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "tools")
from intraday_momentum import at, minutes
from overnight_intraday_reversal import NY, matrix
from pre_announcement_drift import calendar

SYMBOL, COST = "SPXUSD", 1e-4
OUT = "marketdata/candidates/paper_announcement_day_long_indices"


def sharpe(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 20 and x.std() > 0 else float("nan")


def main():
    days, p = matrix(SYMBOL, NY)
    lp = np.log(p.astype(float))
    week = days.dayofweek < 5
    lp, days = lp[week], days[week]
    intr = pd.Series(at(lp, minutes("16:00")) - at(lp, minutes("09:30")), index=days)
    from holdout import drop
    intr = drop(intr)
    days = intr.index
    cal = calendar(days)
    ev = {"NFP": cal["NFP"].notna(), "GDP": cal["GDP"].notna(), "ISM": cal["ISM"].notna(), "FOMC": cal["FOMC"]}
    ev = pd.DataFrame(ev)
    anyev = ev.any(axis=1)
    for tag, mask in (("all4", anyev), ("NFP", ev.NFP), ("GDP", ev.GDP), ("ISM", ev.ISM), ("FOMC", ev.FOMC),
                      ("nfp+ism+fomc", ev.NFP | ev.ISM | ev.FOMC)):
        for lab, sl in (("to2017", days < "2018-01-01"), ("2018on", days >= "2018-01-01")):
            m = mask & sl
            o = sl & ~anyev
            x = intr[m].dropna()
            print(f"{tag:13s} {lab:7s} n {len(x):4d} mean {x.mean()*1e4:6.1f} bp  t {x.mean()/x.std()*np.sqrt(len(x)):5.2f}"
                  f"  others {intr[o].mean()*1e4:5.1f} bp  net Sharpe(on event days, all-days basis) "
                  f"{sharpe(pd.Series(np.where(m, intr - COST, 0.0), index=days)[sl]):5.2f}")
    r1 = pd.Series(np.where(anyev, intr - COST, 0.0), index=days).dropna()
    r15 = pd.Series(np.where(anyev, intr - 1.5 * COST, 0.0), index=days).dropna()
    r2 = pd.Series(np.where(anyev, intr - 2 * COST, 0.0), index=days).dropna()
    print("Sharpe 1x/1.5x/2x full", sharpe(r1), sharpe(r15), sharpe(r2))
    for nm, r in (("", r1), ("_stress", r15)):
        d = pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values})
        d.to_csv(OUT + nm + ".csv", index=False)


if __name__ == "__main__":
    main()
