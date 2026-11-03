"""The owner's one look at the holdout (tools/holdout.py): how the Hydra legs, plus breakout and noise at their Hydra
defaults, did on the held-out days next to the days before them.  Agents never run this (it refuses when
AURUM_AGENT=1, as run-agent.ps1 sets), and nothing seen here is tuned on.

    python tools/holdout_check.py
"""
import os
import sys

import numpy as np

import holdout
import target_odds

if os.environ.get("AURUM_AGENT") == "1":
    sys.exit("refused: the holdout is for the owner only (tools/holdout.py)")


def stats(r):
    eq = np.cumprod(1 + r)
    dd = 1 - eq / np.maximum.accumulate(eq)
    return 100 * r.mean() * 252, 100 * r.std() * np.sqrt(252), r.mean() / r.std() * np.sqrt(252), 100 * dd.max()


full = target_odds.daily(1.0, with_holdout=True)
n = len(target_odds.daily(1.0, with_holdout=False))
# daily() cuts the mean to the edge, at 1.0 nothing is cut, so the two series line up day for day.
before, held = full[:n], full[n:]
print(f"holdout from {holdout.START.date()}: {len(held)} days; before it {len(before)} days (size 1, sum of legs)")
print("            return/yr   vol/yr   Sharpe   max DD")
for name, r in (("before", before), ("holdout", held)):
    print("%-10s  %8.1f%%  %6.1f%%  %6.2f  %6.1f%%" % (name, *stats(r)))
for goal in target_odds.TARGETS:
    p = target_odds.windows(held)
    if len(p):
        end, dead = target_odds.rounds(p, goal, 2.5, 20.0, before.std(), 0.2)
        print(f"{goal:.0f}x rounds in the holdout (scale 2.5): P(hit) {100 * np.mean(end >= goal - 1e-9):.1f}%  "
              f"P(ruin) {100 * dead.mean():.1f}%  of {len(p)} rounds")
