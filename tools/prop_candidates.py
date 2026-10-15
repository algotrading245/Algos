"""First-payout odds of AurumFunded with the two candidate legs added: the noise-area index leg
(research/noise_area_index.py, half S&P 500 VM 1.5 and half Nasdaq VM 1.0 at 0.75 bp, weight 0.55) and the USD/JPY
London breakout (research/london_breakout.py, 0.8 bp, at 0.125% risk a trade).

Each combination is scaled to the volatility of AurumFunded's legs alone (2010 on), so a change in the odds comes
from the better Sharpe, not from more risk.  The paths are those of tools/prop_instant.py (FundedNext Stellar
Instant, size 0.3, claim on the 14-day cycle) and tools/prop_sizing.py (FTMO 2-step, AurumFunded 1.01 sizes 0.5 /
0.5 / 0.5, room 8.5, cap 1.4), at 70% of the backtested edge and at half the edge with every day under -1.5%
booked as a 3% day stop.

    python tools/prop_candidates.py

Result (2026-10-15), each at AurumFunded's volatility:
                    instant (70% edge)           FTMO (70% edge)               half edge + dips
  AurumFunded       1m 43%, 3m 74%, 1.4 months   9m 46%, 12m 67%, 9.6 months   instant lost 1.1%, FTMO failed 0.0%
  + breakout        43%, 74%, 1.4                50%, 71%, 9.0                 2.6%, 5.8%
  + noise           45%, 75%, 1.4                48%, 72%, 9.3                 3.4%, 0.0%
  + both            45%, 75%, 1.4                50%, 73%, 9.0                 3.4%, 0.1%
  The legs lift the Sharpe (3.24 -> 3.30 / 3.43 / 3.48 from 2018) and the FTMO odds by a few points, leave the
  instant account's 1.4 months as it is, and under the pessimistic case add failures - the breakout's losses come
  in runs (its own drawdown is 9.2% at 7.1% volatility).  Neither goes into AurumFunded's prop presets before its
  Strategy Tester run; of the two the noise leg is the safer for a challenge.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
import backtest_prop as B  # noqa: E402
import prop_instant as PI  # noqa: E402
import prop_sizing as PS  # noqa: E402

CACHE = ROOT / "marketdata" / "candidate_legs_daily.csv.gz"


def candidates(index):
    if CACHE.exists():
        c = pd.read_csv(CACHE, index_col=0, parse_dates=True)
    else:
        from london_breakout import run as breakout
        from noise_area_index import run as noise
        spx, _ = noise("SPXUSD", vm=1.5, cost_bp=0.75)
        nsx, _ = noise("NSXUSD", vm=1.0, cost_bp=0.75)
        T = breakout("USDJPY", "side")
        r = T.r - 0.8e-4 / T.rel
        c = pd.DataFrame({"noise": 0.5 * spx + 0.5 * nsx,
                          "breakout": pd.Series(r.to_numpy(), index=T.day).groupby(level=0).sum() * 0.00125})
        c.to_csv(CACHE)
    return c.reindex(index).fillna(0.0)


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


if __name__ == "__main__":
    f = B.legs().drop(columns=["grid", "hold"]).sum(axis=1)
    f = f[f.index.dayofweek < 5]
    c = candidates(f.index)
    combos = {"AurumFunded": f, "+ breakout": f + c.breakout, "+ noise": f + 0.55 * c.noise,
              "+ both": f + c.breakout + 0.55 * c.noise}
    for name, x in combos.items():
        x = x * f.std() / x.std() * 100
        real = (x - x.mean() * 0.3).to_numpy()
        bad = x - x.mean() * 0.5
        bad = bad.where(bad > -1.5, -PI.GUARD).to_numpy()
        print(f"{name}: Sharpe 2010-17 {sharpe(x[:'2017']):.2f}, 2018+ {sharpe(x['2018':]):.2f}")
        for case, y in (("70% edge", real), ("half edge + dips", bad)):
            res = [PI.path(y, s, 0.3, 4.5, 4.5, 1.0, "cycle") for s in range(0, len(y) - 510, 3)]
            n = len(res)
            t = np.array([d for d, _, _ in res if d is not None])
            lost = sum(fl for _, fl, _ in res) / n
            ft = PS.score(y, (0.5, 0.5, 0.5), 8.5, 1.4)
            print(f"  {case:16s} instant: within 1m {np.sum(t <= 21) / n:4.0%}, 3m {np.sum(t <= 63) / n:4.0%}, median "
                  f"{np.median(t) / 21:.1f} months, lost {lost:4.1%} | FTMO: payout <=6m {ft[0]:4.0%}, <=9m {ft[1]:4.0%}, "
                  f"<=12m {ft[2]:4.0%}, median {ft[4]:.1f} months, failed {ft[3]:4.1%}", flush=True)
