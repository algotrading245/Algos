"""Volatility-managed sizing of the Hydra and AurumFunded legs (Moreira, Muir, "Volatility Managed Portfolios",
NBER w22208 / Journal of Finance 2017, read in full).

Paper: scale a factor's return by c / (previous month's realized variance) (eq. 1-2), c fixed so the managed
return has the factor's volatility; alpha comes from volatility being forecastable while expected return is not.
Using volatility instead of variance, or capping the weight at 1 or 1.5, keeps the Sharpe ratio and trades less
(section 3.2-3.3, table 4-5).  A common volatility works about as well as each factor's own (section 3.5).

Here: the daily returns of the legs (marketdata/hydra_legs_daily.csv.gz, the EA's sizes).  Every leg trades
intraday and opens new positions each day, so changing the size costs nothing extra.  Variants: inverse variance
or inverse volatility, of the whole portfolio or of each leg, 22 or 63 trading days, weights capped, rebalanced
monthly (the paper) or daily; c set on 2010-2017 only so the managed portfolio has the same volatility there, then
the same c is used on 2018-2026.

    python research/vol_managed_legs.py

Result (2026-10-15): rejected.  Every variant lowers the Sharpe ratio in 2010-2017 and 2018-2026 alike.  Hydra as
is 2.60 / 3.37; the best managed version (inverse 63-day volatility of the portfolio, monthly) 2.37 / 3.27; inverse
variance 2.2-2.4 / 2.6-3.0; per-leg scaling 1.6-2.2 / 1.7-2.7.  AurumFunded as is 2.66 / 3.24, best managed
2.39 / 3.10, and no variant lowers its drawdown or worst day in a useful way.  The reason: unlike the equity factors
of the paper, the legs' mean return rises in step with their past volatility (2010-2017, terciles of the past 22
days' volatility: Sharpe 2.70, 2.76, 2.56 for Hydra, 2.32, 3.11, 2.67 for AurumFunded; returns about proportional
to volatility), because each leg already sizes its trades by volatility and busy markets bring more signals.  So
there is no price of risk to time in either direction; the EA's constant sizing stays.
"""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
TRAIN = slice(None, "2017-12-31")


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def maxdd(x):
    e = x.cumsum()
    return (e.cummax() - e).max()


def weights(x, n, power, cap, monthly):
    """c / sigma^power of the past n days, known before the day it applies to."""
    v = x.rolling(n, min_periods=n // 2).std().shift(1)
    if monthly:
        v = v.groupby(v.index.to_period("M")).transform("first")
    w = 1.0 / v ** power
    c = 1.0 / (x * w)[TRAIN].std() * x[TRAIN].std()
    return (c * w).clip(upper=cap).fillna(0.0)


def line(name, x):
    t, o = x[TRAIN], x["2018":]
    return (f"{name:42s} 2010-17 {sharpe(t):+.2f}  2018-26 {sharpe(o):+.2f} (2021-26 {sharpe(x['2021':]):+.2f})  "
            f"ret/yr {o.mean() * 252 * 100:5.1f}%  maxDD {maxdd(o) * 100:4.1f}%  worst day {o.min() * 100:+.2f}%")


if __name__ == "__main__":
    L = pd.read_csv(CACHE, index_col=0, parse_dates=True)
    L = L[L.index.dayofweek < 5]
    for title, cols in (("Hydra, all eight legs", list(L)), ("AurumFunded, no grid, no hold",
                                                             [c for c in L if c not in ("grid", "hold")])):
        print(title)
        x = L[cols].sum(axis=1)
        print(line("as is", x))
        for power in (2, 1):
            for n in (22, 63):
                for cap in (1.5, 2.0):
                    for monthly in (True, False):
                        tag = f"{'var' if power == 2 else 'vol'} {n}d cap {cap} {'monthly' if monthly else 'daily'}"
                        print(line("portfolio " + tag, x * weights(x, n, power, cap, monthly)))
                        y = sum(L[c] * weights(L[c], n, power, cap, monthly) for c in cols)
                        y = y * x[TRAIN].std() / y[TRAIN].std()
                        print(line("per leg   " + tag, y))
