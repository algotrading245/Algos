"""Search for the size schedule that brings AurumFunded's first FTMO payout soonest with few failures.

Same path as tools/prop_timeline.py (phase 1 +10%, 2 days, phase 2 +5%, 5 days, funded, payout claimable after 10
trading days in profit), but the EA's final stop at -8.5% is the failure line and the size each day is
    base size of the stage x min(cap, max(least, (equity + 8.5) / room))
so it shrinks near the final stop and, with cap above 1, grows once the cushion is wide.  Each schedule is scored
on paths started every 5th trading day 2010-2023: the share with a first payout within 6 and 9 months at 70% of
the backtested edge, and the share failed at half the edge with every day below -1.5% booked as a 3% day stop.

    python tools/prop_sizing.py

Result (sizes phase 1 / phase 2 / funded, room, cap; 70% edge: first payout within 6, 9, 12 months, median;
half edge with the intraday stand-in: failed):
  old EA rule   (0.5, 0.5, 0.5, 6.5, 1.0)   13% 37% 62%, 10.6 months | failed 7.8%
  new default   (0.5, 0.5, 0.5, 8.5, 1.4)   19% 46% 67%,  9.6 months | failed 0.0%
  faster        (0.6, 0.5, 0.5, 8.5, 1.4)   25% 52% 72%,  8.8 months | failed 3.7%
  Larger phase-2 or funded sizes do not help: phase 2 is short anyway and the first payout only needs a profit.
  AurumFunded 1.01 takes the new default (InpPropRoomPct 8.5, InpPropCap 1.4).
"""
import itertools

import numpy as np

import backtest_prop as B

GUARD, SLIP, DAILY, STOP, LEAST, DAYS, COAST = 3.0, 1.2, 5.0, 8.5, 0.3, 4, 0.1


def path(x, start, sizes, room, cap, limit=750):
    """(trading days to the first payout or None, failed)."""
    day = start
    for stage, (target, gap) in enumerate(((10.0, 2), (5.0, 5), (None, 0))):
        equity, first = 0.0, day
        while True:
            if day >= len(x) or day - start >= limit:
                return None, False
            f = sizes[stage] * min(cap, max(LEAST, (equity + STOP) / room))
            r = x[day] * f
            if target is not None and equity >= target:
                r *= COAST
            day += 1
            if r < -GUARD:
                r = -GUARD * SLIP
            equity += r
            if r <= -DAILY or equity <= -STOP:
                return None, True
            if target is None:
                if day - first >= 10 and equity > 0:
                    return day - start, False
            elif equity >= target and day - first >= DAYS:
                break
        day += gap
    return None, False


def score(x, sizes, room, cap, every=5):
    res = [path(x, s, sizes, room, cap) for s in range(0, len(x) - 760, every)]
    n = len(res)
    t = np.array([d for d, _ in res if d is not None])
    return (np.sum(t <= 126) / n, np.sum(t <= 189) / n, np.sum(t <= 252) / n, sum(f for _, f in res) / n,
            np.median(t) / 21 if len(t) else np.nan)


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    real = (b - b.mean() * 0.3).to_numpy()                           # 70% of the edge
    bad = b - b.mean() * 0.5
    bad = bad.where(bad > -1.5, -GUARD).to_numpy()                   # half the edge, pessimistic intraday
    # note: the stand-in is applied before sizing, as a day the guard would have stopped at any size
    rows = []
    for s1, s2, sf, room, cap in itertools.product((0.4, 0.5, 0.6, 0.7, 0.85, 1.0), (0.5, 0.7, 0.9, 1.1),
                                                   (0.5, 0.8), (6.5, 8.5, 11.0), (1.0, 1.4)):
        a = score(real, (s1, s2, sf), room, cap)
        f = score(bad, (s1, s2, sf), room, cap)
        rows.append(((s1, s2, sf, room, cap), a, f))
    print("current EA (0.5, 0.5, 0.5, room 6.5 on the -10% line) is close to sizes (0.5,0.5,0.5) room 6.5 cap 1")
    print("sizes p1/p2/funded, room, cap | 70% edge: payout <=6m <=9m <=12m, failed, median months | half edge + dips: <=9m, failed")
    keep = [r for r in rows if r[2][3] <= 0.05]
    for cfg, a, f in sorted(keep, key=lambda r: -r[1][1])[:15] + [r for r in rows if r[0] == (0.5, 0.5, 0.5, 6.5, 1.0)]:
        print(f"  {cfg} | {a[0]:.0%} {a[1]:.0%} {a[2]:.0%}, failed {a[3]:.1%}, median {a[4]:.1f} | {f[1]:.0%}, failed {f[3]:.1%}")
