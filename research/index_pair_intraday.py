"""Intraday pairs trade between the Nasdaq 100 and S&P 500 CFDs: fade the spread's deviation from the open.

The classic pairs idea (Gatev, Goetzmann, Rouwenhorst 2006, daily stocks) on the two US index CFDs, own test with
rules fixed in advance: spread s(t) = Nasdaq return since 9:30 - beta x S&P 500 return since 9:30, beta from the
previous 60 days' daily returns; its usual size at each half hour = mean |s| at that time over the previous 20
days.  At 10:00, 10:30, ... 15:30 New York, if |s| > 2 x usual, sell the leg that ran ahead and buy the other
(beta-weighted), hold to 16:00, one trade a day.  Cost 0.75 bp a leg a round trip.  Bid minute bars, New York clock.

    python research/index_pair_intraday.py

Result (2026-10-15): rejected.  1,278 trades, -2.80 bp a trade after cost (t -3.1), 46% won, Sharpe -0.77 (-1.22
to 2017, -0.51 from 2018).  The spread keeps going within the day rather than reverting, but following it earns
about +1.2 bp before the two legs' ~1.6 bp of cost - nothing either way.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overnight_intraday_reversal import NY, matrix  # noqa: E402

OPEN, CLOSE = 570, 960


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    ds, ps = matrix("SPXUSD", NY)
    dn, pn = matrix("NSXUSD", NY)
    days = ds.intersection(dn)
    S = pd.DataFrame(ps.astype(float), index=ds).loc[days].ffill(axis=1).to_numpy()
    N = pd.DataFrame(pn.astype(float), index=dn).loc[days].ffill(axis=1).to_numpy()
    keep = (days.dayofweek < 5) & ~np.isnan(S[:, OPEN]) & ~np.isnan(N[:, OPEN]) & ~np.isnan(S[:, CLOSE]) & ~np.isnan(N[:, CLOSE])
    days, S, N = days[keep], S[keep], N[keep]
    rs, rn = S[:, CLOSE] / S[:, OPEN] - 1, N[:, CLOSE] / N[:, OPEN] - 1
    ds_ = pd.Series(S[:, CLOSE]).pct_change(); dn_ = pd.Series(N[:, CLOSE]).pct_change()
    beta = (ds_.rolling(60).cov(dn_) / ds_.rolling(60).var()).shift(1).to_numpy()
    checks = list(range(OPEN + 30, CLOSE, 30))
    spread = np.stack([(N[:, m] / N[:, OPEN] - 1) - beta * (S[:, m] / S[:, OPEN] - 1) for m in checks], axis=1)
    usual = pd.DataFrame(np.abs(spread)).rolling(20).mean().shift(1).to_numpy()
    out = np.zeros(len(days))
    n = 0
    for i in range(len(days)):
        if np.isnan(beta[i]) or np.isnan(usual[i]).any():
            continue
        for j, m in enumerate(checks):
            if abs(spread[i, j]) > 2 * usual[i, j]:
                side = -np.sign(spread[i, j])                    # +1: buy Nasdaq, sell beta x S&P
                rN = N[i, CLOSE] / N[i, m] - 1
                rS = S[i, CLOSE] / S[i, m] - 1
                out[i] = side * (rN - beta[i] * rS) - 0.75e-4 * (1 + abs(beta[i]))
                n += 1
                break
    x = pd.Series(out, index=days)
    t = x[x != 0]
    hy = pd.read_csv(Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0,
                     parse_dates=True).sum(axis=1)
    print(f"{n} trades: {t.mean() * 1e4:+.2f} bp a trade (t {t.mean() / t.std() * np.sqrt(len(t)):+.1f}), win {(t > 0).mean():.0%}; "
          f"Sharpe {sharpe(x):+.2f} (to 2017 {sharpe(x[:'2017']):+.2f}, 2018+ {sharpe(x['2018':]):+.2f}); "
          f"corr Hydra {pd.concat([x, hy], axis=1, sort=True).dropna().corr().iloc[0, 1]:+.2f}")
