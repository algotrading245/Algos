"""Time-series momentum on Bitcoin and Ether (the idea of Liu and Tsyvinski 2021, Review of Financial Studies).

Daily closes (00:00 UTC) from the Binance hourly bars in marketdata/crypto.  Each coin holds the sign of its return
over the last `lb` days (long-short, or long-flat), sized to 25% annual volatility (exponential, span 30, up to
yesterday), 10 bp per unit of turnover, which is about the spread of a crypto CFD.  CFD swap is not charged, so
the results are an upper bound.  The paper was not read in full: the test only checks whether a leg of this kind
could add to Hydra.

    python research/crypto_tsmom.py

Result (2018 to 2026-10), not added to any EA:
  long-short: lookback 7 Sharpe 0.57 (1.20 in 2018-21, 0.06 from 2022), 14: 0.89 (1.16, 0.67), 28: 0.85 (1.23,
  0.53), 56: 1.02 (1.41, 0.70).  Long-flat is 0.9 to 1.1 but carries the coins' own rise.  Correlation with the
  Hydra legs is 0.00 to 0.03, but at Sharpe 0.7 since 2022 the leg lifts a Sharpe of 3.0 to about 3.08 before
  swap, and crypto CFD swaps (often tens of percent a year on the notional) can take more than that.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(365)


if __name__ == "__main__":
    P = pd.DataFrame({s: pd.read_csv(ROOT / "crypto" / f"{s}_H1.csv.gz", index_col="time").close
                      for s in ("BTCUSDT", "ETHUSDT")})
    P.index = pd.to_datetime(P.index, unit="s")
    D = P.resample("1D").last().dropna()
    R = D.pct_change()
    vol = R.ewm(span=30).std().shift(1) * np.sqrt(365)
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    for lb in (3, 7, 14, 21, 28, 56):
        for mode in ("long-short", "long-flat"):
            sig = np.sign(D / D.shift(lb) - 1).shift(1)
            if mode == "long-flat":
                sig = sig.clip(lower=0)
            w = sig * 0.25 / vol
            r = (w * R - w.diff().abs() * 10e-4).sum(axis=1).dropna()["2018":]
            c = pd.concat([r, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
            print(f"lookback {lb:2d} {mode:10s}: Sharpe {sharpe(r):+.2f} (2018-21 {sharpe(r[:'2021']):+.2f}, "
                  f"from 2022 {sharpe(r['2022':]):+.2f}), correlation with Hydra {c:+.2f}")
