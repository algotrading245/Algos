"""VWAP trend trading on stock-index CFDs (Zarattini, Aziz, "Volume Weighted Average Price (VWAP) The Holy Grail for
Day Trading Systems", 2023-11-13, SSRN 4631351, read in full from concretumgroup.com).

The paper's rule (section 3): from 9:31 New York be long while the last 1-minute close is above the session VWAP
(regular hours only) and short while it is below, reversing on each close across; flat at 16:00.  QQQ 2018-01 to
2023-09: Sharpe 2.1, 43% a year, volatility 18%, about 15 trades a day, hit ratio 17%, commission $0.0005 a share
(near nothing).  Figure 7: the profit comes from 9:30-12:00 and 15:00-16:00.  Table 5: plain moving averages do
much worse (SMA9 1.3, SMA200 0.9).

Here: histdata bid minute bars, no volume, so the time-weighted average of the closes since 9:30 stands in for the
VWAP.  Each reversal pays one round trip of `cost` bp (closing one side and opening the other), the day's first entry
and last exit one more.  Size as in research/noise_area_index.py (2% daily volatility target, at most 4x), so the
two can be compared; the paper's 100%-of-equity sizing gives the same Sharpe.

    python research/vwap_trend_index.py

Result (2010-11 to 2026-10), not added to any EA:
  Before costs it replicates on the Nasdaq: Sharpe 1.19, 1.70 from 2018 (the paper's years), but 0.58 to 2017;
  S&P 500 0.85 (0.34 | 1.22).  It reverses 18 times a day, so a CFD spread kills it: Nasdaq 0.28 at 0.25 bp a
  round trip, -0.58 at 0.5 bp, -1.41 at 0.75 bp; the paper's best hours only (9:31-12 and 15-16) do no better
  (-0.40 at 0.5 bp).  The noise-area rule (research/noise_area_index.py) trades once a day and survives costs.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from noise_area_index import SESSIONS, line
from overnight_intraday_reversal import matrix


def run(symbol, cost_bp=0.75, hours=None, target=0.02, cap=4.0, look=14):
    """hours: list of (from, to) minutes of the day in which the rule may hold a position (None = the whole session)."""
    zone, OPEN, CLOSE = SESSIONS[symbol]
    days, p = matrix(symbol, zone)
    p = pd.DataFrame(p.astype(float)).ffill(axis=1).to_numpy()
    keep = days.dayofweek < 5
    days, p = days[keep], p[keep]
    s = p[:, OPEN:CLOSE + 1]
    ok = ~np.isnan(s).any(axis=1)
    days, s = days[ok], s[ok]
    twap = np.cumsum(s, axis=1) / np.arange(1, s.shape[1] + 1)
    pos = np.sign(s - twap)[:, 1:-1]                 # held over the next minute, from 9:31 to 15:59
    if hours:
        mins = np.arange(OPEN + 1, CLOSE)
        allow = np.zeros(len(mins), bool)
        for a, b in hours:
            allow |= (mins >= a) & (mins < b)
        pos = pos * allow
    r = s[:, 2:] / s[:, 1:-1] - 1
    gross = (pos * r).sum(axis=1)
    full = np.concatenate([np.zeros((len(pos), 1)), pos, np.zeros((len(pos), 1))], axis=1)
    turns = np.abs(np.diff(full, axis=1)).sum(axis=1) / 2   # round trips: a reversal counts one
    net = gross - turns * cost_bp * 1e-4
    c = s[:, -1]
    dvol = pd.Series(c / np.r_[np.nan, c[:-1]] - 1).rolling(look).std().shift(1).to_numpy()
    size = np.where(dvol > 0, np.minimum(cap, target / dvol), 0.0)
    return pd.Series(net * size, index=days), pd.Series(turns, index=days)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "marketdata"
    hydra = pd.read_csv(root / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    for sym in ("NSXUSD", "SPXUSD"):
        print(sym)
        for cost in (0.0, 0.25, 0.5, 0.75):
            x, n = run(sym, cost)
            line(f"all day, cost {cost} bp", x, n, hydra)
        for cost in (0.0, 0.5, 0.75):
            x, n = run(sym, cost, hours=[(570, 720), (900, 960)])
            line(f"9:31-12 and 15-16, cost {cost} bp", x, n, hydra)
