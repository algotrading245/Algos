"""Check of Singha, Aguilera-Toste, Lahiri, "Forecast-to-Fill: Benchmark-Neutral Alpha and Billion-Dollar Capacity
in Gold Futures (2015-2025)", arXiv 2511.08571 (read in full).

Paper: long-only gold.  y = log price, EMA y~_t = lambda y~_t-1 + (1 - lambda) y_t, slope d_t = y~_t - y~_t-1,
z = (d - mean) / std over the 10-year training window, p_trend = (clip(z, -3, 3) + 3) / 6, m = 1 if P_t > P_t-50,
p_bull = 0.6 p_trend + 0.4 m.  Enter long when p_bull >= 0.52 and d > 0; exit at entry - 2 ATR14, peak - 1.5 ATR14,
after 30 days, or when p_bull < 0.5.  Weight = 15% / sigma_EWMA capped at 2, times (p_bull - 0.5) / 0.5, times a
fractional Kelly f (sizes only).  Walk-forward 10-year train, 6-month test, 2015-2025, cost 0.7 bp.  Reported:
Sharpe 2.88 at T+0, 2.28 at T+1, 2.24 at T+2; max drawdown 0.52% at 0.91% volatility; 65.8% of active days
profitable with gains of 6.0 bp at a mean weight of 0.033 (that is about 1.8% of notional per winning day, more than
gold's average absolute daily move); its own cost table gives Sharpe 0.94 at baseline costs.  lambda is "estimated"
and never given.

Here: COMEX gold front month (marketdata/commod/GC.csv), 2005-2026, signal at the close, position from the next
close (T+1) or the same close (T+0, which earns the return of the day the signal is formed from: look-ahead),
costs 2 bp per unit of turnover, lambda 0.80 / 0.90 / 0.95 (z standardised on the previous 10 years).

    python research/gold_forecast_to_fill.py

Result (2026-10-15): rejected, the headline is look-ahead.  Filled at the close the signal is formed from (T+0) the
rule shows Sharpe 3.0 to 4.4 with drawdowns of 1-3%, the paper's picture; filled at the next close (T+1, tradable)
Sharpe 0.53 to 0.55 with 14-17% drawdowns and a 49-51% hit rate, below buying and holding gold (0.81).  The paper's
own T+1 figure (2.28) cannot be reproduced from its rules.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata" / "commod"


def run(g, lam, lag, cost=0.0002):
    c = g.close
    y = np.log(c)
    d = y.ewm(alpha=1 - lam, adjust=False).mean().diff()
    mu, sd = d.rolling(2520, min_periods=1260).mean().shift(1), d.rolling(2520, min_periods=1260).std().shift(1)
    z = ((d - mu) / sd).clip(-3, 3)
    pb = 0.6 * (z + 3) / 6 + 0.4 * (c > c.shift(50))
    tr = pd.concat([g.high - g.low, (g.high - c.shift()).abs(), (g.low - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    r = c.pct_change()
    sig = np.sqrt((r ** 2).ewm(alpha=0.06).mean())
    wv = (0.15 / np.sqrt(252) / sig).clip(upper=2)
    w = np.zeros(len(c))
    on, entry, peak, age = False, 0.0, 0.0, 0
    for t in range(len(c)):
        if np.isnan(z.iloc[t]) or np.isnan(atr.iloc[t]):
            continue
        p = c.iloc[t]
        if on:
            peak, age = max(peak, p), age + 1
            if p < entry - 2 * atr.iloc[t] or p < peak - 1.5 * atr.iloc[t] or age >= 30 or pb.iloc[t] < 0.5:
                on = False
        if not on and pb.iloc[t] >= 0.52 and d.iloc[t] > 0:
            on, entry, peak, age = True, p, p, 0
        if on:
            w[t] = wv.iloc[t] * max(pb.iloc[t] - 0.5, 0) / 0.5
    w = pd.Series(w, index=c.index)
    pos = w.shift(lag)
    x = (pos * r - cost * pos.diff().abs()).fillna(0)
    return x["2015":"2025-10"]


def stats(x):
    s = x.mean() / x.std() * np.sqrt(252)
    e = x.cumsum()
    act = x[x != 0]
    return (f"Sharpe {s:+.2f}  ret {x.mean() * 252 * 100:5.2f}%  vol {x.std() * np.sqrt(252) * 100:5.2f}%  "
            f"maxDD {(e.cummax() - e).max() * 100:5.2f}%  active-day hit {(act > 0).mean() * 100:4.1f}%")


if __name__ == "__main__":
    g = pd.read_csv(ROOT / "GC.csv", index_col=0, parse_dates=True)
    g = g[g.index.dayofweek < 5].dropna()
    r = g.close.pct_change()["2015":"2025-10"]
    print(f"buy and hold 2015-2025: Sharpe {r.mean() / r.std() * np.sqrt(252):+.2f}")
    for lam in (0.80, 0.90, 0.95):
        for lag in (0, 1, 2):
            print(f"lambda {lam:.2f}  T+{lag}: " + stats(run(g, lam, lag)))
