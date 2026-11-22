"""Python expectation for j13 (AurumFunded, FundedNext Stellar Instant guard), calibrated on j12.

Both runs use the shared leg library (legs on at 0.0625% breakout risk and 0.1375 noise per index, half of j3's
0.125 / 0.275).  j12 is the FTMO funded preset (size 0.5, static floor -8.5%, room 8.5, cap 1.4) to 2025-10-10; j13
the FundedNext preset (size 0.3, floor 4.5% under the highest day-start equity, room 4.5, cap 1.0) to 2025-09-30.
Both have the day stop at 3% of the initial balance.  PropSize() in AurumFunded.mq5: size x
max(0.3, min(cap, (equity - floor) / (start x room))).

Daily leg results (marketdata/hydra_legs_daily.csv.gz without grid and hold, candidate_legs_daily.csv.gz), compounded
on equity like the EA.  Daily data cannot see intraday dips, so the drawdown is a lower bound.  The tester's share of
the model's log growth on j12 tells how much of j13's model figure to expect.

    python research/fnext_tester_expect.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

DATA = ROOT / "marketdata"
LEAST, DAYSTOP = 0.3, 0.03
TESTER = {"j12": 1.40503, "j13": 0.42431}         # tester net return (result.json / summary.md)
TESTER_DD = {"j12": 0.0750, "j13": 0.0239}


def walk(r, size, room, cap, stop, trailing):
    eq, peak_start, peak, dd, hits, worst, path = 1.0, 1.0, 1.0, 0.0, 0, 0.0, []
    for x in r.to_numpy():
        floor = (peak_start if trailing else 1.0) - stop
        f = max(LEAST, min(cap, (eq - floor) / room))
        pnl = eq * size * f * x
        if pnl <= -DAYSTOP:
            pnl, hits = -DAYSTOP, hits + 1
        worst = min(worst, pnl / eq)
        eq += pnl
        if eq <= floor:
            return eq, dd, worst, hits, pd.Series(path + [eq], r.index[:len(path) + 1]), True
        peak = max(peak, eq)
        peak_start = max(peak_start, eq)
        dd = max(dd, 1 - eq / peak)
        path.append(eq)
    return eq, dd, worst, hits, pd.Series(path, r.index), False


def main():
    legs = holdout.drop(pd.read_csv(DATA / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True))
    legs = legs.drop(columns=["grid", "hold"]).sum(axis=1)
    cand = holdout.drop(pd.read_csv(DATA / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True))
    cand = cand.reindex(legs.index).fillna(0.0)
    book = legs + 0.5 * cand.breakout + 0.275 * cand.noise
    runs = {"j12": (book.loc["2024-01-01":"2025-10-10"], 0.5, 0.085, 1.4, 0.085, False),
            "j13": (book.loc["2024-01-01":"2025-09-30"], 0.3, 0.045, 1.0, 0.045, True)}
    share = {}
    print(f"{'run':<5}{'days':>6}{'model':>9}{'tester':>9}{'log share':>11}{'model DD':>10}{'tester DD':>11}"
          f"{'worst day':>11}{'day stops':>11}")
    for name, (r, size, room, cap, stop, trailing) in runs.items():
        eq, dd, worst, hits, path, lost = walk(r, size, room, cap, stop, trailing)
        share[name] = np.log1p(TESTER[name]) / np.log(eq)
        print(f"{name:<5}{len(r):>6}{(eq - 1) * 100:>8.1f}%{TESTER[name] * 100:>8.1f}%{share[name]:>11.2f}"
              f"{dd * 100:>9.2f}%{TESTER_DD[name] * 100:>10.2f}%{worst * 100:>10.2f}%{hits:>11}"
              + ("  LOST" if lost else ""))
        if name == "j13":
            first = path[path >= 1.05]
            print(f"     model first +5%: {first.index[0].date() if len(first) else 'never'}; "
                  f"lowest close {path.min():.4f} on {path.idxmin().date()}")
            for k in (0.67, 0.74, 0.87):
                print(f"     at {k:.0%} of the model's log growth: {(eq ** k - 1) * 100:+.1f}%")
    print(f"j13 share / j12 share: {share['j13'] / share['j12']:.2f}")


if __name__ == "__main__":
    main()
