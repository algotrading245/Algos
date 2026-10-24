"""AurumHydra goal model at three account leverages: how much of the tester's goal shortfall is the test leverage?

Why: lesson 19 (corrected 2026-10-19) found that the Strategy Tester never applied the job's leverage. The Hydra goal
jobs asked for 1:500, but the 21 single-month runs t3b-t5b ran on the tester install at 1:100 and the Terminal 16 runs
(j4-j10b) at 1:33 (research/demo_margin_terminals.out.txt). The margin rates of the goal model are fitted from the
t3b-t5b stop-outs (research/hydra_size_cap2.out.txt lines 34-36: gold 0.0202, fx 0.0100, other 0.0199 of notional),
so they are the 1:100 rates. MT5 margin = notional * symbol rate / account leverage, so another leverage scales every
rate by 100 / leverage.

What runs: the round-5 engine with the four size-cap fixes (research/hydra_size_cap.py: open_ratio_fixed,
assemble_fixed; the module files are not edited), mode lg (EA+legs), preset cap 50, 23 days, vol 0.0156, edge 1.0 and
0.7, every month-start round with >= 15 days 2010-06..2025-09 (184 months), and the 21 tester months as a check. Only
the margin rates change between the columns. No setting is chosen: 0 trials.

PRE-REGISTERED READING (written before any number was seen):
  A. Calibration: at 1:100 the model's stop-outs on the 21 months should sit near the tester's 7/10/9 (round 5 gave 8);
     if they do not, the model is not fit to answer and the result is written down as such.
  B. Leverage explains the tester's stop-outs if, at 1:500 against 1:100 on the 184 months, edge 1.0, P(stop-out)
     falls by at least half at 4x and 5x. Then the 1:100 tester figures (9/4/2 of 21) do not measure a 1:500 account,
     and a tester re-run at 1:500 (after tools change (4)) is the next Hydra job.
  C. The 1:500 account is not simply better: report P(goal), P(stop-out) and the share of rounds ending below 0.5x
     (ruin-like) at each leverage. If P(goal) at 1:500 rises by less than 3 pp at 4x and 5x, the clip and the margin
     are not what hold the goal back, whatever B says.
  The P(goal) levels stay a loose upper bound (lesson 19); only the differences between columns are read.

    python research/hydra_leverage_sens.py
"""
import time

import numpy as np
import pandas as pd

import hydra_goal_margin_model as mod
import hydra_size_cap as cap

LEVS = (33, 100, 500)
FIT_LEV = 100                      # the leverage the fitted rates belong to (t3b-t5b on the tester install)
GOALS = (3, 4, 5)
EDGES = (1.0, 0.7)
DAYS, VOL, CAP = 23, 0.0156, 50.0


def rt_at(rt0, lev):
    k = FIT_LEV / lev
    return mod.SimpleNamespace(ag=rt0.ag * k, af=rt0.af * k, ao=rt0.ao * k, om=rt0.om * k)


def row(rs, g):
    v = np.array([x[0] for x in rs])
    so = np.array([bool(x[1]) for x in rs])
    return 100 * np.mean(v >= g * mod.TOL), 100 * np.mean(so), 100 * np.mean(v < 0.5), float(np.median(v))


def main():
    t0 = time.time()
    runs = mod.scan_runs()
    print("tester runs found: " + ", ".join(f"{g}x {len(v)}" for g, v in runs.items()))
    a_gold, a_fx, a_oth, om = mod.part1(runs)
    rt0 = mod.SimpleNamespace(ag=a_gold, af=a_fx, ao=a_oth, om=om)
    b = mod.build_bars()
    r = mod.m.daily().reindex(b.days).fillna(0.0)
    E1, E7 = mod.edge_set(b, r, 1.0), mod.edge_set(b, r, 0.7)
    L = mod.build_legs(b)
    mod.open_ratio = cap.open_ratio_fixed
    S = {1.0: cap.assemble_fixed(L, E1, E1, mod.VAR5, 1.0), 0.7: cap.assemble_fixed(L, E7, E1, mod.VAR5, 0.7)}
    noise = ("round-5 noise path (17:00, EA vol from SPXUSD/NSXUSD M1)" if L.noise_new is not None
             else "round 4's constant noise ticket")
    print(f"NOISE PATH: {noise}")

    months = [(p, d0, d1) for p, (d0, d1) in mod.MONTHS.items() if d1 - d0 >= 15]
    last_used = mod.DAYS_IDX[max(d1 for _, _, d1 in months) - 1]
    assert last_used < cap.LAST_OK, f"a round runs to {last_used.date()}"
    print(f"holdout guard: {len(months)} months {months[0][0]} .. {months[-1][0]}, last day used {last_used.date()}")
    print("=" * 100)
    print("rates by leverage (margin per USD notional): " + "; ".join(
        f"1:{lv} gold {rt_at(rt0, lv).ag:.5f} fx {rt_at(rt0, lv).af:.5f} other {rt_at(rt0, lv).ao:.5f}" for lv in LEVS))

    print("=" * 100)
    print("PART A  21 tester months (check only), edge 1.0, cap 50: model goal reached / stop-outs at each leverage")
    print("goal | tester (1:100) goal SO | " + " | ".join(f"model 1:{lv} goal SO" for lv in LEVS))
    for g in GOALS:
        cells = []
        for lv in LEVS:
            rt = rt_at(rt0, lv)
            mr = [mod.go(S[1.0], *mod.MONTHS[pd.Period(f"{rn['month'][:4]}-{rn['month'][4:]}", "M")], DAYS, CAP, VOL,
                         g, "lg", rt) for rn in runs[g]]
            cells.append(f"{sum(x[0] >= g * mod.TOL for x in mr):10d} {sum(bool(x[1]) for x in mr):3d}")
        tr = sum(rn["mult"] >= g * mod.TOL for rn in runs[g])
        ts = sum(rn["so"] is not None for rn in runs[g])
        print(f" {g}x  | {tr:18d} {ts:3d} | " + " | ".join(cells))

    print("=" * 100)
    print(f"PART B  {len(months)} month-start rounds, cap 50: P(goal) % / P(stop-out) % / share below 0.5x % / median "
          f"multiple")
    res = {}
    for e in EDGES:
        for g in GOALS:
            for lv in LEVS:
                rt = rt_at(rt0, lv)
                rs = [mod.go(S[e], d0, d1, DAYS, CAP, VOL, g, "lg", rt) for _, d0, d1 in months]
                res[(e, g, lv)] = row(rs, g)
            print(f"edge {e} goal {g}x: " + " | ".join(
                f"1:{lv} {res[(e, g, lv)][0]:5.1f} / {res[(e, g, lv)][1]:5.1f} / {res[(e, g, lv)][2]:5.1f} / "
                f"{res[(e, g, lv)][3]:.2f}x" for lv in LEVS) + f"   ({time.time() - t0:.0f} s)")

    print("=" * 100)
    print("READING (rules fixed in the docstring)")
    for g in (4, 5):
        p100, p500 = res[(1.0, g, 100)], res[(1.0, g, 500)]
        b_ok = p500[1] <= 0.5 * p100[1]
        c_ok = p500[0] - p100[0] >= 3.0
        print(f"goal {g}x edge 1.0: P(stop-out) 1:100 {p100[1]:.1f}% -> 1:500 {p500[1]:.1f}% "
              f"(B {'MET' if b_ok else 'NOT MET'}: halved or more); P(goal) {p100[0]:.1f}% -> {p500[0]:.1f}% "
              f"({p500[0] - p100[0]:+.1f} pp, C {'MET' if c_ok else 'NOT MET'}: +3 pp or more); below 0.5x "
              f"{p100[2]:.1f}% -> {p500[2]:.1f}%")
    print(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
