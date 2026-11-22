"""Front-running institutional rebalancing (Harvey, Mazzoleni, Melone, "The Unintended Consequences of Rebalancing",
NBER WP 33554, March 2025 revised January 2026, read in full).

Paper: simulate a 60/40 S&P 500 / 10-year Treasury portfolio.  Threshold signal = equity weight minus 60% for a
portfolio rebalanced when |weight - 60%| >= delta, averaged over delta = 0, 0.1%, ..., 2.5% (eq. 2, B.1).  Calendar
signal = the same for a portfolio rebalanced on the last business day of each month (B.2).  Section 4 strategy:
w = mean(-Threshold / 1.5%, Calendar term), Calendar term = sign(-Calendar) in the last 5 business days of the month,
sign(Calendar four days earlier) on the first business day of the next month, else 0; return = w x (R_SP500 -
R_10y) the next day.  Table 6: 10.2% a year, volatility 9.2%, Sharpe 1.11, skew 5.2 (1997-09 to 2023-03), 0.90
without 2008-09 and March 2020; strongest at quarter-ends and when volatility is high; Table 3: most of it is in
the S&P 500 leg (-0.33 against +0.08 per unit of Threshold).

Here: daily total returns of SPY and TLT (TLT returns x 0.5 as a stand-in for the 10-year note's shorter duration),
2010 on; signals at today's close, position held from today's close to tomorrow's.  The paper's sample ends in
March 2023, so April 2023 on is out of its sample.  Cost: bp per unit of change in |w|.

    python research/rebalancing_frontrun.py

Result (2010-03 to 2026-10), not added to any EA for now:
  Combined, S&P 500 alone at 1 bp: Sharpe 0.91 (1.22 in 2010-17, 0.97 in 2018-23/03, 0.35 after the paper).  The
  Threshold half fails after the paper (-0.43); the Calendar half (month-end, about 60 days a year) holds: S&P 500
  alone 0.91 (1.50, 0.29, 0.95 after the paper), correlation with the Hydra legs -0.01.  CFD swap on the overnight
  position (2-3 bp a day) takes it to 0.69-0.76 (0.11-0.17 in 2018-23/03).  Added to Hydra with the weight best to
  2017 (the grid's top, 1.0): from 2018 3.38 -> 3.32-3.37 (no gain), after the paper 3.41 -> 3.48-3.55.  Fails the
  rule (the 2018+ test); worth re-checking as more months come in - it is the strongest lead from this paper.
  Intraday on the last trading day of the month (one-off check, S&P 500 CFD minute bars, against the month-to-date
  SPY minus half TLT, 1 bp): 15:00-16:00 +1.1 bp (t 0.4), 15:30-16:00 +3.3 bp (t 1.3; -0.02 to 2017), the whole
  day +9.4 bp (t 1.7) - 12 trades a year, Sharpe about 0.3: not used.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"


def signals(rs, rb):
    """Threshold and Calendar signals (equity weight minus 60%) at each close."""
    days = rs.index
    last = pd.Series(days, index=days).groupby(days.to_period("M")).transform("max") == days
    deltas = np.arange(0.0, 0.02501, 0.001)
    w = np.full(len(deltas), 0.6)
    wc = 0.6
    th, ca = np.zeros(len(days)), np.zeros(len(days))
    for i, (a, b) in enumerate(zip(rs.to_numpy(), rb.to_numpy())):
        w = w * (1 + a) / (w * (1 + a) + (1 - w) * (1 + b))
        wc = wc * (1 + a) / (wc * (1 + a) + (1 - wc) * (1 + b))
        th[i] = np.mean(w - 0.6)
        ca[i] = wc - 0.6
        w = np.where(np.abs(w - 0.6) >= deltas, 0.6, w)     # threshold rebalancers reset after today's close
        if last.iloc[i]:
            wc = 0.6
    return pd.Series(th, index=days), pd.Series(ca, index=days), last


def weights(th, ca, last):
    days = th.index
    pos_in_month = pd.Series(1, index=days).groupby(days.to_period("M")).cumsum()
    left = pd.Series(1, index=days).groupby(days.to_period("M")).transform("sum") - pos_in_month   # days after today
    cal = pd.Series(0.0, index=days)
    cal[left < 5] = np.sign(-ca[left < 5])                   # the position held tomorrow, decided at today's close
    first_next = last                                        # tomorrow is the first business day of a new month
    cal[first_next] = np.sign(ca.shift(4)[first_next])
    return (-th / 0.015 + cal) / 2, -th / 0.015, cal


def sharpe(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    spy = pd.read_csv(ROOT / "letf" / "SPY.csv", index_col=0, parse_dates=True).adj
    tlt = pd.read_csv(ROOT / "letf" / "TLT.csv", index_col=0, parse_dates=True).adj
    px = pd.concat([spy, tlt], axis=1, keys=["s", "b"]).dropna()
    rs, rb = px.s.pct_change().fillna(0), 0.5 * px.b.pct_change().fillna(0)
    th, ca, last = signals(rs, rb)
    w, wt, wc = weights(th, ca, last)
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    periods = (("2010-2017", "2010-03", "2017-12"), ("2018-2023/03", "2018-01", "2023-03"),
               ("2023/04 on (out of the paper)", "2023-04", "2026-12"), ("all", "2010-03", "2026-12"))
    for name, pos in (("combined", w), ("Threshold only", wt), ("Calendar only", wc)):
        for leg, ret in (("S&P 500 - 10y", rs - rb), ("S&P 500 alone", rs)):
            for cost in (0.0, 1.0):
                r = (pos.shift(1) * ret - pos.diff().abs().shift(1).fillna(0) * cost * 1e-4)
                cells = "  ".join(f"{p} {sharpe(r[a:b]):+.2f}" for p, a, b in periods)
                c = pd.concat([r, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
                print(f"{name:15s} {leg:14s} cost {cost:.0f} bp: {cells}  | vol {np.sqrt(252) * r.std():.1%}, corr Hydra {c:+.2f}")
