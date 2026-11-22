"""Dynamic-programming size policy for FTMO's 1-Step Challenge (trailing maximum loss), the exact solution of the
problem a reinforcement-learning agent would be trained on, and the hybrid that proved safe for the 2-Step
(tools/prop_dp.py): the DP size while equity is at or above the start, the cushion rule below it.

Model: state (equity, peak) on a 0.5% grid; each day equity += max(a x r, -2.4) (the EA's 2% day stop x1.2), r drawn
from the funded legs' daily results at size 1 (70% of the edge, 201 quantiles); +10% passes; equity 8.5% under its
peak fails (the EA's stop, 1.5% inside the 10% trailing line) and counts -penalty; T trading days.  The policy is
then run on the real historical sequence (tools/prop_ftmo_1step.py's path: challenge, then the FTMO Account at 0.5,
first payout on the first 10th funded day in profit).

    python tools/prop_dp_1step.py

Result (2026-10-15): not used.  70% edge: cushion rule at 0.5 within 6 / 9 / 12 months 35 / 57 / 79%, median 7.8
months, none failed; hybrid 35 / 69 / 85%, 7.2 months, 2.1% failed.  Half the edge with day stops: cushion 27% within
9 months, none failed; hybrid 40%, 11.1% failed.  A fail penalty of 6 or 12 instead of 3 leaves 1.7% / 9-11% failed.
Under a trailing maximum loss "above the start" is not a safe place to size up - the floor has risen with the
profits - so unlike the 2-Step hybrid this one fails when the edge is weaker than assumed.  The cushion rule stays for
the 1-Step; a DP policy only once live results confirm the edge.
"""
import numpy as np

import backtest_prop as B
import prop_dp as PD
import prop_ftmo_1step as P

SIZES = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0])
STEP, STOP, TARGET, DAYCUT = 0.5, 8.5, 10.0, 2.4


def solve(r, T=189, penalty=3.0):
    peaks = np.arange(0.0, TARGET, STEP)                      # peak below the target
    E = np.arange(-STOP, TARGET, STEP)                        # equity grid (above the stop of peak 0)
    nP, nE = len(peaks), len(E)
    V = np.zeros((nP, nE))
    pol = np.zeros((T + 1, nP, nE), dtype=np.int8)
    for t in range(1, T + 1):
        best = np.full((nP, nE), -np.inf)
        arg = np.zeros((nP, nE), dtype=np.int8)
        for ai, a in enumerate(SIZES):
            dx = np.maximum(a * r, -DAYCUT)                   # (Q,)
            e2 = E[None, :, None] + dx[None, None, :]         # (1, nE, Q)
            pk = np.maximum(peaks[:, None, None], e2)         # (nP, nE, Q)
            win = e2 >= TARGET
            lose = e2 <= pk - STOP
            pi = np.clip(np.round(pk / STEP).astype(int), 0, nP - 1)
            ei = np.clip(np.round((e2 + STOP) / STEP).astype(int), 0, nE - 1)
            ei = np.broadcast_to(ei, pk.shape)
            cont = V[pi, ei]
            val = np.where(win, 1.0, np.where(lose, -penalty, cont)).mean(axis=2)
            better = val > best
            best = np.where(better, val, best)
            arg = np.where(better, ai, arg)
        valid = E[None, :] > peaks[:, None] - STOP            # states that exist
        V = np.where(valid, best, -penalty)
        pol[t] = arg
    return pol, peaks, E


def hybrid_path(x, start, pol, peaks, E, T=189, room=8.5, cap=1.4, limit=750):
    eq = peak = 0.0
    phase, k0 = 1, 0
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False
        floor = peak - 10.0
        stop = floor + 1.5
        if phase == 1:
            if eq >= 0:
                t = max(1, min(T, T - k))
                pi = int(np.clip(round(min(peak, TARGET - STEP) / STEP), 0, len(peaks) - 1))
                ei = int(np.clip(round((eq + STOP) / STEP), 0, len(E) - 1))
                a = SIZES[pol[t, pi, ei]]
            else:
                a = 0.5 * min(cap, max(0.3, (eq - stop) / room))
        else:
            a = 0.5 * min(cap, max(0.3, (eq - stop) / room))
        r = max(x[d] * a, -DAYCUT)
        eq += r
        if eq <= floor or eq <= stop:
            return None, True
        peak = max(peak, eq)
        if phase == 1 and eq >= TARGET and k + 1 >= 4:
            phase, k0, eq, peak = 2, k + 1, 0.0, 0.0
        elif phase == 2 and (k + 1 - k0) >= 10 and (k + 1 - k0) % 10 == 0 and eq > 0:
            return k + 1, False
    return None, False


if __name__ == "__main__":
    pol, peaks, E = solve(PD.returns(0.7))
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -3.0).to_numpy()
    for case, x in cases.items():
        for name, fn in (("cushion rule, size 0.5", lambda s: P.path(x, s, 0.5)),
                         ("hybrid DP / cushion", lambda s: hybrid_path(x, s, pol, peaks, E))):
            res = [fn(s) for s in range(0, len(x) - 760, 5)]
            n = len(res)
            t = np.array([d for d, _ in res if d is not None])
            print(f"{case:16s} {name:22s}: within 6 / 9 / 12 months {np.sum(t <= 126) / n:4.0%} {np.sum(t <= 189) / n:4.0%} "
                  f"{np.sum(t <= 252) / n:4.0%}, median {np.median(t) / 21:.1f} months, failed {sum(f for _, f in res) / n:5.1%}",
                  flush=True)
