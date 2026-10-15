"""Dynamic-programming size policy for Instant Funding PRO's first payout (static -10% floor until +5%, payout at +5%
after 14 days), and the hybrid that was safe on the FTMO 2-Step's static floor: the DP size at or above the start,
the cushion rule (size 0.5) below it.

Model: equity on a 0.25% grid; each day equity += max(a x r, -3.6) (the EA's 3% day stop x1.2), r from the funded
legs at size 1 (70% of the edge); +5% pays (the 10-day minimum is left out of the DP, kept in the check), -8.5% fails
and counts -penalty; T trading days.  Checked on the real historical sequence with tools/prop_instantfunding.py's
rules.

    python tools/prop_dp_instantfunding.py

Result (2026-10-15), first payout:
  70% edge          cushion 0.5: within 1 / 2 / 3 months 20 / 41 / 57%, median 2.5 months, none lost
                    hybrid T=42: 29 / 50 / 62%, median 2.0 months, none lost (T=63: 2.1; T=126: 3.2 - too long a
                    horizon sizes down)
  half edge + dips  cushion 0.5: median 3.9 months, none lost;  hybrid T=42: 2.9 months, none lost
  The static floor keeps "above the start" a safe place to size up, as on the FTMO 2-Step.  Compacted to 21-day
  blocks and 0.5% steps (FAST_IF in AurumFunded 1.03, used with InpPropFast when the target is 0 and the lock is on)
  the table gives the same: 28 / 50 / 62%, median 2.0, none lost; half the edge 2.9, none lost.  The Instant Funding
  preset switches it on (InpPropFast=true, InpPropFastDays=42).
"""
import numpy as np

import backtest_prop as B
import prop_dp as PD

SIZES = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0])
STEP, STOP, TARGET, DAYCUT = 0.25, -8.5, 5.0, 3.6


def solve(r, T=63, penalty=3.0):
    E = np.arange(STOP, TARGET, STEP)
    V = np.zeros(len(E))
    pol = np.zeros((T + 1, len(E)), dtype=np.int8)
    for t in range(1, T + 1):
        vals = []
        for a in SIZES:
            e2 = E[:, None] + np.maximum(a * r, -DAYCUT)[None, :]
            idx = np.clip(np.round((e2 - STOP) / STEP).astype(int), 0, len(E) - 1)
            vals.append(np.where(e2 >= TARGET, 1.0, np.where(e2 <= STOP, -penalty, V[idx])).mean(axis=1))
        vals = np.array(vals)
        pol[t] = vals.argmax(axis=0)
        V = vals.max(axis=0)
    return pol, E


def path(x, start, pol, E, T=63, room=8.5, cap=1.4, limit=500):
    eq, locked = 0.0, False
    for k in range(limit):
        d = start + k
        if d >= len(x):
            return None, False
        floor = -5.0 if locked else -10.0
        stop = floor + 1.5
        cush = 0.5 * min(cap, max(0.3, (eq - stop) / room))
        if eq >= 0 and not locked:
            t = max(1, T - k)
            a = SIZES[pol[min(t, T), int(np.clip(round((eq - STOP) / STEP), 0, len(E) - 1))]]
        else:
            a = cush
        r = max(x[d] * a, -DAYCUT)
        eq += r
        if eq <= floor or eq <= stop:
            return None, True
        if eq >= 5.0:
            locked = True
            if k + 1 >= 10:
                return k + 1, False
    return None, False


if __name__ == "__main__":
    import prop_instantfunding as IF
    b = B.legs().drop(columns=["grid", "hold"]).sum(axis=1) * 100
    b = b[b.index.dayofweek < 5]
    cases = {"70% edge": (b - b.mean() * 0.3).to_numpy()}
    bad = b - b.mean() * 0.5
    cases["half edge + dips"] = bad.where(bad > -1.5, -3.0).to_numpy()
    for T in (42, 63, 126):
        pol, E = solve(PD.returns(0.7), T=T)
        for case, x in cases.items():
            for name, fn in (("cushion 0.5", lambda s: IF.path(x, s, 0.5, 8.5)), (f"hybrid T={T}", lambda s: path(x, s, pol, E, T=T))):
                if name.startswith("cushion") and T != 42:
                    continue
                res = [fn(s) for s in range(0, len(x) - 510, 3)]
                n = len(res)
                t = np.array([d for d, _ in res if d is not None])
                print(f"{case:16s} {name:14s}: within 1 / 2 / 3 months {np.sum(t <= 21) / n:4.0%} {np.sum(t <= 42) / n:4.0%} "
                      f"{np.sum(t <= 63) / n:4.0%}, median {np.median(t) / 21:.1f} months, lost {sum(f for _, f in res) / n:5.1%}",
                      flush=True)
