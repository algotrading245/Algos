"""FTMO 1-Step Challenge (rules from several 2026 reviews, not FTMO's own page - to verify: 10% target, 3% daily loss,
10% maximum loss trailing the end-of-day balance (one older review says 6%), Best Day rule: no day more than 50% of
the profit, about 4 trading days) then the FTMO Account (no target, payout on a 14-day cycle).

Path on AurumFunded's legs as in tools/prop_sizing.py: EA day stop 2% (x1.2 slip stays inside the 3%), final stop
1.5% inside the trailing line, cushion sizing, size `base` in the challenge and 0.5 when funded; the challenge ends
at +10% once the best day is at most half the profit and 4 days are traded; the first payout is the first 10th
funded trading day in profit (then 14-day cycles).

    python tools/prop_ftmo_1step.py

Result (2026-10-15), first payout:
  70% edge          size 0.5: within 6 / 9 / 12 months 35 / 57 / 79%, median 7.8 months, failed 0%
                    size 0.7: 46 / 70 / 85%, median 6.5 months, failed 0%;  size 1.0: median 4.8, failed 7.3%
  half edge + dips  size 0.5: median 13.9 months, failed 0%;  size 0.7: failed 27%;  size 1.0: failed 38%
  The Best Day rule costs almost nothing (median 7.7 -> 7.8 at size 0.5): a 10% target spreads over many days.
  So at size 0.5 the 1-Step is a little faster than the 2-Step (9.6 months) with the same safety, and slower than
  the instant accounts (Instant Funding PRO 2.5 months, FundedNext 1.4 or 4.3).  An AurumFunded preset for it would
  be: target 10, trailing true, InpPropMaxStopPct 8.5, InpPropDayStopPct 2.0 (the firm's daily limit is 3%).
  Verify the maximum loss on ftmo.com first (one review says 6%, which would change this).
  With both candidate legs at AurumFunded's volatility, size 0.5: within 6 / 9 / 12 months 39 / 68 / 84%, median 7.1
  months, none failed (half the edge: median 12.9 months, none failed).
"""
import numpy as np

import backtest_prop as B

SLIP = 1.2


def path(x, start, base, day_stop=2.0, trail=10.0, room=8.5, cap=1.4, best_rule=0.5, limit=750):
    eq, peak, best, phase, k0 = 0.0, 0.0, 0.0, 1, 0
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False
        floor = peak - trail
        stop = floor + 1.5
        size = base if phase == 1 else 0.5
        r = x[d] * size * min(cap, max(0.3, (eq - stop) / room))
        if r < -day_stop:
            r = -day_stop * SLIP
        eq += r
        if eq <= floor or eq <= stop:
            return None, True
        peak = max(peak, eq)
        if phase == 1:
            best = max(best, r)
            if eq >= 10.0 and best <= best_rule * eq and k + 1 >= 4:
                phase, k0, eq, peak = 2, k + 1, 0.0, 0.0     # funded account starts fresh
        elif (k + 1 - k0) >= 10 and (k + 1 - k0) % 10 == 0 and eq > 0:
            return k + 1, False
    return None, False


if __name__ == "__main__":
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -3.0).to_numpy()
    for case, x in cases.items():
        print(case)
        for base in (0.5, 0.7, 1.0):
            for rule in (0.5, None):
                res = [path(x, s, base, best_rule=rule if rule else 99) for s in range(0, len(x) - 760, 5)]
                n = len(res)
                t = np.array([d for d, _ in res if d is not None])
                print(f"  size {base} best-day rule {rule}: first payout within 3 / 6 / 9 / 12 months {np.sum(t <= 63) / n:4.0%} "
                      f"{np.sum(t <= 126) / n:4.0%} {np.sum(t <= 189) / n:4.0%} {np.sum(t <= 252) / n:4.0%}, median "
                      f"{np.median(t) / 21:.1f} months, failed {sum(f for _, f in res) / n:5.1%}")
