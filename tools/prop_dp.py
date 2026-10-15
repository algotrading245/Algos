"""The size policy that maximises the chance of passing both FTMO phases within a deadline: dynamic programming over
(stage, equity, days left) on the empirical distribution of AurumFunded's daily results (the exact solution of the
problem a reinforcement-learning agent would be trained on).

Model: each day equity += a x r, r drawn from the daily results of the funded legs at size 1 (70% of the backtested
edge), cut at the 3% day stop (x1.2 slip); a is chosen from SIZES each day.  Phase 1: +10% passes (then 2 days to the
next account), -8.5% (the EA's final stop) fails; phase 2: +5% passes.  V[t, e] = best probability of passing both
with t trading days left.  The 4-day minimum and the funded wait (10 days in profit) are left out; days are iid
draws, so the policy is then checked on the real historical sequence (tools/prop_sizing.py's paths).

    python tools/prop_dp.py

Result (policies checked on the real sequence of days, paths every 5th day 2010-2023):
  policy                                         70% edge: <=6m  <=9m  <=12m  failed  median | half edge + dips: <=9m  failed
  cushion rule (AurumFunded 1.01)                          31%   57%   76%    0.0%    8.0m   |                  26%   0.0%
  DP, 9-month deadline, no fail penalty                    43%   86%   88%   10.8%    6.1m   |                  53%  44.3%
  DP, 6-month deadline, no fail penalty                    73%   77%   78%   21.5%    4.0m   |                  53%  44.7%
  DP, 9 months, fail counts -3 (fee and restart)           37%   82%   88%    1.0%    6.8m   |                  46%  22.8%
  same, solved on the pessimistic distribution             26%   78%   86%    1.0%    7.4m   |                  42%  19.7%
  same, size capped at 1.0 / 0.85 / 0.7                    39%   79%   85%    0.1%    6.7m   |                  43%  21.9%
                                                            38%   76%   84%    0.1%    6.7m   |                  41%  18.9%
                                                            35%   69%   82%    0.0%    7.0m   |                  36%  16.4%
  A deadline makes catching up when behind optimal, and catching up is what fails when the edge is weak; the
  cushion rule does the opposite near the final stop and never fails.  So: the cushion rule until the live edge is
  known, the deadline policy (about 80% within 9 months, 1% failed) once live results confirm 70% of the edge.
  Hybrid (AurumFunded 1.02, InpPropFast): the table() policy (sizes up to 1.0, compacted to 21-day blocks and 0.5%
  steps) while equity is at or above the phase's start, the cushion rule below it: 70% edge 31% / 67% / 82% within
  6 / 9 / 12 months, median 7.3 months, no failure; half edge + dips 15% / 29% / 40%, no failure (cushion rule alone
  31 / 57 / 76% and 17 / 26 / 37%).  The table alone, everywhere: 39 / 79 / 88%, 0.4% failed, but 34% failed at
  half edge + dips.
"""
import numpy as np

import backtest_prop as B

SIZES = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0, 1.2, 1.5])
STEP, LO = 0.05, -8.5


def returns(edge=0.7, q=201, dip=None):
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    x = b - b.mean() * (1 - edge)
    if dip:
        x = x.where(x > -dip, -3.0)
    x = x.to_numpy()
    return np.quantile(x, (np.arange(q) + 0.5) / q)


def solve(r, T, target1=10.0, target2=5.0, gap=2, penalty=0.0):
    """Value and policy tables for both phases: V2[t, i], V1[t, i] over the equity grid, policy as size indices."""
    def grid(top):
        return np.arange(LO, top + 1e-9, STEP)

    def stage(top, win):
        """win(t) = value of passing with t days left; returns V[t, i] and the argmax action."""
        g = grid(top)
        V = np.zeros((T + 1, len(g)))
        P = np.zeros((T + 1, len(g)), dtype=int)
        for t in range(1, T + 1):
            best = np.full(len(g), -1.0)
            for k, a in enumerate(SIZES):
                d = a * r
                d = np.where(d < -3.0, -3.6, d)
                e = g[:, None] + d[None, :]
                val = np.where(e >= top, win(t - 1), np.where(e <= LO, -penalty,
                               np.interp(e, g, V[t - 1])))
                v = val.mean(axis=1)
                better = v > best
                best[better], P[t, better] = v[better], k
            V[t] = best
        return g, V, P

    g2, V2, P2 = stage(target2, lambda t: 1.0)
    i0 = np.argmin(np.abs(g2))
    g1, V1, P1 = stage(target1, lambda t: max(V2[max(t - gap, 0), i0], -penalty))
    return (g1, V1, P1), (g2, V2, P2)


if __name__ == "__main__":
    r = returns()
    for months in (6, 9):
        T = 21 * months
        (g1, V1, P1), (g2, V2, P2) = solve(r, T)
        i = np.argmin(np.abs(g1))
        print(f"deadline {months} months: best chance of passing both {V1[T, i]:.1%}")
        for t in (T, T // 2, T // 4):
            row = "  ".join(f"{e:+.0f}%:{SIZES[P1[t, np.argmin(np.abs(g1 - e))]]:.2f}" for e in (-7, -5, -3, -1, 0, 2, 4, 6, 8, 9.5))
            print(f"  phase 1, {t:3d} days left, size by equity: {row}")
        for t in (T // 2, T // 4):
            row = "  ".join(f"{e:+.0f}%:{SIZES[P2[t, np.argmin(np.abs(g2 - e))]]:.2f}" for e in (-7, -5, -3, -1, 0, 2, 4))
            print(f"  phase 2, {t:3d} days left, size by equity: {row}")


def table(T=189, penalty=3.0, cap=1.0, edge=0.7):
    """Compact policy for the EA: size by phase, 21-day block of days left (0 = the last block) and 0.5% step of
    equity from -8.5% to the phase target."""
    global SIZES
    keep = SIZES
    SIZES = keep[keep <= cap]
    (g1, V1, P1), (g2, V2, P2) = solve(returns(edge=edge), T, penalty=penalty)
    out = []
    for g, P, top in ((g1, P1, 10.0), (g2, P2, 5.0)):
        rows = []
        for blk in range(T // 21):
            t = min(T, 21 * blk + 11)                      # middle of the block
            rows.append([float(SIZES[P[t, np.argmin(np.abs(g - e))]]) for e in np.arange(LO, top + 1e-9, 0.5)])
        out.append(rows)
    SIZES = keep
    return out


def size_from(tab, phase, days_left, equity):
    rows = tab[phase]
    blk = min(len(rows) - 1, max(0, (days_left - 1) // 21))
    k = int(round((min(max(equity, LO), LO + 0.5 * (len(rows[0]) - 1)) - LO) / 0.5))
    return rows[blk][k]
