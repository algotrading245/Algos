"""An instant-funded account (FundedNext Stellar Instant, rules read on fundednext.com on 2026-10-15): no challenge,
no target, no daily loss limit, a 6% trailing maximum loss, a payout on demand once the account is 5% up or on the
14-day cycle; reward share 70% (80% from tier 3), no fee refund; EAs need an add-on.

Path on the daily results of AurumFunded's legs, started every 3rd trading day 2010-2023: the trailing floor is 6%
under the highest end-of-day equity (taken not to lock, the strict reading); the EA's guard stops at `stop` % under
that peak; size = base x min(cap, max(0.3, cushion / room)), cushion = equity - guard line; a day stop of 3% x1.2
slip.  The first payout is either (a) the first day the account is +5%, or (b) the first 14-day cycle date (10
trading days) on which it is at least +1%.

    python tools/prop_instant.py

Result (cap has no effect here: the cushion under a trailing line never exceeds the room):
  70% edge, 14-day cycle  size 0.3: paid 100%, within 1/2/3/6 months 43/62/74/90%, median 1.4 months, 1.7% at
                          the claim, no account lost; size 0.5: 53/69/77/89%, 1.0 months, lost 1.6%; size 1.0:
                          57/69/75/82%, lost 17%.
  70% edge, at +5%        size 0.3: median 5.5 months; size 0.5: 3.3 months, lost 5.3%.
  half edge + dips, cycle size 0.3: 35/50/59/75%, median 1.9 months, lost 1.1%; size 0.5: lost 13.5%.
  So: size 0.3, claim on the 14-day cycle (preset AurumFunded_FundedNext_instant.set).  The first claim is small
  (about 1.7% of the account at 70% share), so the fee comes back over the following cycles, not the first.
"""
import numpy as np

import backtest_prop as B

TRAIL, GUARD, SLIP = 6.0, 3.0, 1.2


def path(x, start, base, stop, room, cap, mode, limit=500):
    equity = peak = 0.0
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False, 0.0
        cushion = equity - (peak - stop)
        r = x[d] * base * min(cap, max(0.3, cushion / room))
        if r < -GUARD:
            r = -GUARD * SLIP
        equity += r
        if equity <= peak - TRAIL or equity <= peak - stop:
            return None, True, 0.0
        peak = max(peak, equity)
        days = k + 1
        if mode == "5%" and equity >= 5.0:
            return days, False, equity
        if mode == "cycle" and days % 10 == 0 and equity >= 1.0:
            return days, False, equity
    return None, False, 0.0


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -GUARD).to_numpy()
    for case, x in cases.items():
        print(case)
        for mode in ("cycle", "5%"):
            for base, stop, room, cap in ((0.3, 4.5, 4.5, 1.0), (0.5, 4.5, 4.5, 1.0), (0.5, 4.5, 4.5, 1.4),
                                          (0.7, 4.5, 4.5, 1.4), (1.0, 4.5, 4.5, 1.4)):
                res = [path(x, s, base, stop, room, cap, mode) for s in range(0, len(x) - 510, 3)]
                n = len(res)
                t = np.array([d for d, _, _ in res if d is not None])
                amt = np.array([a for d, _, a in res if d is not None])
                fail = sum(f for _, f, _ in res) / n
                print(f"  payout {mode:5s} size {base} cap {cap}: paid {len(t) / n:5.1%} (within 1m {np.sum(t <= 21) / n:5.1%}, "
                      f"2m {np.sum(t <= 42) / n:5.1%}, 3m {np.sum(t <= 63) / n:5.1%}, 6m {np.sum(t <= 126) / n:5.1%}), "
                      f"median {np.median(t) / 21:4.1f} months, profit at claim median {np.median(amt):.1f}%; "
                      f"lost before any payout {fail:5.1%}")
