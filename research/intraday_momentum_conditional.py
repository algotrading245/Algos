"""Market intraday momentum under the conditions the paper ties it to (Baltussen, Da, Lammers, Martens 2021).

The paper finds the last-half-hour effect only when option market makers are net short gamma, stronger on jump
days, and reverting over the next days.  The option open interest behind their gamma measure is not available
here, so short gamma is proxied by what goes with it: a high VIX, a VIX above its three-month sister, a market
below its recent high, a falling day.  Also tried: a shorter last window, and fading the last half hour over the
next day.  S&P 500 minute bars, costs in basis points per round trip.

    python research/intraday_momentum_conditional.py

Result on histdata minute bars (2010-11 to 2026-10) at 1 bp, not added to any EA:
  The conditions point the right way up to 2017 (VIX top third: Sharpe 1.1; VIX top third and a falling day, last
  15 minutes: 1.5) and are gone from 2018 (-0.1 and 0.2).  Best 2018+ line is VIX top third and jump day at 0.36.
  A shorter last window is worse after costs.  Fading the last half hour over the next day: under 0.35 everywhere.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import intraday_momentum as M

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
SPLIT = M.SPLIT


def vix(name):
    return pd.read_csv(ROOT / "vixidx" / f"^{name}.csv", index_col=0, parse_dates=True)["close"]


def line(name, pos, ret, cost):
    pos = pos.reindex(ret.index).fillna(0.0)
    on = pos != 0
    x = pos * ret - on * cost * 1e-4
    print(f"  {name:34s} {on.mean() * 100:3.0f}%  gross {(pos * ret)[on].mean() * 1e4:6.2f} bp   "
          f"all {M.stats(x)}   to 2017 {M.stats(x[:SPLIT])}   2018+ {M.stats(x[SPLIT:])}")


def study(symbol="SPXUSD", last=30, cost=1.0):
    r = M.table(symbol, last)
    v, v3 = vix("VIX").shift(1).reindex(r.index).ffill(), vix("VIX3M").shift(1).reindex(r.index).ffill()
    zone, _, c = M.MARKETS[symbol]
    days, p = M.matrix(symbol, zone)
    close = pd.Series(M.at(p, M.minutes(c)), index=days).reindex(r.index)
    below = close.shift(1) / close.shift(1).rolling(20).max() - 1          # yesterday's close against its 20-day high
    hi = v > v.rolling(250, min_periods=60).quantile(2 / 3)
    lo = v < v.rolling(250, min_periods=60).quantile(1 / 3)
    jump = r["rod"].abs() > 2.0 * r["rod"].abs().rolling(250, min_periods=60).mean().shift(1)
    s = np.sign(r["rod"])
    print(f"\n=== {symbol}  last {last} min  cost {cost} bp  {len(r)} days")
    for name, cond in (("all days", s == s), ("VIX top third", hi), ("VIX bottom third", lo),
                       ("VIX above VIX3M", v > v3), ("5% or more below 20-day high", below < -0.05),
                       ("falling day (rod < 0)", r["rod"] < 0), ("rising day (rod > 0)", r["rod"] > 0),
                       ("jump day", jump), ("VIX top third and falling", hi & (r["rod"] < 0)),
                       ("VIX top third and jump", hi & jump), ("below high and falling", (below < -0.05) & (r["rod"] < 0))):
        line(name, s * cond, r["lh"], cost)
    # next day: fade today's last window from the close to the next close and to the next first half hour
    nxt = close.shift(-1) / close - 1
    print("  fade the last window over the next day:")
    for name, cond in (("all days", s == s), ("VIX top third", hi), ("jump day", jump),
                       ("last window with the day", np.sign(r["lh"]) == s)):
        line("  " + name + ", to next close", -np.sign(r["lh"]) * cond, nxt.dropna(), cost)
        line("  " + name + ", overnight+30min", -np.sign(r["lh"]) * cond, r["onfh"].shift(-1).dropna(), cost)


if __name__ == "__main__":
    for last in (30, 15, 5):
        study("SPXUSD", last)
