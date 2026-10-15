"""Instant Funding PRO (instantfunding.com/instant-funding, read 2026-10-15): no challenge, no profit target, no
daily limit, no consistency rule; maximum loss 10% of the starting balance, and once the account is 5% up the
limit becomes 5% of the starting balance for good ("Smart Drawdown", read here as a floor at -5%); a payout needs
the Smart Drawdown locked in (so +5% reached), 14 days since the first trade, positions closed; then weekly.  No
weekend holding without an add-on; metals and indices 1:5 on funded accounts for now; 80-90% share.

Path on AurumFunded's legs (no grid, no hold) as in tools/prop_instant.py: guard (the EA's final stop) at -8.5%
before the lock and -4.5% after, cushion sizing size x min(cap, max(0.3, cushion / room)), 3% day stop x1.2.
First payout: the first day the account is +5% or more and at least 10 trading days in.

    python tools/prop_instantfunding.py

Result (2026-10-15):
  70% edge          size 0.5: within 1 / 2 / 3 / 6 months 20 / 41 / 57 / 82%, median 2.5 months, lost 0%
                    size 0.7: 28 / 51 / 65 / 85%, median 2.0 months, lost 0%;  size 1.0: 40 / 59 / 70 / 86%, 1.4, lost 2.6%
  half edge + dips  size 0.5: median 3.9 months, lost 0%;  size 0.7: 2.6 months, lost 6.7%;  size 1.0: lost 20%
  Against FundedNext Stellar Instant (1.4 months without a consistency rule, 4.3 with one) this account has no
  consistency rule on its own page, a larger first claim (+5% at 80% share) and room for size 0.5-0.7.  Its EA policy
  is not on the rules page (a review site says only HFT, tick scalping, server exploits and cross-account hedging are
  banned) - to be confirmed before buying.  The "5% of the starting balance" after the lock is read as a floor at -5%.
"""
import numpy as np

import backtest_prop as B

GUARD, SLIP = 3.0, 1.2


def path(x, start, base, room, cap=1.4, limit=500):
    equity, locked = 0.0, False
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False
        floor = -5.0 if locked else -10.0
        stop = floor + 1.5
        r = x[d] * base * min(cap, max(0.3, (equity - stop) / room))
        if r < -GUARD:
            r = -GUARD * SLIP
        equity += r
        if equity <= floor or equity <= stop:
            return None, True
        if equity >= 5.0:
            locked = True
            if k + 1 >= 10:
                return k + 1, False
    return None, False


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -GUARD).to_numpy()
    for case, x in cases.items():
        print(case)
        for base in (0.3, 0.5, 0.7, 1.0):
            for room in (8.5,):
                res = [path(x, s, base, room) for s in range(0, len(x) - 510, 3)]
                n = len(res)
                t = np.array([d for d, _ in res if d is not None])
                lost = sum(f for _, f in res) / n
                print(f"  size {base}: paid {len(t) / n:5.1%}, within 1m {np.sum(t <= 21) / n:4.0%}, 2m {np.sum(t <= 42) / n:4.0%}, "
                      f"3m {np.sum(t <= 63) / n:4.0%}, 6m {np.sum(t <= 126) / n:4.0%}, median {np.median(t) / 21:.1f} months, "
                      f"lost {lost:5.1%}")
