"""Which two-step challenge brings AurumFunded's first payout soonest: the same path as tools/prop_sizing.py with
each firm's targets, minimum days and first-payout wait (AurumFunded 1.01 sizing: 0.5 x cushion / 8.5, 0.3 to 1.4;
day stop 3%, final stop 8.5%, the firm's 5% daily and 10% static maximum loss).  Rules as reported by third-party
pages on 2026-10-15; check each firm's own page before buying.

    python tools/prop_firms.py

Result (paths every 3rd trading day 2010-2023):
  70% edge          FTMO 10/5 median 9.8 months, 45% within 9 months; FundedNext 8/5 9.0, 51%; FundingPips 8/5 8.8,
                    52%; The5ers 10/5 as FTMO.  No failures.
  half edge + dips  FTMO 15.8 months, 19%; FundedNext 15.2, 21%; FundingPips 15.1, 21%.  No failures.
  An 8% first target saves about a month; the edge decides far more than the firm.  FTMO stays the pick for its
  track record of paying, unless the owner prefers the month.
"""
import numpy as np

import backtest_prop as B

GUARD, SLIP, DAILY, STOP, LEAST, CAP, ROOM, SIZE, COAST = 3.0, 1.2, 5.0, 8.5, 0.3, 1.4, 8.5, 0.5, 0.1
# name: (targets, minimum trading days a phase, trading days to the next account, trading days to the first claim)
FIRMS = {"FTMO 2-Step 10/5": ((10.0, 5.0), 4, (2, 5), 10),
         "FundedNext Stellar 8/5": ((8.0, 5.0), 5, (2, 5), 15),
         "FundingPips 2-Step 8/5": ((8.0, 5.0), 3, (2, 5), 10),
         "The5ers High Stakes 10/5": ((10.0, 5.0), 3, (2, 5), 10)}


def path(x, start, targets, mindays, gaps, wait, limit=750):
    day = start
    for stage in range(3):
        target = targets[stage] if stage < 2 else None
        equity, first = 0.0, day
        while True:
            if day >= len(x) or day - start >= limit:
                return None, False
            r = x[day] * SIZE * min(CAP, max(LEAST, (equity + STOP) / ROOM))
            if target is not None and equity >= target:
                r *= COAST
            day += 1
            if r < -GUARD:
                r = -GUARD * SLIP
            equity += r
            if r <= -DAILY or equity <= -STOP:
                return None, True
            if target is None:
                if day - first >= wait and equity > 0:
                    return day - start, False
            elif equity >= target and day - first >= mindays:
                break
        if stage < 2:
            day += gaps[stage]
    return None, False


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -GUARD).to_numpy()
    for case, x in cases.items():
        print(case)
        for name, (targets, mindays, gaps, wait) in FIRMS.items():
            res = [path(x, s, targets, mindays, gaps, wait) for s in range(0, len(x) - 760, 3)]
            n = len(res)
            t = np.array([d for d, _ in res if d is not None])
            fail = sum(f for _, f in res) / n
            print(f"  {name:26s} first payout within 3m {np.sum(t <= 63) / n:4.0%}, 6m {np.sum(t <= 126) / n:4.0%}, "
                  f"9m {np.sum(t <= 189) / n:4.0%}, 12m {np.sum(t <= 252) / n:4.0%}; median {np.median(t) / 21:4.1f} months "
                  f"(10% {np.percentile(t, 10) / 21:3.1f}, 90% {np.percentile(t, 90) / 21:4.1f}); failed {fail:.1%}")
