"""Two hourly checks on HYDRA_H1 (server time, New York + 7): gold's "London bias" and fading the weekend gap.

London bias: gold is said to fall from the London open to the afternoon fix and to rise in Asian hours (a CBS master
thesis, Donati and Jung, and a University of Zurich study found by web search; neither is peer reviewed and neither
was read in full, as the rule is rejected on the data alone).  Short gold from 10:00 (London 8:00) or 9:00 to 17:00
(the 15:00 PM fix) or 16:00, 0.30 USD/oz a round trip.

Weekend gap: after a gap between Friday's last price and Monday's second hour larger than its 52-week standard
deviation, bet on it closing over the next 4 or 10 hours; 1.5 bp a round trip (2.5 bp on AUD/CAD).

    python research/gold_london_and_gaps.py

Result (2009-06 to 2026-10), nothing added to any EA:
  London bias: short 10->17 Sharpe -0.06 (0.27 to 2017, -0.37 from 2018), 9->17 -0.06, 10->16 0.22 (0.79 to 2017,
  -0.31 from 2018), 11->17 -0.16.  The bias was real before 2018 and is gone since.  The one hour that stays
  negative in both halves (16:00-17:00, the hour into the PM auction) is the LBMA auction dip already rejected.
  Weekend gap: t between -1.07 and +1.06 for gold, AUD/USD, USD/CAD and AUD/CAD; no pair is positive in both halves
  with t above 1.
  USD/JPY (one-off check, 2026-10-15, 1.2 bp): 200 gaps, +2.2 bp over 4 hours (t 1.1; 0.3 / 1.2 by half), +1.8 bp
  over 10 hours (t 0.6; 1.4 / -0.4) - nothing.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
SPLIT = "2018-01-01"
COST = {"AUDUSD": 1.5e-4, "USDCAD": 1.5e-4, "AUDCAD": 2.5e-4, "XAUUSD": 1.5e-4}


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


def tstat(x):
    return x.mean() / x.std() * np.sqrt(len(x))


def london(h):
    g = h.XAUUSD.dropna()
    g = g[g.index.dayofweek < 5]
    P = g.groupby([g.index.normalize(), g.index.hour]).last().unstack()
    for a, b in ((10, 17), (9, 17), (10, 16), (11, 17)):
        x = (-(P[b] / P[a] - 1) - 0.3 / P[a]).dropna()
        print(f"short gold {a}:00->{b}:00  Sharpe {sharpe(x):+.2f} (to 2017 {sharpe(x[:SPLIT]):+.2f}, "
              f"from 2018 {sharpe(x[SPLIT:]):+.2f})")


def gaps(h):
    for s in h.columns:
        p = h[s].dropna()
        fri = p[p.index.dayofweek == 4]
        fri = fri.groupby(fri.index.normalize()).last()
        mon = p[p.index.dayofweek == 0]
        rows = []
        for d, f in fri.items():
            m = mon[(mon.index >= d + pd.Timedelta(days=3)) & (mon.index < d + pd.Timedelta(days=4))]
            if len(m) < 12:
                continue
            o = m.iloc[1]
            rows += [(d, n, o / f - 1, m.iloc[min(1 + n, len(m) - 1)] / o - 1) for n in (4, 10)]
        t = pd.DataFrame(rows, columns=["d", "hours", "gap", "fwd"]).set_index("d")
        for n in (4, 10):
            x = t[t.hours == n]
            big = x.gap.abs() > x.gap.rolling(52, min_periods=20).std().shift(1)
            r = (-np.sign(x.gap) * x.fwd - COST[s])[big]
            print(f"{s} gap fade over {n:2d} hours: {len(r)} trades, {1e4 * r.mean():+.1f} bp, t {tstat(r):+.2f} "
                  f"(to 2017 {tstat(r[:SPLIT]):+.2f}, from 2018 {tstat(r[SPLIT:]):+.2f})")


if __name__ == "__main__":
    h = pd.read_csv(ROOT / "histdata" / "HYDRA_H1.csv.gz", index_col=0, parse_dates=True)
    london(h)
    gaps(h)
