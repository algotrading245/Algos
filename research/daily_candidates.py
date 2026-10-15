"""Daily-data candidates for a new Hydra leg, all rejected, and a check of the leg weights.

    python research/daily_candidates.py

Each line: Sharpe over 2010-2026-10, to 2017, from 2018, correlation with the Hydra legs.  Costs 2 bp a round trip
on the index, 4 bp on gold/silver, 5 bp on single stocks.  No paper was read in full for these: they were quick
checks of known ideas, and none is used.

Result:
  SPY on the day before an exchange holiday            -0.06 (0.48 to 2017, -0.41 from 2018)
  SPY while VIX/VIX3M < 1 (or < 0.9)                    0.89 (0.73), but below holding SPY itself: it is the index's
                                                         own return, not a new edge
  gold/silver ratio fade at a 20-day z of 1.5           -0.35
  SPY on Monday after a falling Friday                   0.05
  SPY 1, 3, 5 days after VIX rises 20% in a day          0.28, 0.05, 0.03
  weekly reversal, 100 most traded US stocks            0.44 before cost, 0.18 at 5 bp (-0.09 to 2017)
  daily reversal, same stocks                           0.00 before cost
  gold on the last weekday of the month against the month's gold or stock move, 16:00-18:00, 16:00-19:00 server
  time, and the whole day: t from -0.27 to +1.40, signs differ between the halves (hourly bars of HYDRA_H1; a
  one-off check, not repeated by this script)
  SPY in the week of the monthly option expiry (third Friday) and the week after (one-off check): 6.6 and 7.4 bp a
  day to 2017 against 4.2 on other days, -1.7 and 7.8 from 2018 against 8.8 - nothing.
Leg weights: the maximum-Sharpe weights (correlations shrunk to 0 by half or fully) fitted to 2017 give 3.11 to 3.24
from 2018 against 3.37 for the EA's weights; fitted from 2018 they give 2.78 to 2.82 to 2017 against 2.60.  On the
whole history 3.10 against 3.01.  No change to the weights: the gain is within the noise.
"""
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
SPLIT = "2018-01-01"


def sharpe(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def read(p):
    return pd.read_csv(ROOT / p, index_col=0, parse_dates=True)


def line(name, r, hydra):
    c = pd.concat([r, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
    print(f"{name:34s} Sharpe {sharpe(r):+.2f} (to 2017 {sharpe(r[:SPLIT]):+.2f}, from 2018 {sharpe(r[SPLIT:]):+.2f}), "
          f"correlation {c:+.2f}")


def index_rules(hydra):
    spy = read("letf/SPY.csv")
    vix, v3 = read("vixidx/^VIX.csv").close, read("vixidx/^VIX3M.csv").close
    cc, idx = spy.adj.pct_change(), spy.index
    gap = (pd.Series(idx[1:].append(pd.DatetimeIndex([idx[-1] + pd.Timedelta(days=1)])), index=idx)
           - idx.to_series()).dt.days
    pre = (((gap >= 2) & (idx.dayofweek != 4)) | (gap >= 4)).shift(1, fill_value=False).astype(float)
    line("SPY before a holiday", pre * (cc - 2e-4), hydra)
    w = ((vix / v3).reindex(idx).shift(1) < 1.0).astype(float)
    line("SPY while VIX/VIX3M < 1", w * cc - w.diff().abs() * 2e-4, hydra)
    line("SPY held", cc, hydra)
    w = ((cc < 0) & (idx.dayofweek == 4)).shift(1, fill_value=False).astype(float)
    line("SPY Monday after a falling Friday", w * (cc - 2e-4), hydra)
    spike = (vix.pct_change() > 0.2).reindex(idx, fill_value=False).shift(1, fill_value=False).astype(float)
    for h in (1, 3, 5):
        w = spike.rolling(h, min_periods=1).max()
        line(f"SPY {h} days after VIX +20%", w * cc - w.diff().abs() * 2e-4, hydra)
    gc, si = read("commod/GC.csv").close, read("commod/SI.csv").close
    lr = np.log(gc / si).dropna()
    z = (lr - lr.rolling(20).mean()) / lr.rolling(20).std()
    w = (-np.sign(z) * (z.abs() > 1.5)).shift(1)
    line("gold/silver fade", (w * (gc.pct_change() - si.pct_change()) - w.diff().abs() * 4e-4)["2010":], hydra)


def stock_reversal(hydra):
    C, V = {}, {}
    for f in sorted((ROOT / "stocks").glob("*.csv")):
        d = pd.read_csv(f, index_col=0, parse_dates=True)
        if len(d) >= 1000:
            C[f.stem], V[f.stem] = d.adj, d.close * d.volume
    C = pd.DataFrame(C).sort_index()
    V = pd.DataFrame(V).reindex(C.index)
    R = C.pct_change(fill_method=None)
    liq = V.rolling(60).mean().rank(axis=1, ascending=False) <= 100
    for lb in (1, 5):
        past = C / C.shift(lb) - 1
        past = past.sub(past.where(liq).mean(axis=1), axis=0).where(liq)
        w = -past.div(past.abs().sum(axis=1), axis=0)
        if lb == 5:
            w = w[w.index.dayofweek == 4].reindex(C.index).ffill(limit=4)
        w = w.shift(1)
        for cost in (0.0, 5e-4):
            r = ((w * R).sum(axis=1) - w.diff().abs().sum(axis=1) * cost)["2010-03":]
            line(f"reversal {lb}d, {cost * 1e4:.0f} bp", r, hydra)


def weights():
    d = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    d = d[d.index.dayofweek < 5]

    def tangency(X, shrink):
        S = X.cov().to_numpy()
        S = (1 - shrink) * S + shrink * np.diag(np.diag(S))
        w = np.clip(np.linalg.solve(S, X.mean().to_numpy()), 0, None)
        return w / w.mean()

    a, b = d[:SPLIT], d[SPLIT:]
    for shrink in (0.0, 0.5, 1.0):
        print(f"weights fitted to 2017, shrink {shrink}: from 2018 {sharpe(b @ tangency(a, shrink)):.2f} "
              f"(EA {sharpe(b.sum(axis=1)):.2f}); fitted from 2018: to 2017 {sharpe(a @ tangency(b, shrink)):.2f} "
              f"(EA {sharpe(a.sum(axis=1)):.2f})")
    N = NormalDist()
    for s in (3.0, 3.2, 3.4, 4.0, 5.0):
        print(f"best chance of 5x in a month at Sharpe {s}: {N.cdf(N.inv_cdf(0.2) + s * np.sqrt(1 / 12)):.0%}")


if __name__ == "__main__":
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    index_rules(hydra)
    stock_reversal(hydra)
    weights()
