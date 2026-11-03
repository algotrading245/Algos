"""AurumHydra goal EA, run 2 of hydra_size_cap: static caps 20-45 and a DYNAMIC margin-aware cap against the preset 50.

Why: run 1 (research/hydra_size_cap.py) swept static InpGoalCap 3-14 against the preset 50 and kept 50 (caps <= 14 lose
19-25 pp of P(goal)). Cap 50 binds in 55-76% of rounds (median day-1 size asked 36-47). The reviewer said caps 15-49 are
untested. Run 2 tests (A) static caps 20, 25, 30, 35, 40, 45, 50 and (B) a dynamic cap, size = min(GoalSize, 50, s_dyn),
at margin-level thresholds 1.5, 2, 3, 4, 6 (margin level = equity / margin, broker stop-out at 0.5). 12 variants.

Engine: research/hydra_goal_margin_model.py ("mod", imported, NOT edited) and research/hydra_size_cap.py ("sc", imported,
NOT edited): sc's fixed sets (assemble_fixed: fix before cross, boost haircut), sc's open_ratio_fixed patched into
mod.open_ratio, sc.metrics, sc.pick_rows, sc's holdout guard, check C. Mode "lg", 23 days, vol 0.0156, goals 3/4/5,
edges 1.0 and 0.7, the 184 month-start rounds (months with >= 15 days).

The dynamic cap (computable by the EA at the day's open, no look-ahead). At every sizing call (the day-open size in
run_round and the intraday sizef(eq) the grid calls) size = min(goal_size(...), s_dyn). s_dyn is the largest s with
projected margin level eq / Mproj(s) >= thr, Mproj from what is known at the day's open bar a = E.starts[d]:
  hold  s * eq * max(E.pos[a], 0) * ag                      (target at size s, the 25% band ignored)
  grid  max(G_open * af, s * eq * GRID_LEVELS * GRID_RISK / (GRID_RISK_STEPS * E.unit[a]) * af)
        (G_open = grid notional open in the state at the day's open; the per-level formula is mod.ea_day line 1104,
        base = balance * size * GRID_RISK / (GRID_RISK_STEPS * unit), times GRID_LEVELS levels)
  other s * eq * OM_MAX, OM_MAX one constant: the 95th percentile over the model days 2010-06..2017-12 of
        sum_t t[6] * rate(t[3]) over the day's tickets in S[1.0] (rate ag / af / ao as mod.legs_margin).
Closed form with q = 1/thr, h = max(pos,0)*ag + OM_MAX, g = GRID_LEVELS*GRID_RISK/(GRID_RISK_STEPS*unit)*af, Gaf =
G_open*af/eq: f(s) = s*h + max(Gaf, s*g) is increasing, solve f(s) = q: if Gaf > q then 0; sB = (q - Gaf)/h and if
sB*g <= Gaf then s_dyn = sB, else s_dyn = q/(h+g). s_dyn = 0 means no new size that day. What size 0 does in ea_day:
T <= 0 closes the hold (equity pays the hold cost H*HC) and the grid opens no level (base 0, n <= 1e-9); accepted
behaviour: the account sits flat and the open grid, if any, runs on. thr 0 = off (reproduces cap 50 exactly).

SELECTION RULE: printed verbatim by the script (SELECTION_RULE below), fixed before any number was seen.

Limits (printed too): noise leg is round 4's constant ticket because marketdata/histdata/NSXUSD_M1.csv.gz is missing;
noise pnl not rescaled; the EA sizes on balance, the model on live equity; other legs have no intraday path; P(goal) is an
upper bound; OM_MAX is a constant where the EA would compute its own planned leg margin.

    python research/hydra_size_cap2.py           (full, edges 1.0 and 0.7)
    python research/hydra_size_cap2.py --quick   (smoke test: goal 3, edge 1.0, cap 50 and dyn 3, first 40 months)
"""
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hydra_goal_margin_model as mod  # noqa: E402
import hydra_size_cap as sc  # noqa: E402

holdout = sc.holdout
GOALS, EDGES, DAYS, VOL, PP = sc.GOALS, sc.EDGES, sc.DAYS, sc.VOL, sc.PP
PERIODS = sc.PERIODS
BASE = 50.0
STATIC = [20, 25, 30, 35, 40, 45, 50]
THRS = [1.5, 2, 3, 4, 6]
# order = closeness to the preset: static larger cap first, then static before dynamic, dynamic lower threshold first
ORDER = [("s", c) for c in sorted(STATIC, reverse=True)] + [("d", t) for t in sorted(THRS)]
PRESET = ("s", 50)
T0 = [time.time()]

SELECTION_RULE = """SELECTION RULE (fixed before any number is seen). Variants: static caps 20, 25, 30, 35, 40, 45, 50 and dynamic
min(50, s_dyn) at thresholds 1.5, 2, 3, 4, 6 (12). For each goal 3, 4, 5, on "to 2017" (2010-06..2017-12):
 a. best = the highest P(goal) at edge 1.0 over all 12 variants.
 b. near = variants within 1.0 pp of best. Pick the one with the lowest P(stop-out) at edge 1.0 to 2017; ties go to the
    variant closest to the preset (static: the larger cap; dynamic: the lower threshold; static before dynamic).
 c. The pick's P(goal) at edge 0.7 to 2017 must be >= cap 50's minus 1.0 pp; if not, take the next variant of `near` in
    the order of (b) that passes; if none, cap 50.
 d. Do the same steps a-c restricted to the 7 static variants: "best static".
 e. CONFIRM on "2018 on" (2018-01..2025-09), edge 1.0: PASS against cap 50 if pick P(goal) >= cap 50's - 1.0 pp AND pick
    P(SO) < cap 50's. If the pick is dynamic it must ALSO PASS against "best static" by the same test (P(goal) >= best
    static's - 1.0 pp and P(SO) < best static's); otherwise the verdict is "dynamic does not beat the best static". If the
    pick is cap 50: "no variant better than the preset"."""


def name(v):
    return f"cap {v[1]}" if v[0] == "s" else f"dyn {v[1]}"


def lap(label):
    now = time.time()
    print(f"[elapsed] {label}: {now - T0[0]:.1f} s")
    T0[0] = now


# ---------------------------------------------------------------- the dynamic cap

DYN = dict(om_max=0.0, log=None)


def s_dyn(pos_a, unit_a, eq, g_open, thr, ag, af, om_max):
    """Largest s with eq / Mproj(s) >= thr (see the docstring). eq > 0."""
    if thr <= 0 or eq <= 0:
        return math.inf
    q = 1.0 / thr
    h = max(pos_a, 0.0) * ag + om_max
    g = mod.GRID_LEVELS * mod.GRID_RISK / (mod.GRID_RISK_STEPS * unit_a) * af
    gaf = g_open * af / eq
    if gaf > q:
        return 0.0
    if h <= 0.0:
        return q / g if g > 0 else math.inf
    sb = (q - gaf) / h
    if sb * g <= gaf + 1e-15:
        return sb
    return q / (h + g)


_ORIG_RUN = mod.run_round


def run_round_dyn(E, d0, d1, days, cap, vol, goal, margin, a_gold=0.0, a_fx=0.0, ea=False, om=0.0, fixed=None,
                  mins=None, ao=0.0, lmode=0, clip=mod.CLIP, legmargin=True, thr=0.0):
    """mod.run_round with size = min(goal_size, s_dyn(thr)). Same loop, line for line, for the EA path; anything else goes
    to the original. thr 0 skips s_dyn, so it is the original arithmetic."""
    if not (ea and fixed is None and margin):
        return _ORIG_RUN(E, d0, d1, days, cap, vol, goal, margin, a_gold, a_fx, ea, om, fixed, mins, ao, lmode, clip,
                         legmargin)
    eq, stopped = 1.0, False
    mod.LAST[0] = -1
    d = d0 - 1
    S = mod.new_state()
    om_max, log = DYN["om_max"], DYN["log"]
    for k in range(min(days, d1 - d0)):
        d = d0 + k
        eq = S["eq"]
        left = days - k
        size = mod.goal_size(eq, goal, left, cap, vol)
        if thr > 0:
            a = E.starts[d]
            g_open = sum(S["lv"])
            sd = s_dyn(E.pos[a], E.unit[a], eq, g_open, thr, a_gold, a_fx, om_max)
            if log is not None:
                log.append(sd < size - 1e-12)
            size = min(size, sd)

            def sizef(x, left=left, a=a, g_open=g_open):
                v = mod.goal_size(x, goal, left, cap, vol)
                return min(v, s_dyn(E.pos[a], E.unit[a], x, g_open, thr, a_gold, a_fx, om_max))
        else:
            def sizef(x, left=left):
                return mod.goal_size(x, goal, left, cap, vol)
        stopped = mod.ea_day(E, d, size, S, a_gold, a_fx, om, sizef, ao, lmode, clip, legmargin)
        eq = S["eq"]
        if stopped:
            mod.LAST[0] = d
            break
        if eq >= goal or eq <= mod.m.RUIN:
            break
    if mins is not None:
        mins.extend(S["mins"])
    mod.ACC.update(ol=S["ol"], nobar=S["nobar"], last=d, mins=S["mins"])
    return min(eq, goal), stopped


def play(E, d0, d1, v, g, rt):
    if v[0] == "s":
        return mod.go(E, d0, d1, DAYS, float(v[1]), VOL, g, "lg", rt)
    return mod.go(E, d0, d1, DAYS, BASE, VOL, g, "lg", rt, thr=float(v[1]))


def unit_test_sdyn():
    """GRID_LEVELS 4, GRID_RISK 0.035, STEPS 10, unit 0.007 -> per-level 0.035/0.07 = 0.5, four levels 2.0 per unit of
    eq*size; af = 0.01 so g = 0.02 (grid margin at size s = 0.02 s eq); ag = 0.005, pos 2.0 -> hold 0.01 s eq;
    OM_MAX 0.02 -> h = 0.01 + 0.02 = 0.03; thr 2 -> q = 0.5; eq = 1.
    Day 1, no open grid (Gaf 0): sB = 0.5/0.03 = 16.667 but sB*g = 0.333 > Gaf 0 so the grid term s*g binds:
        s = q/(h+g) = 0.5/0.05 = 10.  Check: 10*0.03 + 10*0.02 = 0.5 -> level 2.0.
    Day 2, G_open 25 (Gaf = 25*0.01 = 0.25): sB = (0.5-0.25)/0.03 = 8.3333, sB*g = 0.1667 <= 0.25 so the open grid binds
        (the max picks Gaf): s = 8.3333.  Check: 8.3333*0.03 + 0.25 = 0.5.
    Day 3, G_open 60 (Gaf 0.6 > q 0.5): even s = 0 fails -> 0.   Day 4, thr 0 -> inf (off)."""
    ag, af, om_max = 0.005, 0.01, 0.02
    t = [("day 1 no open grid: 10", s_dyn(2.0, 0.007, 1.0, 0.0, 2.0, ag, af, om_max), 10.0),
         ("day 2 G_open 25, the max binds: 8.3333", s_dyn(2.0, 0.007, 1.0, 25.0, 2.0, ag, af, om_max), 0.25 / 0.03),
         ("day 3 G_open 60, s=0 fails: 0", s_dyn(2.0, 0.007, 1.0, 60.0, 2.0, ag, af, om_max), 0.0),
         ("thr 0 off: inf", s_dyn(2.0, 0.007, 1.0, 0.0, 0.0, ag, af, om_max), math.inf)]
    print("=" * 100)
    print("UNIT TEST s_dyn (answers worked out in the function's comments)")
    oks = []
    for lab, got, want in t:
        ok = (got == want) if math.isinf(want) else abs(got - want) < 1e-9
        oks.append(ok)
        print(f"  {lab}: got {got:.6f} -> {'PASS' if ok else 'FAIL'}")
    return all(oks)


# ---------------------------------------------------------------- selection

def select(goal, M, pool):
    pgs = {v: M[(goal, 1.0, v, "to 2017")]["pg"] for v in pool}
    best = max(pgs.values())
    near = [v for v in pool if pgs[v] >= best - PP - 1e-9]
    near.sort(key=lambda v: (M[(goal, 1.0, v, "to 2017")]["pso"], ORDER.index(v)))
    steps = [f"best P(goal) to 2017 edge 1.0 = {best:.2f}% ({name(max(pgs, key=pgs.get))}); near (within {PP:.1f} pp), "
             f"in order of lowest P(SO) then closeness to preset: "
             + ", ".join(f"{name(v)} (P(goal) {pgs[v]:.1f}, P(SO) {M[(goal, 1.0, v, 'to 2017')]['pso']:.1f})" for v in near)]
    b7 = M[(goal, 0.7, PRESET, "to 2017")]["pg"]
    ok7 = lambda v: M[(goal, 0.7, v, "to 2017")]["pg"] >= b7 - PP - 1e-9
    pick = PRESET
    for v in near:
        steps.append(f"edge 0.7 to 2017: {name(v)} {M[(goal, 0.7, v, 'to 2017')]['pg']:.2f}% vs floor {b7 - PP:.2f}% "
                     f"-> {'passes' if ok7(v) else 'fails'}")
        if ok7(v):
            pick = v
            break
    else:
        steps.append("none passes: cap 50")
    return pick, steps


def beats(M, g, v, ref):
    a, b = M[(g, 1.0, v, "2018 on")], M[(g, 1.0, ref, "2018 on")]
    return a["pg"] >= b["pg"] - PP - 1e-9 and a["pso"] < b["pso"] - 1e-9


# ---------------------------------------------------------------- main

def main():
    quick = "--quick" in sys.argv
    T0[0] = time.time()
    goals = (3,) if quick else GOALS
    edges = (1.0,) if quick else EDGES
    pool = [("s", 50), ("d", 3)] if quick else [("s", c) for c in STATIC] + [("d", t) for t in THRS]

    # ---- part 0: data (as sc.main)
    runs = mod.scan_runs()
    print("tester runs found: " + ", ".join(f"{g}x {len(v)}" for g, v in runs.items()))
    a_gold, a_fx, a_oth, om = mod.part1(runs)
    rt = SimpleNamespace(ag=a_gold, af=a_fx, ao=a_oth, om=om)
    b = mod.build_bars()
    r = mod.m.daily().reindex(b.days).fillna(0.0)
    E1, E7 = mod.edge_set(b, r, 1.0), mod.edge_set(b, r, 0.7)
    L = mod.build_legs(b)
    lap("part 0 data build")

    all_months = [(p, d0, d1) for p, (d0, d1) in mod.MONTHS.items() if d1 - d0 >= 15]
    months = all_months[:40] if quick else all_months
    # ---- check 5: holdout guard
    last_used = mod.DAYS_IDX[max(d1 for _, _, d1 in all_months) - 1]
    n_after = sum(1 for d in mod.DAYS_IDX if d >= sc.LAST_OK)
    ho_ok = last_used < sc.LAST_OK and all(holdout.month_ok(f"{p.year}.{p.month:02d}") for p, _, _ in all_months) \
        and all(holdout.month_ok(f"{rn['month'][:4]}.{rn['month'][4:]}") for g in GOALS for rn in runs[g])
    print(f"CHECK 5 holdout: {len(all_months)} months {all_months[0][0]} .. {all_months[-1][0]}, last day used "
          f"{last_used.date()} (< 2025-10-01); the arrays hold {n_after} model days from 2025-10-01, none in a round "
          f"-> {'PASS' if ho_ok else 'FAIL'}")
    assert ho_ok

    nsx = mod.DATA / "NSXUSD_M1.csv.gz"
    noise_r5 = L.noise_new is not None
    noise_txt = ("round-5 noise path" if noise_r5 else "round 4's CONSTANT noise ticket (round-5 noise sizing not built)")
    print(f"NOISE PATH: {noise_txt}; NSXUSD_M1.csv.gz {'exists' if nsx.exists() else 'is missing'}")

    # ---- check 1: sc's patch, copy check, identity, C1, unit tests
    mod.open_ratio = sc.open_ratio_fixed
    print("=" * 100)
    print("CHECK 1  sc's copy check, identity, unit tests, check C")
    ref1, ref7 = mod.assemble(L, E1, E1, mod.VAR5), mod.assemble(L, E7, E1, mod.VAR5)
    c1 = sc.assemble_fixed(L, E1, E1, mod.VAR5, 1.0, fix_first=False, haircut=False)
    c7 = sc.assemble_fixed(L, E7, E1, mod.VAR5, 0.7, fix_first=False, haircut=False)
    cp1, cp7 = sc.same_sets(c1, ref1), sc.same_sets(c7, ref7)
    cp_ok = cp1[0] and cp7[0] and max(cp1[1:] + cp7[1:]) < 1e-12
    print(f"copy check (fixes 3, 4 off vs mod.assemble): {'PASS' if cp_ok else 'FAIL'}")
    S = {1.0: sc.assemble_fixed(L, E1, E1, mod.VAR5, 1.0), 0.7: sc.assemble_fixed(L, E7, E1, mod.VAR5, 0.7)}
    ident = {e: max(abs(sum(t[4] for t in S[e].tix[d]) + S[e].res[d] - S[e].other[d]) for d in range(len(S[e].other)))
             for e in sc.EDGES}
    ident_ok = all(v < 1e-9 for v in ident.values())
    print("identity max |sum ticket pnl + res - other|: " + ", ".join(f"edge {e}: {v:.2e}" for e, v in ident.items())
          + f" -> {'PASS' if ident_ok else 'FAIL'}")
    unit_ok = sc.unit_tests()
    mo = [(p, (d0, d1)) for p, d0, d1 in all_months]
    cres = mod.check_c(S[1.0], runs, rt, mo)
    c1_ok = all(v[3] for v in cres.values())
    print(f"C1 overall: {'PASS' if c1_ok else 'FAIL'}")
    chk1 = cp_ok and ident_ok and unit_ok and c1_ok
    print(f"CHECK 1 {'PASS' if chk1 else 'FAIL'}")
    lap("check 1")

    # ---- OM_MAX
    tix = S[1.0].tix
    sel_days = [i for i, d in enumerate(mod.DAYS_IDX) if pd.Timestamp("2010-06-01") <= d <= pd.Timestamp("2017-12-31")]
    om_day = np.array([sum(t[6] * (rt.ag if t[3] == 0 else (rt.af if t[3] == 1 else rt.ao)) for t in tix[i])
                       for i in sel_days])
    DYN["om_max"] = float(np.percentile(om_day, 95))
    print(f"OM_MAX (95th pct over {len(sel_days)} model days 2010-06..2017-12 of sum t[6]*rate, per unit of eq*size) = "
          f"{DYN['om_max']:.5f}; median {float(np.median(om_day)):.5f}; share of days with no ticket "
          f"{100 * float(np.mean(om_day == 0)):.1f}%; max {float(om_day.max()):.5f}")

    ok3 = unit_test_sdyn()
    print(f"CHECK 3 s_dyn unit test: {'PASS' if ok3 else 'FAIL'}")

    # ---- check 2: dynamic off == original run_round (own loop vs mod's original), every round
    mod.run_round = run_round_dyn
    print("=" * 100)
    mx, nflag, nr = 0.0, 0, 0
    c2_goals = goals
    for g in c2_goals:
        for e in edges:
            for p, d0, d1 in months:
                mod.run_round = _ORIG_RUN
                o = mod.go(S[e], d0, d1, DAYS, BASE, VOL, g, "lg", rt)
                mod.run_round = run_round_dyn
                n_ = mod.go(S[e], d0, d1, DAYS, BASE, VOL, g, "lg", rt, thr=0.0)
                mx = max(mx, abs(o[0] - n_[0]))
                nflag += bool(o[1]) != bool(n_[1])
                nr += 1
    ok2 = mx == 0.0 and nflag == 0
    print(f"CHECK 2 dynamic off (thr 0) vs original run_round at cap 50: {nr} rounds, max abs diff of end multiples "
          f"{mx:.1e}, stop-out flag differences {nflag} -> {'PASS' if ok2 else 'FAIL'}")
    lap("check 2")

    # ---- sweep
    print("=" * 100)
    print(SELECTION_RULE)
    print("=" * 100)
    print(f"SWEEP: variants {[name(v) for v in pool]}, goals {list(goals)}, edges {list(edges)}, {len(months)} month "
          f"rounds, {DAYS} days, vol {VOL}, mode lg, fixed sets; OM_MAX {DYN['om_max']:.5f}")
    RAW, BIND = {}, {}
    for g in goals:
        for e in edges:
            for v in pool:
                rows = []
                bl = []
                for p, d0, d1 in months:
                    if v[0] == "d" and e == 1.0:
                        DYN["log"] = []
                    x = play(S[e], d0, d1, v, g, rt)
                    if DYN["log"] is not None:
                        bl.append(list(DYN["log"]))
                        DYN["log"] = None
                    rows.append((p, *x))
                RAW[(g, e, v)] = rows
                if bl:
                    BIND[(g, v)] = (100 * np.mean([any(x) for x in bl]),
                                    100 * sum(sum(x) for x in bl) / max(1, sum(len(x) for x in bl)))
            print(f"  done goal {g}x edge {e} ({time.time() - T0[0]:.0f} s)")
    M = {}
    for (g, e, v), rows in RAW.items():
        for per in PERIODS:
            if sc.pick_rows(rows, per):                # --quick has no 2018-on months
                M[(g, e, v, per)] = sc.metrics(sc.pick_rows(rows, per), g)
    for g in goals:
        for e in edges:
            for per in PERIODS:
                if (g, e, PRESET, per) not in M:
                    continue
                print(f"\ngoal {g}x  edge {e}  period {per} ({M[(g, e, PRESET, per)]['n']} months)")
                print("  variant   | P(goal)%  P(SO)%  P(ruin)%  median end  10th pct end")
                for v in pool:
                    x = M[(g, e, v, per)]
                    print(f"  {name(v):9s} | {x['pg']:7.1f}  {x['pso']:6.1f}  {x['pru']:7.1f}  {x['med']:9.2f}x  "
                          f"{x['p10']:10.2f}x{'   <- preset' if v == PRESET else ''}")
    lap("sweep and tables")

    # ---- check 4
    want_pg = {3: 39.7, 4: 28.8, 5: 22.8}
    ok4 = True
    if not quick:
        parts = []
        for g in goals:
            pg = M[(g, 1.0, PRESET, "all")]["pg"]
            ok = round(pg, 1) == want_pg[g]
            ok4 &= ok
            parts.append(f"{g}x {pg:.1f}% (run 1: {want_pg[g]})")
        print(f"CHECK 4 cap 50 reproduces run 1 with fixes, edge 1.0, all {len(months)} months: " + "; ".join(parts)
              + f" -> {'PASS' if ok4 else 'FAIL'}")
    else:
        print("CHECK 4 skipped in --quick (first 40 months only)")

    if quick:
        for g in goals:
            for v in pool:
                if (g, v) in BIND:
                    print(f"goal {g}x {name(v)}: s_dyn below the schedule in {BIND[(g, v)][0]:.1f}% of rounds, "
                          f"{BIND[(g, v)][1]:.1f}% of days")
        print("QUICK run finished (no selection).")
        return

    # ---- selection
    print("=" * 100)
    print("SELECTION (chosen on 'to 2017' only)")
    pick, bst, why, whys = {}, {}, {}, {}
    statics = [v for v in pool if v[0] == "s"]
    for g in goals:
        pick[g], why[g] = select(g, M, pool)
        bst[g], whys[g] = select(g, M, statics)
        print(f"goal {g}x, all 12:")
        for s_ in why[g]:
            print(f"   {s_}")
        print(f"   PICK {name(pick[g])}")
        print(f"goal {g}x, best static (7):")
        for s_ in whys[g]:
            print(f"   {s_}")
        print(f"   BEST STATIC {name(bst[g])}")
    print("\nCONFIRM on '2018 on':")
    verdict = {}
    for g in goals:
        v = pick[g]
        for e in edges:
            for lab, ref in (("cap 50", PRESET), ("best static", bst[g])):
                a, bb = M[(g, e, v, "2018 on")], M[(g, e, ref, "2018 on")]
                print(f"goal {g}x edge {e}: {name(v)} P(goal) {a['pg']:.1f}% P(SO) {a['pso']:.1f}% vs {lab} {name(ref)} "
                      f"P(goal) {bb['pg']:.1f}% P(SO) {bb['pso']:.1f}%")
        if v == PRESET:
            verdict[g] = "no variant better than the preset"
        elif not beats(M, g, v, PRESET):
            verdict[g] = "FAIL (not better than cap 50)"
        elif v[0] == "d" and not beats(M, g, v, bst[g]):
            verdict[g] = "dynamic does not beat the best static"
        else:
            verdict[g] = "PASS"
        print(f"goal {g}x VERDICT: {verdict[g]}")
    lap("selection")

    # ---- tester months (check only)
    print("=" * 100)
    print("CHECK ONLY (never used to choose): 21 tester months 2024.01-2025.09, edge 1.0, mode lg, preset")
    tchk = {}
    for g in goals:
        res = {}
        for v in sorted({pick[g], bst[g], PRESET}, key=ORDER.index):
            rr = [play(S[1.0], *mod.MONTHS[pd.Period(f"{rn['month'][:4]}-{rn['month'][4:]}", "M")], v, g, rt)
                  for rn in runs[g]]
            res[v] = (sum(x[0] >= g * mod.TOL for x in rr), sum(bool(x[1]) for x in rr))
        t = (sum(rn["mult"] >= g * mod.TOL for rn in runs[g]), sum(rn["so"] is not None for rn in runs[g]))
        tchk[g] = (res, t, len(runs[g]))
        print(f"goal {g}x ({len(runs[g])} months): " + " | ".join(f"{name(v)}: goal {x[0]}, SO {x[1]}" for v, x in res.items())
              + f" | tester (cap 50): goal {t[0]}, SO {t[1]}")

    print("=" * 100)
    print("HOW OFTEN s_dyn BINDS below the goal schedule (edge 1.0, day-open sizing calls, all 184 rounds)")
    for g in goals:
        for t in THRS:
            bd = BIND[(g, ("d", t))]
            print(f"goal {g}x dyn {t}: {bd[0]:.1f}% of rounds, {bd[1]:.1f}% of played days")

    # ---- summary
    print("=" * 100)
    print("SIZE CAP 2 SUMMARY")
    print("selection rule: see the verbatim block above (highest P(goal) to 2017 at edge 1.0; lowest P(SO) within 1.0 pp; "
          "edge 0.7 floor; confirm on 2018 on against cap 50 and, if dynamic, against best static)")
    print(f"OM_MAX {DYN['om_max']:.5f} (median {float(np.median(om_day)):.5f})")
    for g in goals:
        print(f"goal {g}x: PICK {name(pick[g])}, BEST STATIC {name(bst[g])}, VERDICT {verdict[g]}")
        for per, tag in (("to 2017", "selection half"), ("2018 on", "confirm half  ")):
            for e in edges:
                line = []
                for lab, v in (("pick", pick[g]), ("best static", bst[g]), ("cap 50", PRESET)):
                    x = M[(g, e, v, per)]
                    line.append(f"{lab} {name(v)} P(goal) {x['pg']:.1f}% P(SO) {x['pso']:.1f}%")
                print(f"   {tag} edge {e}: " + " | ".join(line))
        res, t, n = tchk[g]
        print("   tester-month check only: " + " | ".join(f"{name(v)} goal {x[0]} SO {x[1]}" for v, x in res.items())
              + f" | tester goal {t[0]} SO {t[1]} of {n}")
        print("   s_dyn binds (rounds/days %): " + ", ".join(f"thr {t}: {BIND[(g, ('d', t))][0]:.0f}/{BIND[(g, ('d', t))][1]:.0f}"
                                                              for t in THRS))
    print(f"CHECKS: 1 (sc copy/identity/C1/unit) {'PASS' if chk1 else 'FAIL'} | 2 (dyn off == cap 50) "
          f"{'PASS' if ok2 else 'FAIL'} | 3 (s_dyn unit test) {'PASS' if ok3 else 'FAIL'} | 4 (cap 50 reproduces run 1) "
          f"{'PASS' if ok4 else 'FAIL'} | 5 (holdout) {'PASS' if ho_ok else 'FAIL'}")
    print("TRIALS: 12 variants x 3 goals = 36 trials in this run, plus run 1's 9 x 3 = 27 (63 in all for the candidate)")
    print("STATED LIMITS: the noise leg is round 4's constant ticket (marketdata/histdata/NSXUSD_M1.csv.gz is missing); "
          "noise pnl is not rescaled to the EA's vol sizing; the EA sizes on balance, the model on live equity; the other "
          "legs have no intraday path (booked at the close, their open loss never enters the stop-out check); P(goal) is an "
          "upper bound; OM_MAX is a constant where the EA would compute its own planned leg margin")
    lap("summary")


if __name__ == "__main__":
    try:
        main()
    finally:
        mod.run_round = _ORIG_RUN
