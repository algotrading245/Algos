"""AurumHydra goal EA: pick a smaller InpGoalCap from 2010-06..2017, confirm on 2018..2025-09.

Why: GoalSize() = scale * phi(z) / (x * sqrt(left)) / dayvol is capped at InpGoalCap (50 in the presets
mql5/Experts/AurumHydra/AurumHydra_target{3,4,5}x_FTMO.set). In the Strategy Tester on 21 fresh-deposit months
2024.01-2025.09 the account hit a broker stop-out in 7/10/9 months at targets 3x/4x/5x. The round-5 margin model
(research/hydra_goal_margin_model.py, imported here and NOT edited) puts the smallest fixed size with a stop-out or ruin
(hit size) at min 15, 5th percentile 20. Every candidate cap below is under 15; the hit size is a ceiling, never a
candidate. InpGoalCap is an existing input, so the result is a preset change only.

Engine: the module's "lg" mode (EA+legs, round 5), 23-day month-start rounds, vol 0.0156, every month with >= 15 days
(184 months), edge 1.0 and edge 0.7. Four fixes to the round-5 reviewer REDO list are made here by overriding the
module's functions (the module file is untouched):
  1. open_ratio() returns 1.0 at once when clip >= 1e11 (no clip), whatever the free margin; check C is rerun.
  2. unit tests of open_ratio on hand-built 5-part and 1-part tickets (answers worked out in the comments).
  3. fix before cross: the EA sends the 5 fix pairs before the 3 crosses (Legs.mqh:1093-1098); the model sorted
     (entry hour, name), so cross came first. The sort key now gives the fix ticket the slot of "cross" and the cross
     ticket the slot of "fix", so only those two swap; every other leg keeps its present order.
  4. boost haircut at edge 0.7: extra_e = extra - (1 - edge) * mean(extra over all model days), put into that set's
     other / rr / rr_np / vol / res (res = other - tickets, so "tickets at ratio 1 + res == other" holds by build and is
     measured).

SELECTION RULE (fixed before any number was seen). Caps: 3, 4, 5, 6, 8, 10, 12, 14 and the preset 50 (the baseline is
in the pool, so the rule can end on 50). For each goal 3, 4, 5:
  a. Take P(goal) on the "to 2017" months (2010-06..2017-12) at edge 1.0 for every cap; best = the highest.
  b. Among the caps whose P(goal) is within 1.0 percentage point of best, take the smallest cap.
  c. That cap must also have P(goal) at edge 0.7 on "to 2017" no lower than cap 50's minus 1.0 pp; if it does not, take
     the next cap up in the list (any larger cap, 50 included) that passes this test. Cap 50 passes by definition.
  d. Then print "2018 on" (2018-01..2025-09), chosen cap against cap 50: difference in P(goal) and P(stop-out) at both
     edges. VERDICT: PASS if, on 2018 on at edge 1.0, chosen P(goal) >= cap 50's minus 1.0 pp AND chosen P(stop-out)
     < cap 50's; otherwise FAIL. If the chosen cap is 50: "no cap better than the preset".
The 21 tester months are a CHECK ONLY, run after the choice is printed, never used to choose.

Stated limits (printed too): noise leg is round 4's constant ticket unless marketdata/histdata/NSXUSD_M1.csv.gz exists
(the script says which path was used); noise pnl is not rescaled to the EA's vol sizing; the EA sizes on balance, the
model on live equity; the other legs have no intraday path; server hours 23-0 have no bars; P(goal) stays an upper
bound. Holdout: the module's holdout.drop() leaves model days to 2025-10-10 in the arrays (they feed the edge means),
but no round starts or runs past 2025-09-30 (October 2025 has < 15 days); the script asserts that.

    python research/hydra_size_cap.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import hydra_goal_margin_model as mod

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

CAPS = [3, 4, 5, 6, 8, 10, 12, 14]
BASE = 50
POOL = CAPS + [BASE]
GOALS = (3, 4, 5)
EDGES = (1.0, 0.7)
DAYS, VOL = 23, 0.0156
HIT_MIN = 15                       # round-5 hit size, minimum over the months: a ceiling, not a candidate
PERIODS = ("to 2017", "2018 on", "all")
PP = 1.0                           # selection tolerance, percentage points
LAST_OK = pd.Timestamp("2025-10-01")
T0 = [time.time()]


def lap(label):
    now = time.time()
    print(f"[elapsed] {label}: {now - T0[0]:.1f} s")
    T0[0] = now


# ---------------------------------------------------------------- fixes 1, 3, 4 (overrides)

_ORIG_OPEN = mod.open_ratio


def open_ratio_fixed(t, free, k0, ag, af, ao, clip):
    """Fix 1: no clip (clip >= 1e11) is ratio 1 whatever the free margin; otherwise the module's open_ratio."""
    if clip >= 1e11:
        return 1.0
    return _ORIG_OPEN(t, free, k0, ag, af, ao, clip)


def assemble_fixed(L, E, E1, var, edge, fix_first=True, haircut=True):
    """The module's assemble() with fix 3 (fix_first) and fix 4 (haircut of the boost extra at edge < 1). With both
    False it must equal mod.assemble() (checked below)."""
    n = len(E.other)
    B = var.boost
    fx = L.fixday
    fp = L.file_pnl
    extra = (B - 1.0) * fx * (fp["fix"] + fp["cross"] + L.full["tokyo"] + L.bell)
    extra_e = extra - (1.0 - edge) * float(np.mean(extra)) if haircut else extra
    pen = np.array(E.other) - np.array(E1.other)
    swap = {"fix": "cross", "cross": "fix"} if fix_first else {}
    V = __import__("copy").copy(E)
    use_new = var.noise_new and L.noise_new is not None
    tix, res = [], []
    for d in range(n):
        out = []
        for t in L.tix[d]:
            if use_new and t[7] == "noise":
                continue
            f = B if (fx[d] and t[7] in ("fix", "cross", "tokyo")) else 1.0
            segs = [(a_, b_, x * f) for a_, b_, x in t[2]] if f != 1.0 else t[2]
            out.append([t[0], t[1], segs, t[3], t[4] * f, t[5], t[6] * f, t[7], (1.0,) if var.single else t[8]])
        if use_new and L.noise_new[d] is not None:
            t = L.noise_new[d]
            out.append([t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], (1.0,) if var.single else t[8]])
        if var.h2 and out and pen[d] != 0.0:
            tot = sum(o[6] for o in out)
            if tot > 0:
                for o in out:
                    o[4] += pen[d] * o[6] / tot
        out.sort(key=lambda t: (t[0], swap.get(t[7], t[7])))
        tix.append([tuple(o) for o in out])
        res.append(E.other[d] + extra_e[d] - sum(o[4] for o in out))
    V.tix, V.res = tix, res
    V.other = (np.array(E.other) + extra_e).tolist()
    V.rr_np = E.rr_np + extra_e
    V.rr = V.rr_np.tolist()
    V.vol = float(np.std(V.rr_np, ddof=1))
    V.var = var.name
    return V


def same_sets(A, B):
    """(tickets identical, max abs diff of res, of other, of rr)."""
    tix_same = all(A.tix[d] == B.tix[d] for d in range(len(A.tix)))
    return (tix_same, float(np.max(np.abs(np.array(A.res) - np.array(B.res)))),
            float(np.max(np.abs(np.array(A.other) - np.array(B.other)))),
            float(np.max(np.abs(A.rr_np - B.rr_np))))


# ---------------------------------------------------------------- unit test of open_ratio (fix 2)

def unit_tests():
    """Hand-built tickets, kind FX (rate af), k0 = 1, nmax = 10, af = 0.01, so want = 1 * 10 * 0.01 = 0.10 and each
    of the 5 equal parts (share 0.2) has w = 0.02.
    A (clip 1.0, free 0.05): part1 min(1, 0.05/0.02) = 1, left 0.03; part2 min(1, 0.03/0.02) = 1, left 0.01;
        part3 0.01/0.02 = 0.5, left 0.01 - 0.5*0.02 = 0; parts 4, 5 get 0.
        ratio = 0.2 * (1 + 1 + 0.5 + 0 + 0) = 0.50.
    B (clip 0.5, free 0.07): part1 0.5*0.07/0.02 = 1.75 -> 1, left 0.05; part2 0.5*0.05/0.02 = 1.25 -> 1, left 0.03;
        part3 0.5*0.03/0.02 = 0.75, left 0.03 - 0.75*0.02 = 0.015; part4 0.5*0.015/0.02 = 0.375, left 0.0075;
        part5 0.5*0.0075/0.02 = 0.1875.  ratio = 0.2 * (1 + 1 + 0.75 + 0.375 + 0.1875) = 0.6625.
    C (clip 1e12, free 0): 1.0 (five parts and one part).  The module's own function gives 0 for the one-part ticket.
    D (1 part, clip 0.5, free 0.03): min(1, 0.5*0.03/0.10) = 0.15; with free 1.0: min(1, 0.5/0.1) = 1.0."""
    ag, af, ao, k0 = 0.005, 0.01, 0.01, 1.0
    five = (16, 18, [(16, 18, 10.0)], 1, 0.0, True, 10.0, "fix", (0.2,) * 5)
    one = (16, 18, [(16, 18, 10.0)], 1, 0.0, True, 10.0, "noise", (1.0,))
    oo = mod.open_ratio                                     # the patched function, the one ea_day calls
    tests = [
        ("A 5 parts, clip 1.0, free 0.05, 3rd part runs out: hand value 0.50", oo(five, 0.05, k0, ag, af, ao, 1.0), 0.50),
        ("B 5 parts, clip 0.5, free 0.07: hand value 0.6625", oo(five, 0.07, k0, ag, af, ao, 0.5), 0.6625),
        ("C1 5 parts, clip 1e12, free 0: hand value 1.0", oo(five, 0.0, k0, ag, af, ao, 1e12), 1.0),
        ("C2 1 part, clip 1e12, free 0: hand value 1.0", oo(one, 0.0, k0, ag, af, ao, 1e12), 1.0),
        ("D1 1 part, clip 0.5, free 0.03: min(1, 0.5*0.03/0.1) = 0.15", oo(one, 0.03, k0, ag, af, ao, 0.5), 0.15),
        ("D2 1 part, clip 0.5, free 1.0: min(1, 5) = 1.0", oo(one, 1.0, k0, ag, af, ao, 0.5), 1.0),
    ]
    print("=" * 100)
    print("UNIT TEST open_ratio (patched): want = k0 * nmax * rate = 1 * 10 * 0.01 = 0.10, 5 parts of w = 0.02 each")
    print(f"  (the module's unpatched open_ratio on the one-part ticket at clip 1e12, free 0 gives "
          f"{_ORIG_OPEN(one, 0.0, k0, ag, af, ao, 1e12):.3f}: the reviewer's C1 bug)")
    oks = []
    for label, got, want in tests:
        ok = abs(got - want) < 1e-9
        oks.append(ok)
        print(f"  {label}: got {got:.10f} -> {'PASS' if ok else 'FAIL'}")
    return all(oks)


# ---------------------------------------------------------------- metrics

def metrics(rows, goal):
    """rows (period, end multiple, stopped). P(goal) at the module's TOL, P(stop-out), P(ruin), median, 10th pct."""
    v = np.array([x[1] for x in rows], dtype=float)
    so = np.array([x[2] for x in rows], dtype=float)
    return dict(n=len(rows), pg=100 * float(np.mean(v >= goal * mod.TOL)), pso=100 * float(np.mean(so)),
                pru=100 * float(np.mean(v <= mod.m.RUIN + 1e-9)), med=float(np.median(v)),
                p10=float(np.percentile(v, 10)))


def pick_rows(rows, period):
    if period == "to 2017":
        return [x for x in rows if x[0].year <= 2017]
    if period == "2018 on":
        return [x for x in rows if x[0].year >= 2018]
    return rows


# ---------------------------------------------------------------- selection

def select(goal, M):
    """The rule in the module docstring. Returns (chosen cap, text describing the steps)."""
    pgs = {c: M[(goal, 1.0, c, "to 2017")]["pg"] for c in POOL}
    best = max(pgs.values())
    near = [c for c in POOL if pgs[c] >= best - PP - 1e-9]
    pick = min(near)
    steps = [f"best P(goal) to 2017 edge 1.0 = {best:.2f}% (cap {max(pgs, key=pgs.get)}); caps within {PP:.1f} pp: "
             f"{near}; smallest = {pick}"]
    base7 = M[(goal, 0.7, BASE, "to 2017")]["pg"]
    ok7 = lambda c: M[(goal, 0.7, c, "to 2017")]["pg"] >= base7 - PP - 1e-9
    steps.append(f"edge 0.7 to 2017: cap 50 {base7:.2f}%, floor {base7 - PP:.2f}%, cap {pick} "
                 f"{M[(goal, 0.7, pick, 'to 2017')]['pg']:.2f}% -> {'passes' if ok7(pick) else 'fails'}")
    if not ok7(pick):
        pick = [c for c in POOL if c > pick and ok7(c)][0]
        steps.append(f"next cap up that passes: {pick} ({M[(goal, 0.7, pick, 'to 2017')]['pg']:.2f}%)")
    return pick, steps


# ---------------------------------------------------------------- main

def main():
    T0[0] = time.time()
    assert max(CAPS) < HIT_MIN, "every candidate must be below the hit-size minimum"
    # ---- data, the way the module's main() builds it
    runs = mod.scan_runs()
    print("tester runs found: " + ", ".join(f"{g}x {len(v)}" for g, v in runs.items()))
    a_gold, a_fx, a_oth, om = mod.part1(runs)
    rt = mod.SimpleNamespace(ag=a_gold, af=a_fx, ao=a_oth, om=om)
    b = mod.build_bars()
    r = mod.m.daily().reindex(b.days).fillna(0.0)
    E1, E7 = mod.edge_set(b, r, 1.0), mod.edge_set(b, r, 0.7)
    L = mod.build_legs(b)
    lap("part 0 data build (tester stop-out fit, bars, legs)")

    # ---- holdout guard
    months = [(p, d0, d1) for p, (d0, d1) in mod.MONTHS.items() if d1 - d0 >= 15]
    last_used = mod.DAYS_IDX[max(d1 for _, _, d1 in months) - 1]
    n_after = sum(1 for d in mod.DAYS_IDX if d >= LAST_OK)
    assert last_used < LAST_OK, f"a round runs to {last_used.date()}, on or after 2025-10-01"
    assert all(holdout.month_ok(f"{p.year}.{p.month:02d}") for p, _, _ in months)
    assert all(holdout.month_ok(f"{rn['month'][:4]}.{rn['month'][4:]}") for g in GOALS for rn in runs[g])
    print(f"holdout guard: {len(months)} months {months[0][0]} .. {months[-1][0]}, last day used {last_used.date()} "
          f"(< 2025-10-01); the arrays hold {n_after} model days from 2025-10-01 (the module's holdout.START is "
          f"{holdout.START.date()}), none of them in a round")

    # ---- noise path
    nsx = mod.DATA / "NSXUSD_M1.csv.gz"
    noise_r5 = L.noise_new is not None
    noise_txt = ("round-5 noise path (17:00, EA vol sizing from SPXUSD and NSXUSD M1)" if noise_r5 else
                 "round 4's CONSTANT noise ticket (1.1 at 16:00) because the round-5 noise sizing was not built")
    print(f"NOISE PATH: {noise_txt}; NSXUSD_M1.csv.gz {'exists' if nsx.exists() else 'is missing'}")

    # ---- fix 1 patch and copy check
    mod.open_ratio = open_ratio_fixed
    print("=" * 100)
    print("PART 1  fixes and checks")
    print("fix 1: mod.open_ratio replaced (clip >= 1e11 -> 1.0)")
    ref1, ref7 = mod.assemble(L, E1, E1, mod.VAR5), mod.assemble(L, E7, E1, mod.VAR5)      # the module's own sets
    c1 = assemble_fixed(L, E1, E1, mod.VAR5, 1.0, fix_first=False, haircut=False)
    c7 = assemble_fixed(L, E7, E1, mod.VAR5, 0.7, fix_first=False, haircut=False)
    cp1, cp7 = same_sets(c1, ref1), same_sets(c7, ref7)
    cp_ok = cp1[0] and cp7[0] and max(cp1[1:] + cp7[1:]) < 1e-12
    print(f"copy check, assemble_fixed with fixes 3 and 4 off against mod.assemble: edge 1.0 tickets equal {cp1[0]}, "
          f"max diff res/other/rr {cp1[1]:.1e}/{cp1[2]:.1e}/{cp1[3]:.1e}; edge 0.7 tickets equal {cp7[0]}, "
          f"{cp7[1]:.1e}/{cp7[2]:.1e}/{cp7[3]:.1e} -> {'PASS' if cp_ok else 'FAIL'}")
    S = {1.0: assemble_fixed(L, E1, E1, mod.VAR5, 1.0), 0.7: assemble_fixed(L, E7, E1, mod.VAR5, 0.7)}

    # fix 3 report
    both = 0
    wrong = 0
    for d in range(len(L.tix)):
        nm = [t[7] for t in S[1.0].tix[d]]
        hrs = {t[7]: t[0] for t in S[1.0].tix[d]}
        if "fix" in hrs and "cross" in hrs and hrs["fix"] == hrs["cross"]:
            both += 1
            if nm.index("fix") > nm.index("cross"):
                wrong += 1
    old_first = sum(1 for d in range(len(L.tix)) if "fix" in {t[7] for t in ref1.tix[d]} and
                    {t[7]: t[0] for t in ref1.tix[d]}.get("fix") == {t[7]: t[0] for t in ref1.tix[d]}.get("cross") and
                    [t[7] for t in ref1.tix[d]].index("cross") < [t[7] for t in ref1.tix[d]].index("fix"))
    print(f"fix 3: days with both a fix and a cross ticket at the same entry hour: {both} of {len(L.tix)} model days "
          f"(the module's order had cross before fix on {old_first} of them; now fix before cross on all but {wrong})")
    assert wrong == 0

    # fix 4 report: identity
    ident = {}
    for e in EDGES:
        V = S[e]
        ident[e] = max(abs(sum(t[4] for t in V.tix[d]) + V.res[d] - V.other[d]) for d in range(len(V.other)))
    ex = (mod.BOOST - 1.0) * L.fixday * (L.file_pnl["fix"] + L.file_pnl["cross"] + L.full["tokyo"] + L.bell)
    print(f"fix 4: boost extra mean over model days {float(np.mean(ex)):.3e}; edge 0.7 haircut per day "
          f"{0.3 * float(np.mean(ex)):.3e}; edge 0.7 other differs from the module's by max "
          f"{float(np.max(np.abs(np.array(S[0.7].other) - np.array(ref7.other)))):.3e}")
    ident_ok = all(v < 1e-9 for v in ident.values())
    print("identity max |sum ticket pnl at ratio 1 + res - other|: " +
          ", ".join(f"edge {e}: {v:.2e}" for e, v in ident.items()) + f" -> {'PASS' if ident_ok else 'FAIL'}")

    # fix 2 unit tests
    unit_ok = unit_tests()

    # fix 1 rerun of check C
    print("=" * 100)
    print("CHECK C (module's check_c, patched open_ratio, fixed round-5 edge 1.0 set)")
    mo = [(p, (d0, d1)) for p, d0, d1 in months]
    cres = mod.check_c(S[1.0], runs, rt, mo)
    c1_ok = all(v[3] for v in cres.values())
    print(f"C1 overall: {'PASS' if c1_ok else 'FAIL'}  (" + "; ".join(
        f"{lab}: diff {v[0]:.1e}, flags {v[1]}, rounds {v[2]}" for lab, v in cres.items()) + ")")
    lap("part 1 fixes, unit test, check C")

    # ---- replication of the module's round-5 numbers on its own (unfixed) set
    print("=" * 100)
    print("REPLICATION of the round-5 numbers: module's own round-5 sets (no fixes 3, 4), cap 50, edge 1.0, 23 days, "
          "vol 0.0156, mode lg")
    want_pg = {3: 39.7, 4: 28.8, 5: 22.3}
    rep_ok = True
    for g in GOALS:
        rows = [(p, *mod.go(ref1, d0, d1, DAYS, float(BASE), VOL, g, "lg", rt)) for p, d0, d1 in months]
        pg = 100 * np.mean([x[1] >= g * mod.TOL for x in rows])
        ok = round(pg, 1) == want_pg[g]
        rep_ok &= ok
        tr = sum(rn["mult"] >= g * mod.TOL for rn in runs[g])
        mr = [mod.go(ref1, *mod.MONTHS[pd.Period(f"{rn['month'][:4]}-{rn['month'][4:]}", "M")], DAYS, float(BASE), VOL,
                     g, "lg", rt) for rn in runs[g]]
        print(f"  goal {g}x: P(goal) {pg:.1f}% over {len(rows)} months (round 5 printed {want_pg[g]}) -> "
              f"{'PASS' if ok else 'DIFFERENT'}; tester months: model goal {sum(x[0] >= g * mod.TOL for x in mr)} / "
              f"stop-outs {sum(bool(x[1]) for x in mr)} (round 5 printed goal {dict(zip(GOALS, (10, 10, 9)))[g]}, "
              f"stop-outs 8); tester goal {tr}, stop-outs {sum(rn['so'] is not None for rn in runs[g])}")
    lap("replication")

    # ---- the sweep
    print("=" * 100)
    print(f"PART 2  SWEEP: caps {POOL}, goals {list(GOALS)}, edges {list(EDGES)}, {len(months)} month-start rounds, "
          f"{DAYS} days, vol {VOL}, mode lg, fixed sets (fixes 1-4)")
    RAW = {}
    for g in GOALS:
        for e in EDGES:
            for c in POOL:
                RAW[(g, e, c)] = [(p, *mod.go(S[e], d0, d1, DAYS, float(c), VOL, g, "lg", rt)) for p, d0, d1 in months]
            print(f"  done goal {g}x edge {e} ({time.time() - T0[0]:.0f} s)")
    M = {}
    for (g, e, c), rows in RAW.items():
        for per in PERIODS:
            M[(g, e, c, per)] = metrics(pick_rows(rows, per), g)
    for g in GOALS:
        for e in EDGES:
            for per in PERIODS:
                n = M[(g, e, BASE, per)]["n"]
                print(f"\ngoal {g}x  edge {e}  period {per} ({n} months)")
                print("   cap | P(goal)%  P(SO)%  P(ruin)%  median end  10th pct end")
                for c in POOL:
                    x = M[(g, e, c, per)]
                    print(f"  {c:4d} | {x['pg']:7.1f}  {x['pso']:6.1f}  {x['pru']:7.1f}  {x['med']:9.2f}x  {x['p10']:10.2f}x"
                          f"{'   <- preset' if c == BASE else ''}")
    lap("part 2 sweep and tables")

    # ---- selection
    print("=" * 100)
    print("PART 3  SELECTION (rule in the docstring, chosen on 'to 2017' only)")
    chosen, why = {}, {}
    for g in GOALS:
        chosen[g], why[g] = select(g, M)
        print(f"goal {g}x:")
        for s in why[g]:
            print(f"   {s}")
        print(f"   CHOSEN CAP {chosen[g]}")
    print("\nCONFIRM on '2018 on' (chosen against cap 50):")
    verdict = {}
    for g in GOALS:
        c = chosen[g]
        parts = []
        for e in EDGES:
            a, bb = M[(g, e, c, "2018 on")], M[(g, e, BASE, "2018 on")]
            parts.append(f"edge {e}: P(goal) {a['pg']:.1f}% vs {bb['pg']:.1f}% (diff {a['pg'] - bb['pg']:+.1f} pp), "
                         f"P(SO) {a['pso']:.1f}% vs {bb['pso']:.1f}% (diff {a['pso'] - bb['pso']:+.1f} pp)")
        a, bb = M[(g, 1.0, c, "2018 on")], M[(g, 1.0, BASE, "2018 on")]
        if c == BASE:
            verdict[g] = "no cap better than the preset"
        else:
            ok = a["pg"] >= bb["pg"] - PP - 1e-9 and a["pso"] < bb["pso"] - 1e-9
            verdict[g] = "PASS" if ok else "FAIL"
        print(f"goal {g}x cap {c} vs 50 | " + " | ".join(parts) + f" | VERDICT {verdict[g]}")
    lap("part 3 selection")

    # ---- check only: the 21 tester months
    print("=" * 100)
    print("PART 4  CHECK ONLY - not used to choose")
    print("21 tester months 2024.01-2025.09, preset 23 days, vol 0.0156, edge 1.0 fixed round-5 set, mode lg; goal reached "
          "at 0.3% tolerance; tester = mult >= goal*TOL, stop-out = a 'so ' deal")
    chk = {}
    for g in GOALS:
        c = chosen[g]
        res = {}
        for cap in sorted({c, BASE}):
            rr = [mod.go(S[1.0], *mod.MONTHS[pd.Period(f"{rn['month'][:4]}-{rn['month'][4:]}", "M")], DAYS, float(cap),
                         VOL, g, "lg", rt) for rn in runs[g]]
            res[cap] = (sum(x[0] >= g * mod.TOL for x in rr), sum(bool(x[1]) for x in rr))
        t = (sum(rn["mult"] >= g * mod.TOL for rn in runs[g]), sum(rn["so"] is not None for rn in runs[g]))
        chk[g] = (res[c], res[BASE], t, len(runs[g]))
        print(f"goal {g}x ({len(runs[g])} months): model cap {c}: goal {res[c][0]}, stop-outs {res[c][1]} | model cap 50: "
              f"goal {res[BASE][0]}, stop-outs {res[BASE][1]} | tester (cap 50): goal {t[0]}, stop-outs {t[1]}"
              f"{'  (chosen is 50)' if c == BASE else ''}")
    lap("part 4 tester-month check")

    # ---- binding
    print("=" * 100)
    print("PART 5  how often the cap binds (month-start rounds, edge 1.0, day-open GoalSize calls before the cap)")
    rec = dict(inside=False, log=[])
    orig_gs, orig_ea = mod.goal_size, mod.ea_day

    def gs_rec(eq, goal, left, cap, vol):
        v = orig_gs(eq, goal, left, cap, vol)
        if not rec["inside"]:
            rec["log"].append(orig_gs(eq, goal, left, 1e18, vol))
        return v

    def ea_rec(*a, **k):
        rec["inside"] = True
        try:
            return orig_ea(*a, **k)
        finally:
            rec["inside"] = False

    mod.goal_size, mod.ea_day = gs_rec, ea_rec
    bind = {}
    try:
        for g in GOALS:
            for cap in sorted({chosen[g], BASE}):
                ever, first, mx, days_over, days_all = 0, [], [], 0, 0
                for i, (p, d0, d1) in enumerate(months):
                    rec["log"] = []
                    v, so = mod.go(S[1.0], d0, d1, DAYS, float(cap), VOL, g, "lg", rt)
                    old = RAW[(g, 1.0, cap)][i]
                    assert abs(old[1] - v) < 1e-12 and bool(old[2]) == bool(so), "recorder changed a result"
                    lg = np.array(rec["log"])
                    ever += bool(lg.max() > cap + 1e-9)
                    first.append(lg[0])
                    mx.append(lg.max())
                    days_over += int((lg > cap + 1e-9).sum())
                    days_all += len(lg)
                bind[(g, cap)] = (100 * ever / len(months), float(np.median(first)), float(np.median(mx)),
                                  100 * days_over / days_all)
                print(f"goal {g}x cap {cap:2d}: rounds in which the schedule ever asked for more than the cap "
                      f"{ever} of {len(months)} ({bind[(g, cap)][0]:.1f}%); median GoalSize asked on day 1 "
                      f"{bind[(g, cap)][1]:.1f} (same every month: equity 1.0, 23 days left); median of the largest "
                      f"size asked in a round {bind[(g, cap)][2]:.1f}; share of played days above the cap "
                      f"{bind[(g, cap)][3]:.1f}%")
    finally:
        mod.goal_size, mod.ea_day = orig_gs, orig_ea
    lap("part 5 binding")

    # ---- summary
    print("=" * 100)
    print("SIZE CAP SUMMARY")
    print(f"selection rule: highest P(goal) to 2017 at edge 1.0; smallest cap within {PP:.1f} pp of it; edge 0.7 to 2017 "
          f"no lower than cap 50's minus {PP:.1f} pp else next cap up; verdict on 2018 on at edge 1.0 (P(goal) >= 50's "
          f"minus {PP:.1f} pp and P(SO) lower than 50's)")
    for g in GOALS:
        c = chosen[g]
        print(f"goal {g}x: chosen InpGoalCap {c} (preset 50), VERDICT {verdict[g]}")
        for per, tag in (("to 2017", "selection half"), ("2018 on", "confirm half  ")):
            for e in EDGES:
                a, bb = M[(g, e, c, per)], M[(g, e, BASE, per)]
                print(f"   {tag} edge {e}: chosen P(goal) {a['pg']:5.1f}% P(SO) {a['pso']:5.1f}% | cap 50 P(goal) "
                      f"{bb['pg']:5.1f}% P(SO) {bb['pso']:5.1f}%  ({a['n']} months)")
        x = chk[g]
        print(f"   tester-month check only (not used to choose): model cap {c} goal {x[0][0]} SO {x[0][1]} | model cap 50 "
              f"goal {x[1][0]} SO {x[1][1]} | tester goal {x[2][0]} SO {x[2][1]} of {x[3]}")
        bd = bind[(g, c)]
        print(f"   cap binds in {bd[0]:.1f}% of the {len(months)} month rounds; median day-1 GoalSize asked {bd[1]:.1f}")
    print(f"C1 check_c: {'PASS' if c1_ok else 'FAIL'} | open_ratio unit tests: {'PASS' if unit_ok else 'FAIL'} | "
          f"identity (tickets at ratio 1 + res == other): {'PASS' if ident_ok else 'FAIL'} (max err " +
          ", ".join(f"edge {e} {v:.1e}" for e, v in ident.items()) + f") | assemble copy check: "
          f"{'PASS' if cp_ok else 'FAIL'} | round-5 replication: {'PASS' if rep_ok else 'DIFFERENT'}")
    print(f"noise path used: {noise_txt}")
    print("STATED LIMITS (not fixed): noise P&L is not rescaled to the EA's vol sizing"
          + ("" if noise_r5 else "; the noise leg is round 4's constant ticket (marketdata/histdata/NSXUSD_M1.csv.gz missing)")
          + "; the EA sizes on balance, the model on live equity; the other legs have no intraday path (booked at the "
            "close, their open loss never enters the stop-out check); server hours 23-0 have no bars; P(goal) stays an "
            "upper bound; the edge means include model days to 2025-10-10 that the module's holdout leaves in (no round "
            "uses them)")
    lap("summary")


if __name__ == "__main__":
    main()
