"""Dollar reversals around the fixings (Krohn, Mueller, Whelan, "Foreign Exchange Fixings and Returns Around the
Clock", Bank of Canada WP 2021-48 / Journal of Finance).

The dollar rises into the Tokyo (9:55 Tokyo), ECB (14:15 Frankfurt) and London (16:00) fixings and falls after them:
about 2 bp a leg before costs on 1999-2019 quotes, smaller after 2014; the paper's own Table X has a trader who
pays the spread losing money.  Legs here, each one round trip:

    pre-T   long dollar   8:30 -> 9:55 Tokyo           post-T  short dollar  9:55 -> 15:00 Tokyo
    pre-E   long dollar   7:00 -> 13:15 London         post-L  short dollar  16:00 -> 21:00 London
            (13:00 from July 2016, when the turn moved a quarter of an hour, Table VI)

    python research/fx_fixings_clock.py

Result on histdata minute bars (2010 to 2026-10), not added to any EA:
  Before costs the equal-weight dollar basket earns 0.9 / 1.2 / 1.1 / 0.4 bp on the four legs (paper 2.0 / 2.1 /
           1.7 / 1.8), and from 2018 only 0.6 / 0.6 / 1.1 / -0.4.  At the full round-trip cost every leg is at or
           below zero in both halves and the four together have Sharpe -0.4 (-1.2 from 2018), as the paper's Table X
           says for a trader who pays the spread.  Yesterday's volatility (Table VIII) does not rescue any leg.
  Starting pre-T at 7:00 Tokyo looks like Sharpe 3 on USDCAD and USDCHF: that is the 17:00 New York rollover
           pushing the bid down, not a return.  Hence the 8:30 start.
"""
import numpy as np
import pandas as pd

from intraday_momentum import SPLIT, at, minutes
from overnight_intraday_reversal import matrix, stats

# +1: rises when the dollar falls; round-trip cost, bp
PAIRS = {"EURUSD": (1, 0.85), "GBPUSD": (1, 1.1), "AUDUSD": (1, 1.1), "NZDUSD": (1, 1.5),
         "USDCAD": (-1, 1.2), "USDCHF": (-1, 1.2), "USDJPY": (-1, 0.85)}
MOVED = "2016-07-01"
LEGS = ("preT", "postT", "preE", "postL")


def windows(symbol, tokyo="08:30"):
    """Log return of the foreign currency against the dollar over each window, and yesterday's minute variance."""
    sign = PAIRS[symbol][0]
    days, p = matrix(symbol, "Asia/Tokyo")
    lp = np.log(p.astype(float))
    t = pd.DataFrame({"preT": at(lp, minutes("09:55")) - at(lp, minutes(tokyo)),
                      "postT": at(lp, minutes("15:00")) - at(lp, minutes("09:55"))}, index=days)
    d = np.diff(lp[:, ::5], axis=1)
    t["vol"] = pd.Series(np.sqrt(np.nanmean(d ** 2, axis=1)), index=days).shift(1)
    days, p = matrix(symbol, "Europe/London")
    lp = np.log(p.astype(float))
    turn = np.where(days < pd.Timestamp(MOVED), at(lp, minutes("13:15")), at(lp, minutes("13:00")))
    e = pd.DataFrame({"preE": turn - at(lp, minutes("07:00")),
                      "postL": at(lp, minutes("21:00")) - at(lp, minutes("16:00"))}, index=days)
    r = t.join(e, how="outer")
    r = r[r.index.dayofweek < 5]
    r[list(LEGS)] *= sign
    return r


def row(name, x):
    x = x.dropna()
    print(f"    {name:30s} all {stats(x)}   to 2017 {stats(x[:SPLIT])}   2018+ {stats(x[SPLIT:])}"
          f"   mean {x.mean() * 1e4:5.2f} / {x[:SPLIT].mean() * 1e4:5.2f} / {x[SPLIT:].mean() * 1e4:5.2f} bp"
          f"   win {(x > 0).mean() * 100:4.1f}%")


def trade(r, leg):
    """Result of a leg in the paper's direction: long the dollar before a fixing, short after it."""
    return -r[leg] if leg.startswith("pre") else r[leg]


if __name__ == "__main__":
    R = {s: windows(s) for s in PAIRS}
    print("Before costs, per pair and leg (paper, 1999-2019: DOL 2.0 / 2.1 / 1.7 / 1.8 bp)")
    for leg in LEGS:
        print(f"  {leg}")
        for s in PAIRS:
            row(s, trade(R[s], leg))
        row("DOL (equal weight)", pd.DataFrame({s: trade(R[s], leg) for s in PAIRS}).mean(axis=1))
    for mult in (0.5, 1.0):
        print(f"\nAfter {mult:.1f} x the round-trip cost of each pair")
        for leg in LEGS:
            print(f"  {leg}")
            net = pd.DataFrame({s: trade(R[s], leg) - mult * PAIRS[s][1] * 1e-4 for s in PAIRS})
            for s in PAIRS:
                row(s, net[s])
            row("DOL (equal weight)", net.mean(axis=1))
            hi = pd.DataFrame({s: R[s]["vol"] > R[s]["vol"].rolling(250, min_periods=60).median() for s in PAIRS})
            hi = hi.reindex(net.index).fillna(False).astype(bool)
            row("DOL, yesterday's vol high", net.where(hi).mean(axis=1))
            row("DOL, yesterday's vol low", net.where(~hi).mean(axis=1))
        both = sum(pd.DataFrame({s: trade(R[s], leg) - mult * PAIRS[s][1] * 1e-4 for s in PAIRS}).mean(axis=1)
                   for leg in LEGS)
        row("all four legs, DOL", both)
