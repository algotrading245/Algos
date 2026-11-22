"""Hour-of-day returns of the hourly series in the repository: AUD/USD, USD/CAD, gold and AUD/CAD (HYDRA_H1, server
time, 2009-06 on, split at 2018) and Bitcoin and Ether (Binance, UTC, 2017-08 on, split at 2022).

An hour counts only if its mean return has the same sign in both halves with |t| above 2 (1.5 for the coins).

    python research/hourly_seasonality.py

Result, nothing added to any EA:
  FX and gold: only USD/CAD 02:00 server time qualifies, at 0.3-0.4 bp an hour, far below the spread.
  Coins: 22:00-23:00 UTC, Bitcoin +5.7 bp to 2021 and +3.3 bp from 2022 (t 2.5 and 2.6), Ether +4.4 and +3.6 bp.
  21:00-24:00 UTC holds 6.1 / 7.9 bp a day over the whole sample but 2.3 / 3.0 bp from 2022 (Sharpe 0.5 before
  cost).  A crypto CFD round trip costs 5 bp or more, so neither pays.  The other UTC blocks change sign between
  halves (US hours +0.6 to 2021, -0.2 / -0.5 from 2022).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"


def scan(r, split, least):
    df = pd.DataFrame({"r": r, "h": r.index.hour, "late": r.index >= pd.Timestamp(split)})
    out = []
    for hh, g in df.groupby("h"):
        a, b = g[~g.late].r, g[g.late].r
        ta, tb = (x.mean() / x.std() * np.sqrt(len(x)) for x in (a, b))
        if np.sign(ta) == np.sign(tb) and min(abs(ta), abs(tb)) > least:
            out.append(f"{hh:02d}h {1e4 * a.mean():+.1f}/{1e4 * b.mean():+.1f} bp (t {ta:+.1f}/{tb:+.1f})")
    return out


if __name__ == "__main__":
    h = pd.read_csv(ROOT / "histdata" / "HYDRA_H1.csv.gz", index_col=0, parse_dates=True)
    for s in h.columns:
        p = h[s].dropna()
        p = p[p.index.dayofweek < 5]
        r = np.log(p).diff()
        r = r[r.index.to_series().diff() == pd.Timedelta(hours=1)]
        print(s, scan(r, "2018-01-01", 2.0))
    for s in ("BTCUSDT", "ETHUSDT"):
        d = pd.read_csv(ROOT / "crypto" / f"{s}_H1.csv.gz")
        d.index = pd.to_datetime(d.time, unit="s")
        r = np.log(d.close).diff().dropna()
        print(s, scan(r, "2022-01-01", 1.5))
        for a0, a1 in ((22, 23), (21, 24)):
            x = r[(r.index.hour >= a0) & (r.index.hour < a1)]
            x = x.groupby(x.index.normalize()).sum()
            print(f"  {a0}:00-{a1}:00 UTC: {1e4 * x.mean():+.1f} bp a day, from 2022 {1e4 * x['2022':].mean():+.1f} bp")
