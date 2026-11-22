"""Does a 40% consistency rule (best day <= 40% of the total profit at the claim) slow AurumFunded's first payout
on FundedNext Stellar Instant?  Sources disagree on whether the rule applies to that account (2026-10-15: two
blogs say no consistency rule, thegodfunded.com says 40%), so both readings are simulated.

Path as tools/prop_instant.py (size 0.3, cushion sizing, 6% trailing loss, guard 4.5, claim on the 14-day cycle
at +1% or more), plus the rule: a cycle date counts only if the best day so far is at most 40% of the profit.

    python tools/prop_consistency.py

Result (2026-10-15), 70% of the edge: without the rule first payout within 1 / 3 / 6 months 43 / 74 / 89%, median
1.4 months; with it 13 / 39 / 65%, median 4.3 months, the first claim then ~4.4% of the account.  Waiting for +2% or
+3% before claiming, or size 0.5 instead of 0.3, does not help (median 4.3-4.8 months; size 0.5 loses 5.5-6.5% of
accounts): the rule is a ratio of the best day to the total and does not depend on size.  So ask FundedNext whether
Stellar Instant has a consistency rule before buying: it decides between ~1.4 and ~4.3 months.  FTMO's median at
the same edge is 9.6 months either way.
"""
import numpy as np

import backtest_prop as B
import prop_instant as PI


def path(x, start, base=0.3, stop=4.5, room=4.5, cap=1.0, rule=0.4, limit=500):
    equity = peak = best = 0.0
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False
        cushion = equity - (peak - stop)
        r = x[d] * base * min(cap, max(0.3, cushion / room))
        if r < -PI.GUARD:
            r = -PI.GUARD * PI.SLIP
        equity += r
        best = max(best, r)
        if equity <= peak - PI.TRAIL or equity <= peak - stop:
            return None, True
        peak = max(peak, equity)
        days = k + 1
        if days % 10 == 0 and equity >= 1.0 and (rule is None or best <= rule * equity):
            return days, False
    return None, False


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    x = (b - b.mean() * 0.3).to_numpy()
    for rule in (None, 0.4):
        res = [path(x, s, rule=rule) for s in range(0, len(x) - 510, 3)]
        n = len(res)
        t = np.array([d for d, _ in res if d is not None])
        lost = sum(f for _, f in res) / n
        print(f"rule {rule}: paid {len(t) / n:.1%}, within 1m {np.sum(t <= 21) / n:.0%}, 3m {np.sum(t <= 63) / n:.0%}, "
              f"6m {np.sum(t <= 126) / n:.0%}, median {np.median(t) / 21:.1f} months, lost {lost:.1%}")
