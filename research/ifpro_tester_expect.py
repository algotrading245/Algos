"""Python expectation for j14 (AurumFunded, Instant Funding PRO guard), calibrated on j12, next to j13.

Same daily book as research/fnext_tester_expect.py (shared leg library, legs on at half j3's size).  j14 is the
Instant Funding PRO preset: size 0.5, cushion room 8.5, cap 1.4, static floor -8.5% until equity first reaches +5%,
then -3.5% for good (InpPropLock*), day stop 3% of the initial balance, InpPropFast with the FAST_IF table until the
lock (absolute size, so PropSize() returns fast / InpSizeMult), the cushion rule below the start.  The 1.7% floating
stop (InpPropFloatPct) acts inside the day and cannot be seen on daily data, so it is not in the model.

    python research/ifpro_tester_expect.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
from fnext_tester_expect import DATA, DAYSTOP, LEAST, walk, holdout  # noqa: E402

TESTER = {"j12": 1.40503, "j13": 0.42431, "j14": 1.09814}   # result.json / summary.md
TESTER_DD = {"j12": 0.0750, "j13": 0.0239, "j14": 0.0671}
FAST_IF = [[1.00, 0.20, 0.20, 0.20, 0.20, 0.40, 0.50, 0.70] + [1.00] * 18 + [0.60],
           [1.00, 0.20, 0.20, 0.20, 0.20, 0.30, 0.50, 0.50, 0.70] + [1.00] * 15 + [0.70, 0.50, 0.30]]
SIZE, ROOM, CAP, STOP, LOCK, LOCKSTOP, FASTDAYS = 0.5, 0.085, 1.4, 0.085, 0.05, 0.035, 42


def walk_ifpro(r):
    eq, peak, dd, hits, worst, locked, lock_day, path = 1.0, 1.0, 0.0, 0, 0.0, False, None, []
    for i, x in enumerate(r.to_numpy()):
        floor = 1.0 - (LOCKSTOP if locked else STOP)
        size = None
        if not locked and eq >= 1.0:
            left = FASTDAYS - i
            b = max(0, min(1, (max(left, 1) - 1) // 21))
            c = int(round((min((eq - 1) * 100, 4.5) + 8.5) / 0.5))
            size = FAST_IF[b][max(0, min(26, c))]
        if size is None:
            size = SIZE * max(LEAST, min(CAP, (eq - floor) / ROOM))
        pnl = eq * size * x
        if pnl <= -DAYSTOP:
            pnl, hits = -DAYSTOP, hits + 1
        worst = min(worst, pnl / eq)
        eq += pnl
        if eq <= floor:
            return eq, dd, worst, hits, pd.Series(path + [eq], r.index[:len(path) + 1]), True, lock_day
        if not locked and eq >= 1.0 + LOCK:
            locked, lock_day = True, r.index[i].date()
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        path.append(eq)
    return eq, dd, worst, hits, pd.Series(path, r.index), False, lock_day


def main():
    legs = holdout.drop(pd.read_csv(DATA / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True))
    legs = legs.drop(columns=["grid", "hold"]).sum(axis=1)
    cand = holdout.drop(pd.read_csv(DATA / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True))
    cand = cand.reindex(legs.index).fillna(0.0)
    book = legs + 0.5 * cand.breakout + 0.275 * cand.noise
    res = {"j12": walk(book.loc["2024-01-01":"2025-10-10"], 0.5, 0.085, 1.4, 0.085, False)[:4],
           "j13": walk(book.loc["2024-01-01":"2025-09-30"], 0.3, 0.045, 1.0, 0.045, True)[:4]}
    r14 = book.loc["2024-01-01":"2025-09-30"]
    eq, dd, worst, hits, path, lost, lock_day = walk_ifpro(r14)
    res["j14"] = (eq, dd, worst, hits)
    print(f"{'run':<5}{'model':>9}{'tester':>9}{'log share':>11}{'model DD':>10}{'tester DD':>11}"
          f"{'worst day':>11}{'day stops':>11}")
    share = {}
    for name, (e, d, w, h) in res.items():
        share[name] = np.log1p(TESTER[name]) / np.log(e)
        print(f"{name:<5}{(e - 1) * 100:>8.1f}%{TESTER[name] * 100:>8.1f}%{share[name]:>11.2f}"
              f"{d * 100:>9.2f}%{TESTER_DD[name] * 100:>10.2f}%{w * 100:>10.2f}%{h:>11}")
    print(f"j14 model: lock (+5%) on {lock_day}; lost {lost}; lowest close after the lock "
          f"{path[path.index > pd.Timestamp(lock_day)].min():.4f}" if lock_day else "j14 model: never locked")
    for k in (0.67, 0.79, 0.87):
        print(f"     j14 at {k:.0%} of the model's log growth: {(eq ** k - 1) * 100:+.1f}%")
    print(f"j14 share / j12 share: {share['j14'] / share['j12']:.2f}")
    # The 1.7% floating stop: daily days where the book lost more than 1.7% of the start at the model's size.
    big = (r14 * 0.5 * 1.4 <= -0.017).sum()
    print(f"days the book at size 0.7 closes below -1.7% (a floor for the floating stop's count): {big}")


if __name__ == "__main__":
    main()
