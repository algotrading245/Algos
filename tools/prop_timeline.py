"""From buying an FTMO 2-Step challenge to the first payout, on the daily results of AurumFunded's legs.

A path starts on every trading day 2010-06 to 2026-10 and walks forward with the EA's rules (size 0.5, day stop 3%
x1.2 slip, final stop 8.5% of the initial balance with sizes shrinking within 6.5% of it, a tenth of the size once a
target is hit before the 4 trading days, FTMO's 5% daily and 10% maximum loss): phase 1 to +10%, 2 trading days for
the next account, phase 2 to +5%, 5 trading days for the funded account and its contract, then the first payout
can be claimed 10 trading days (14 calendar days) after the first funded trade if the funded account is in profit,
else on the first later day it is.  `edge` scales the mean daily result (1 = the backtest, 0.7 about what the
Strategy Tester kept, 0.5, 0.33); `dip` books every day below -1.5% as a hit of the 3% day stop (a pessimistic
stand-in for intraday dips).  Daily data cannot see a day that dips through a limit and recovers.

    python tools/prop_timeline.py

Result (paths started every other trading day 2010-06 to 2023-08, three years each), months = 21 trading days:
  edge   pass both  fail   months to pass both (best 10% / median / worst 10%)   first payout median (10% / 90%)
  1.00   100%       0%     3.0 / 6.2 / 11.0                                      7.1 (4.0 / 11.8)
  0.70   100%       0%     3.9 / 9.0 / 16.8                                      10.4 (5.4 / 19.1)
  0.50   97.5%      0%     4.8 / 12.0 / 23.7                                     14.6 (6.4 / 25.6)
  0.33   78.5%      20%    5.2 / 14.5 / 28.4                                     15.4 (6.7 / 28.7)
  With the intraday stand-in: 0.70 9.6 months, 0.50 13.4 months and 5% failed, 0.33 67% passed and 26% failed.
  The Strategy Tester runs (2024-01 start) passed both phases in about 11.5 months, as at edge 0.70.
"""
import numpy as np
import pandas as pd

import backtest_prop as B

SIZE, GUARD, SLIP, DAILY, MOST, ROOM, LEAST, DAYS, COAST = 0.5, 3.0, 1.2, 5.0, 10.0, 6.5, 0.3, 4, 0.1


def path(x, start, limit=750):
    """Trading days to pass phase 1, to pass phase 2, to the first payout, and the profit claimed (% of the
    account); -1 marks a failure at that stage and None a stage not reached within `limit` days."""
    day, out = start, []
    for target, gap in ((10.0, 2), (5.0, 5)):
        equity, first = 0.0, day
        while True:
            if day >= len(x) or day - start >= limit:
                return out + [None]
            r = x[day] * min(1.0, max(LEAST, (equity + MOST) / ROOM))
            if equity >= target:
                r *= COAST
            day += 1
            if r < -GUARD:
                r = -GUARD * SLIP
            equity += r
            if r <= -DAILY or equity <= -MOST:
                return out + [-1]
            if equity >= target and day - first >= DAYS:
                break
        out.append(day - start)
        day += gap
    equity, first = 0.0, day
    while True:
        if day >= len(x) or day - start >= limit:
            return out + [None]
        r = x[day] * min(1.0, max(LEAST, (equity + MOST) / ROOM))
        day += 1
        if r < -GUARD:
            r = -GUARD * SLIP
        equity += r
        if r <= -DAILY or equity <= -MOST:
            return out + [-1]
        if day - first >= 10 and equity > 0:
            return out + [day - start, equity]


def months(d):
    return d / 21.0


if __name__ == "__main__":
    legs = B.legs()
    b = legs.drop(columns=["grid", "hold"]).sum(axis=1) * 100 * SIZE
    b = b[b.index.dayofweek < 5]
    for edge in (1.0, 0.7, 0.5, 0.33):
        for dip in (None, 1.5):
            x = b - b.mean() * (1 - edge)
            if dip:
                x = x.where(x > -dip, -GUARD)
            x = x.to_numpy()
            res = [path(x, s) for s in range(0, len(x) - 760, 2)]
            n = len(res)
            p1 = [r[0] for r in res if len(r) >= 1 and r[0] not in (None, -1)]
            both = [r[1] for r in res if len(r) >= 2 and r[1] not in (None, -1)]
            pay = [(r[2], r[3]) for r in res if len(r) == 4]
            fail = sum(1 for r in res if -1 in r) / n
            q = lambda v, k: months(np.percentile(v, k)) if len(v) else float("nan")
            line = (f"edge {edge:.2f}{' dip' if dip else '    '}: pass both {100 * len(both) / n:5.1f}%, fail {100 * fail:4.1f}%, "
                    f"still open after 3 years {100 * (n - len(pay) - fail * n) / n:4.1f}%  | months to pass both: "
                    f"best 10% {q(both, 10):4.1f}, median {q(both, 50):4.1f}, worst 10% {q(both, 90):4.1f}")
            if pay:
                t, a = zip(*pay)
                line += (f"  | first payout: median {q(t, 50):4.1f} months (10%: {q(t, 10):4.1f}, 90%: {q(t, 90):4.1f}), "
                         f"profit claimed median {np.median(a):.1f}%; payout reached {100 * len(pay) / n:.1f}%")
                for m in (3, 6, 9, 12, 18):
                    line += f"  ≤{m}m {100 * sum(1 for v in t if v <= 21 * m) / n:4.1f}%"
            print(line)
