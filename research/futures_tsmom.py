"""Time-series momentum on the 20 daily futures in marketdata/commod (the idea of Moskowitz, Ooi, Pedersen 2012).

Each contract holds the sign of its return over the last `lb` days, sized to 40% annual volatility (exponential
volatility, centre of mass 60 days, up to yesterday) and split equally across the contracts with a price; 2 bp per
unit of turnover.  Continuous front-month closes, so roll gaps are in the returns.  The paper was not read in full:
the test only checks whether a leg of this kind could add to Hydra.

    python research/futures_tsmom.py

Result (2006 to 2026-10), not added to any EA:
  lookback 21: Sharpe -0.25    63: 0.17 (0.38 to 2017, -0.16 from 2018)    126: 0.40 (0.44, 0.32)
  252: 0.51 (0.45 to 2017, 0.62 from 2018), correlation with the Hydra legs 0.09.  An uncorrelated leg at Sharpe
  0.5 lifts a Sharpe of 3.0 to about 3.04, which does not change the chance of 5x in a month.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
SPLIT = "2018-01-01"


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


if __name__ == "__main__":
    P = pd.DataFrame({f.stem: pd.read_csv(f, index_col=0, parse_dates=True).close
                      for f in sorted((ROOT / "commod").glob("*.csv"))}).sort_index().ffill(limit=3)
    R = P.pct_change(fill_method=None).clip(-0.3, 0.3)
    vol = R.ewm(com=60).std().shift(1) * np.sqrt(252)
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    for lb in (21, 63, 126, 252):
        pos = np.sign(P / P.shift(lb) - 1).shift(1) * 0.4 / vol
        w = pos.div(pos.notna().sum(axis=1), axis=0)
        r = ((w * R).sum(axis=1) - w.diff().abs().sum(axis=1) * 2e-4)["2006":]
        c = pd.concat([r, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
        print(f"lookback {lb:3d}: Sharpe {sharpe(r):+.2f} (to 2017 {sharpe(r[:SPLIT]):+.2f}, from 2018 "
              f"{sharpe(r[SPLIT:]):+.2f}), correlation with Hydra {c:+.2f}")
