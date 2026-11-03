"""Expected Strategy Tester figures for AurumHydra at size 1 (no goal mode), 2024-01 to 2026-10, legs off and on.

Job j4 ran the 5x goal preset for one round at a 100 deposit with most symbol inputs on the other broker's names,
so it tested three legs for one month.  Job j5 runs Hydra at InpSizeMult 1 on FTMO's names from 10,000 instead; this
gives its expectation from the daily leg results (marketdata/hydra_legs_daily.csv.gz, all legs at Hydra's size) and
the candidate legs (candidate_legs_daily.csv.gz: breakout at 0.125% risk a trade, noise per unit weight).  Legs on =
breakout at 0.5% risk (x4) and noise 0.275 per index (0.55), the inputs of j4's compare_set.  Compounded on equity
like the EA, with its 35% drawdown halt.  Daily data cannot see intraday dips, so the drawdown is a lower bound.
The j3 runs kept 67% (legs off) and 74% (legs on) of the model's log growth; the tester column applies 70%.

    python research/hydra_tester_expect.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata"
HALT = 0.35
KEEP = 0.70


def walk(r):
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in r:
        eq *= 1 + x
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        if dd >= HALT:
            break
    return eq, dd


def main():
    legs = pd.read_csv(DATA / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    r = legs.loc["2024-01-01":"2026-10-14"].sum(axis=1)
    c = pd.read_csv(DATA / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True).reindex(r.index).fillna(0.0)
    print(f"{len(r)} days {r.index[0].date()} to {r.index[-1].date()}; legs: {', '.join(legs.columns)}")
    print(f"{'case':<28}{'model':>9}{'max DD':>8}{'Sharpe':>8}{'tester at 70%':>15}{'ret/DD':>8}")
    for name, x in [("legs off", r), ("legs on", r + 4 * c.breakout + 0.55 * c.noise),
                    ("breakout only", r + 4 * c.breakout), ("noise only", r + 0.55 * c.noise)]:
        eq, dd = walk(x)
        sharpe = x.mean() / x.std() * np.sqrt(252)
        tester = np.exp(KEEP * np.log(eq)) - 1
        print(f"{name:<28}{(eq - 1) * 100:>8.0f}%{dd * 100:>7.1f}%{sharpe:>8.2f}{tester * 100:>14.0f}%"
              f"{(eq - 1) / dd:>8.1f}")
    for y in (2024, 2025, 2026):
        ry = r.loc[str(y)]
        print(f"{y}: legs off {((1 + ry).prod() - 1) * 100:.0f}%, Sharpe {ry.mean() / ry.std() * np.sqrt(252):.2f}")


if __name__ == "__main__":
    main()
