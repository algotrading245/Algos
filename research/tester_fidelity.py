"""Does AurumFunded trade as the Python model does?  The Tokyo (USD/JPY) and midday (EUR/USD) legs of the owner's
Strategy Tester run (funded preset, FTMO data, 2024-01 to 2026-10) against tools/backtest_tokyo.py and
tools/backtest_meridian.py on histdata minute bars, day by day; then whether the decayed midday leg should be cut.

Needs the tester's deals (parsed from the HTML report) at the path given; prints the comparison.

    python research/tester_fidelity.py <deals.pkl>

Result (2026-10-15), no change to the EAs:
  midday  model 719 trades, tester 664; 661 on the same days, direction agrees on 96%, correlation of the day's
          result 0.83.  The 58 model-only days are the weeks when US and European clocks differ, which the EA skips
          by design (their mean +0.11 R).
  Tokyo   model 197, tester 179, 178 shared, 96% agree, correlation 0.85; 19 model-only days, same reason.
  So the EA follows the model; the gap seen in the first phase-1 run was the period, not the code.  Recovering the
  skipped weeks would add about 5% more trades of the same edge (+3% Sharpe): not worth rewriting the clock logic
  without a compiler.
  Midday leg by period: Sharpe 1.00 in 2010-17, 0.26 in 2018-21, 0.61 in 2022-26 (Tokyo 1.06, 1.21, 1.20).  In the
  funded leg set the full size is best to 2017 (2.66 against 2.62 at half, 2.48 without), and halving it from 2018
  gains only 3.24 -> 3.29: kept as is.
  The Tokyo rule on the yen crosses (same days, 1.5-2 bp): EUR/JPY Sharpe 0.45 (0.21, 0.15, 1.01 by period),
  GBP/JPY 0.22, AUD/JPY 0.20, CAD/JPY 0.28, correlation 0.6-0.84 with the USD/JPY leg - the effect is in USD/JPY.
  The after-holiday idea on other calendars (the `holidays` package): the day after a Japanese holiday USD/JPY
  falls 3.0 bp from 9:55 to 11:30 Tokyo (t -3.2, both halves), but inside the Tokyo leg's rule the non-gotobi such
  days earn +0.026 R (t 0.7, 0.000 from 2018) and adding them lowers the leg's Sharpe from 2018 (1.21 -> 1.12): the
  signal was the gotobi overlap.  After an English bank holiday GBP/USD and EUR/GBP in the London morning: t -1.6
  to +1.2, signs not stable.  Nothing added.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "tools"))
import backtest_meridian as bm
import backtest_tokyo as bt

if __name__ == "__main__":
    d = pd.read_pickle(sys.argv[1])
    for leg, model in (("midday", bm.trades(cost=0.85)), ("Tokyo", bt.trades(got=1, cost=0.85))):
        m = model["2024-01-01":"2026-10-13"]
        days = pd.DatetimeIndex(d[(d.leg == leg) & (d.dir == "in")].time.dt.normalize().unique())
        md = pd.DatetimeIndex(m.index)
        both = md.intersection(days)
        net = d[d.leg == leg].groupby(d.time.dt.normalize()).net.sum().reindex(both)
        agree = (np.sign(m.r.reindex(both)) == np.sign(net)).mean()
        print(f"{leg}: model {len(m)}, tester {len(days)}, shared {len(both)}, direction agrees {agree:.0%}, "
              f"correlation {m.r.reindex(both).corr(net):.2f}, model-only {len(md.difference(days))}")
