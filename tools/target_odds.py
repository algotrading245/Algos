"""Odds of AurumHydra multiplying an account by 3, 4 or 5 within one month (21 weekdays), and the goal-sizing scale
(InpGoalScale) that gives each target (InpTarget) its best chance.

The account's daily return at size 1 is the sum of the eight Hydra legs (marketdata/hydra_legs_daily.csv.gz, the
EA's default sizes) plus the two library legs at their Hydra defaults (marketdata/candidate_legs_daily.csv.gz:
breakout at 0.125% risk, noise at weight 0.55 = InpNoiseMult 0.275).  Each day the EA sizes like GoalSize() in
mql5/Include/Aurum/Legs.mqh:

    size = min(cap, scale * phi(z) / (x * sqrt(days left)) / day_vol),   x = equity / goal,  z = N^-1(x)

and a round ends at the goal or after 21 weekdays.  Every weekday from 2010 starts one round (overlapping windows),
and the same rounds are run again on a block bootstrap (5-day blocks) for a second opinion.  The edge is cut to
--edge of the backtest (default 0.7, as in the prop tools), and the last 12 months (tools/holdout.py) are left out
unless --holdout is given.

    python tools/target_odds.py                  # table of P(3x), P(4x), P(5x), P(ruin) per target and scale
    python tools/target_odds.py --edge 1.0       # at the full backtested edge

Ruin: equity at or below --ruin of the round's start (default 0.2) at any day.  Leverage is capped by --cap
(InpGoalCap, 20).  An upper bound in one way (no slippage on the larger sizes, daily, not intraday, marking) and a
lower bound in another (no intraday reaction to the goal).
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import holdout

ROOT = Path(__file__).resolve().parent.parent
DAYS = 21
TARGETS = (3.0, 4.0, 5.0)
SCALES = (0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)


def daily(edge, with_holdout=False):
    """Account return a day at size 1 (fraction of equity), with the mean cut to `edge` of the backtest."""
    a = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    b = pd.read_csv(ROOT / "marketdata" / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True)
    b = b.reindex(a.index).fillna(0.0)
    r = a.sum(axis=1) + b.breakout + 0.55 * b.noise
    if not with_holdout:
        r = holdout.drop(r)
    return (r - (1.0 - edge) * r.mean()).to_numpy()


def rounds(paths, goal, scale, cap, vol, ruin):
    """Run one goal round on each row of `paths` (rounds x DAYS daily returns at size 1).  Returns the end
    multiple of each round and whether it was ruined."""
    n = paths.shape[0]
    eq = np.ones(n)
    live = np.ones(n, bool)
    dead = np.zeros(n, bool)
    for d in range(DAYS):
        left = DAYS - d
        x = np.clip(eq / goal, 1e-6, 1 - 1e-6)
        z = norm.ppf(x)
        size = np.minimum(cap, scale * norm.pdf(z) / (x * np.sqrt(left)) / vol)
        eq = np.where(live, eq * np.maximum(0.0, 1.0 + size * paths[:, d]), eq)
        dead |= live & (eq <= ruin)
        live &= (eq < goal) & (eq > ruin)
    return eq, dead


def windows(r):
    return np.lib.stride_tricks.sliding_window_view(r, DAYS)


def bootstrap(r, n, rng, block=5):
    k = -(-DAYS // block)
    starts = rng.integers(0, len(r) - block, size=(n, k))
    return r[starts[:, :, None] + np.arange(block)].reshape(n, -1)[:, :DAYS]


def table(r, cap, ruin, label):
    vol = r.std()
    print(f"\n{label}: {len(r)} days, day vol at size 1 {100 * vol:.2f}%")
    print("target  scale    P(3x)   P(4x)   P(5x)   P(ruin)  median end")
    best = {}
    for goal in TARGETS:
        for s in SCALES:
            end, dead = rounds(PATHS, goal, s, cap, vol, ruin)
            p = [np.mean(end >= g - 1e-9) for g in TARGETS]
            row = (goal, s, *p, dead.mean(), np.median(end))
            print("  %.0fx   %5.2f   %5.1f%%  %5.1f%%  %5.1f%%  %6.1f%%   %.2fx" % (row[0], row[1], *[100 * v for v in row[2:6]], row[6]))
            hit = p[TARGETS.index(goal)]
            if goal not in best or hit > best[goal][1] + 1e-12:
                best[goal] = (s, hit, dead.mean())
        print()
    for g, (s, hit, dead) in best.items():
        print(f"best for {g:.0f}x: scale {s}  P({g:.0f}x) {100 * hit:.1f}%  P(ruin) {100 * dead:.1f}%")
    return best


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge", type=float, default=0.7)
    ap.add_argument("--cap", type=float, default=20.0)
    ap.add_argument("--ruin", type=float, default=0.2)
    ap.add_argument("--holdout", action="store_true", help="include the held-out last 12 months")
    ap.add_argument("--boot", type=int, default=20000)
    a = ap.parse_args()
    r = daily(a.edge, a.holdout)
    PATHS = windows(r)
    table(r, a.cap, a.ruin, f"history, every weekday a round, edge {a.edge}")
    PATHS = bootstrap(r, a.boot, np.random.default_rng(7))
    table(r, a.cap, a.ruin, f"block bootstrap, {a.boot} rounds, edge {a.edge}")
