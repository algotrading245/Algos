"""AurumHydra goal EA, run 3 (the last) of hydra_size_cap: static caps 20-50 and a CLIP-AWARE dynamic margin cap, with a
degeneracy guard, against the preset 50.

Why: run 2's dynamic cap (research/hydra_size_cap2.py) was void (reviewer): it projected margin BEFORE the EA's 50%
free-margin clip, summed all the day's tickets with one constant OM_MAX whether open together or not, so s_dyn <= 2.9
at every threshold, it bound on 100% of days and the test said nothing. Run 3 fixes that and refuses to give a verdict
if the new cap is degenerate again.

Engine: research/hydra_goal_margin_model.py ("mod", imported, NOT edited), research/hydra_size_cap.py ("sc", imported,
NOT edited: assemble_fixed, open_ratio_fixed patched into mod.open_ratio, metrics, pick_rows, holdout guard, check C),
research/hydra_size_cap2.py ("c2", NOT edited; its play / run_round_dyn pattern is reused below). Mode "lg", 23 days, vol
0.0156, goals 3/4/5, edges 1.0 and 0.7, the 184 month-start rounds (months with >= 15 days), nothing after 2025-09.

THE PROJECTION (proj_margin), what the EA can compute at the day's open bar a = E.starts[d], in the EA's order, with
the clip applied order by order, using the engine's own functions mod.open_ratio (as patched by sc.open_ratio_fixed)
and mod.legs_margin so the projection and the engine agree by construction:
  1. HOLD  mirrors mod.ea_day lines 1022-1038: T = eq*s*pos[a] (pos is decided at yesterday's 22:00); no trade inside the
     25% band; a buy is min(diff, clip*free/ag) with free = max(eq - H*ag - G*af, 0) (no ticket is open yet); T <= 0
     closes the hold.
  2. GRID  mirrors lines 1101-1112: levels are added one by one, n = min(base, clip*free/af), free = eq - H*ag - G*af
     after the levels already placed, until GRID_LEVELS (4). Two scenarios, the worse one counts: CONTINUE (the grid
     open in the state keeps its levels and adds up to 4 of the stored cycle base) and FRESH (the grid is closed and a
     new cycle starts: base = max(eq - fh, 0)*s*GRID_RISK/(GRID_RISK_STEPS*unit), line 1104, with fg = 0 after the
     close as at line 1100; unit = E.unitp[a], the step the PREVIOUS close set, so nothing after the open is used).
  3. OTHER LEGS mirror lines 1042-1048: the plan's tickets are opened in the engine's order, each at hr = its window
     start, free = eq - H*ag - G*af - mod.legs_margin(tickets already open at hr), ratio = mod.open_ratio(...) (the
     part-by-part clip of Legs.mqh:625 / 1749 for the multi-part tickets).
  4. Mproj = H*ag + G*af + PEAK over the hours of mod.legs_margin of all the tickets (tickets open together overlap
     there, tickets in disjoint windows do not add: the mod.legs_margin basis), level = eq / Mproj.
Everything is in the state (eq, H, open grid levels, stored base, fh, fg: the EA's own state) or at the open (pos[a],
unitp[a]) or calendar (DST flag, FixDay); no bar after a is read.

THE PLAN (the other legs' tickets, not known at the open). The tickets of E.tix are built from realised outcomes (a
leg's ticket exists only on days it traded, window and size can come from the day's prices), so using them would look
ahead. The plan is a per-leg constant fitted on 2010-06..2017-12 ONLY (S[1.0].tix): per (leg, US-DST flag) the most
common window/segment shape, the MEDIAN notional per segment (per unit of eq*size, FixDay boost removed) and the mean
part shares; on a FixDay the fix, cross and Tokyo notionals get the preset boost (x2, calendar-known). The plan holds
every leg on every day (the EA cannot rule a leg out at the open). It is a stated LIMIT: a leg that does not trade is
still projected; a leg bigger than its median is under-projected; Tokyo, Meridian and dip windows vary by day and the
modal window is used.

s_dyn(thr) = the largest s on the 0.01 grid in [0, 50] with eq/Mproj(s) >= thr (hi if the level at hi already meets thr;
0 if the level at s = 0, which keeps the open grid, is already below thr). No closed form exists (clip, band, parts),
so bisection on the grid; the projection is non-increasing in s (checked in unit test U3). Size = min(goal_size, 50,
s_dyn), also inside the grid's intraday sizef(eq) as in c2 (eq = live equity, the rest of the snapshot from the open).
thr 0 = off (reproduces cap 50 exactly, check 2).

PRE-REGISTRATION (written before any number): dynamic thresholds 1.1, 1.25, 1.5, 2.0, 3.0 (level eq/Mproj after the
clip; stop-out is 0.5; a fully clipped 5-pair leg alone leaves the level near 1.03, so thresholds above 1 are the
meaningful ones); static caps 20, 25, 30, 35, 40, 45, 50 (repeats of run 2, not new trials). DEGENERACY GUARD, printed
BEFORE the sweep, on the to-2017 days of the cap-50 path (edge 1.0, goals 3/4/5 pooled): bind share = share of days with
s_dyn < goal_size, and the median s_dyn on those days. A threshold with bind share > 90% or < 5%, or median bound s_dyn
< 15, is DEGENERATE and dropped from the pool. All five degenerate: "ALL DEGENERATE: no verdict, close with cap 50" and
no sweep. New trials = (non-degenerate thresholds) x 3 goals.

Limits (printed too): noise leg is round 4's constant ticket because marketdata/histdata/NSXUSD_M1.csv.gz is missing;
noise pnl not rescaled; the EA sizes on balance, the model on live equity; other legs have no intraday path; P(goal) is
an upper bound; the plan is a per-leg constant (above); the projection ignores the order costs (HC, GC) and a
panic-dead grid; the intraday sizef uses the day-open snapshot of the hold and the grid.

The full run writes nothing but stdout.

    python research/hydra_size_cap3.py           (full, edges 1.0 and 0.7)
    python research/hydra_size_cap3.py --quick   (smoke test: goal 3, edge 1.0, cap 50 and dyn 1.5, first 40 months)
"""
import copy
import inspect
import math
import sys
import time
from collections import Counter
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
THRS = [1.1, 1.25, 1.5, 2.0, 3.0]          # pre-registered
STEP = 0.01
BOOSTED = ("fix", "cross", "tokyo")
# order = closeness to the preset: static larger cap first, then static before dynamic, dynamic lower threshold first
ORDER = [("s", c) for c in sorted(STATIC, reverse=True)] + [("d", t) for t in sorted(THRS)]
PRESET = ("s", 50)
T0 = [time.time()]

SELECTION_RULE = """SELECTION RULE (fixed before any number is seen). Variants: static caps 20, 25, 30, 35, 40, 45, 50 and dynamic
min(50, s_dyn) at thresholds 1.1, 1.25, 1.5, 2.0, 3.0 less those the degeneracy guard marks DEGENERATE (the pool). For
each goal 3, 4, 5, on "to 2017" (2010-06..2017-12):
 a. best = the highest P(goal) at edge 1.0 over all variants of the pool.
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


# ---------------------------------------------------------------- the plan (other legs, no look-ahead)

DYN = dict(log=None, probe=None, tag=None, plan_for=None)


def fit_plan(tix, fixday, dst, day_ix):
    """Per (leg, DST flag): most common (h0, h1, segment hours), median notional per segment (FixDay boost removed),
    mean part shares, over the tickets on the days day_ix (the to-2017 days only)."""
    groups = {}
    for i in day_ix:
        for t in tix[i]:
            f = mod.BOOST if (fixday[i] and t[7] in BOOSTED) else 1.0
            segs = tuple((hs, he, nt / f) for hs, he, nt in t[2])
            groups.setdefault((t[7], bool(dst[i])), []).append((t[0], t[1], segs, t[3], t[8]))
    plan = {}
    for key, lst in groups.items():
        shape = lambda x: (x[0], x[1], tuple((hs, he) for hs, he, _ in x[2]))
        shp = Counter(shape(x) for x in lst).most_common(1)[0][0]
        mem = [x for x in lst if shape(x) == shp]
        ln = Counter(len(x[4]) for x in mem).most_common(1)[0][0]
        sh = np.mean([x[4] for x in mem if len(x[4]) == ln], axis=0)
        sh = tuple(float(v) for v in sh / sh.sum())
        segs = tuple((hs, he, float(np.median([x[2][k][2] for x in mem]))) for k, (hs, he) in enumerate(shp[2]))
        plan[key] = dict(h0=shp[0], h1=shp[1], segs=segs, kd=mem[0][3], shares=sh, n=len(mem), of=len(lst))
    return plan


def make_plan_for(plan, fixday, dst):
    cache = {}
    swap = {"fix": "cross", "cross": "fix"}                     # sc.assemble_fixed's sort key (fix before cross)
    names = sorted({k[0] for k in plan})

    def plan_for(d):
        key = (bool(dst[d]), bool(fixday[d]))
        if key not in cache:
            out = []
            for nm in names:
                p = plan.get((nm, key[0])) or plan.get((nm, not key[0]))
                f = mod.BOOST if (key[1] and nm in BOOSTED) else 1.0
                segs = [(hs, he, nt * f) for hs, he, nt in p["segs"]]
                out.append((p["h0"], p["h1"], segs, p["kd"], 0.0, True, max(s_[2] for s_ in segs), nm, p["shares"]))
            out.sort(key=lambda t: (t[0], swap.get(t[7], t[7])))
            cache[key] = out
        return cache[key]
    return plan_for


# ---------------------------------------------------------------- the clip-aware projection

def snap_of(S):
    """The EA's own state at the day's open: (H, G open, levels open, stored cycle base, fh, fg)."""
    lv = S["lv"]
    return (S["H"], sum(lv), len(lv), S["base"], S["fh"], S["fg"])


def proj_margin(E, d, s, eq, snap, plan, rt, clip):
    """Peak margin (round-equity units) of the day's plan at size s, equity eq, after the clip, in the EA's order:
    hold, grid (worse of CONTINUE / FRESH), then the plan's tickets. See the docstring for the mod.ea_day lines."""
    H0, G0, nlv, base0, fh, fg = snap
    ag, af, ao = rt.ag, rt.af, rt.ao
    a = E.starts[d]
    k0 = eq * s
    H = H0
    T = eq * s * E.pos[a]
    if T <= 0.0:                                               # ea_day 1023-1026: the hold is closed
        H = 0.0
    else:
        diff = T - H
        if abs(diff) > mod.HOLD_BAND * max(T, H):              # 1029
            if diff > 0.0:
                free = max(eq - H * ag - G0 * af, 0.0)         # 1031 (no ticket open yet)
                H += min(diff, clip * free / ag) if ag > 0 else diff
            else:
                H = T
    u = E.unitp[a] if E.unitp[a] > 0.0 else E.unit[a]
    scen = []
    if nlv > 0:
        scen.append((G0, nlv, base0))                          # the open grid continues, stored base
    if u > 0.0:
        scen.append((0.0, 0, max(eq - fh, 0.0) * s * mod.GRID_RISK / (mod.GRID_RISK_STEPS * u)))   # 1100, 1104
    if not scen:
        scen.append((0.0, 0, 0.0))
    h_a = E.hour[a]
    hrs = sorted({max(hs, h_a) for t in plan for hs, _, _ in t[2]} | {max(t[0], h_a) for t in plan})
    worst = 0.0
    for G, n0, base in scen:
        for _ in range(n0, mod.GRID_LEVELS):                   # 1105-1111
            free = max(eq - H * ag - G * af, 0.0)
            n = min(base, clip * free / af) if af > 0 else base
            if n <= 1e-9:
                break
            G += n
        rat = [None] * len(plan)
        for j, t in enumerate(plan):                           # 1044-1048
            hr = max(t[0], h_a)
            lm = mod.legs_margin(plan, rat, hr, k0, ag, af, ao)
            free = max(eq - H * ag - G * af - lm, 0.0)
            rat[j] = mod.open_ratio(t, free, k0, ag, af, ao, clip)
        peak = max((mod.legs_margin(plan, rat, hr, k0, ag, af, ao) for hr in hrs), default=0.0)
        worst = max(worst, H * ag + G * af + peak)
    return worst


def level_at(E, d, s, eq, snap, plan, rt, clip):
    m_ = proj_margin(E, d, s, eq, snap, plan, rt, clip)
    return math.inf if m_ <= 0.0 else eq / m_


def s_dyn(E, d, eq, snap, plan, rt, thr, hi, clip=mod.CLIP):
    """Largest s on the 0.01 grid in [0, hi] with level >= thr; hi if the level at hi meets thr; 0 if even s = 0 fails."""
    if thr <= 0 or eq <= 0 or hi <= 0:
        return hi
    ok = lambda s: level_at(E, d, s, eq, snap, plan, rt, clip) >= thr - 1e-12
    if ok(hi):
        return hi
    if not ok(0.0):
        return 0.0
    lo, up = 0, int(hi / STEP) + 1                             # lo feasible, up infeasible (level monotone in s)
    while up - lo > 1:
        mid = (lo + up) // 2
        if ok(mid * STEP):
            lo = mid
        else:
            up = mid
    return lo * STEP


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
    log, probe, plan_for = DYN["log"], DYN["probe"], DYN["plan_for"]
    rt = SimpleNamespace(ag=a_gold, af=a_fx, ao=ao)
    for k in range(min(days, d1 - d0)):
        d = d0 + k
        eq = S["eq"]
        left = days - k
        size = mod.goal_size(eq, goal, left, cap, vol)
        if thr > 0:
            snap, plan_d = snap_of(S), plan_for(d)
            sd = s_dyn(E, d, eq, snap, plan_d, rt, thr, min(size, BASE))
            if log is not None:
                log.append(sd < size - 1e-12)
            size = min(size, sd)

            def sizef(x, left=left, snap=snap, plan_d=plan_d, d=d):
                v = mod.goal_size(x, goal, left, cap, vol)
                return s_dyn(E, d, x, snap, plan_d, rt, thr, min(v, BASE))
        else:
            if probe is not None:
                probe.append((DYN["tag"], d, eq, size, snap_of(S)))

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


# ---------------------------------------------------------------- unit tests

def unit_test_hand():
    """U1, hand-computed (ag 0.005, af 0.01, ao 0.01, eq 1, clip 0.5; stub E: one day, pos, unitp, hour 1).
    A  pos 2, unit 0.007, s = 2: T = 4, add = min(4, 0.5*1/0.005 = 100) = 4, hold margin 0.02. Grid base = 1*2*0.035/(10*0.007)
       = 1.0 per level, free stays > 0.95 so n = min(1, 0.5*free/0.01 >= 47) = 1: G = 4, margin 0.04. M = 0.06, level 16.6667.
    B  same, s = 60: T = 120, add = min(120, 100) = 100, hold margin 0.5. base = 30. free 0.5: n1 = min(30, 25) = 25;
       free 0.25: n2 = 12.5; free 0.125: n3 = 6.25; free 0.0625: n4 = 3.125. G = 46.875, margin 0.46875. M = 0.96875,
       level 1.0322581.
    C  pos 0, unit 1e9 (no grid), one fx ticket (16, 18, [10.0]) of one part: want = k0*10*0.01 = 0.1*s.
       s = 1: ratio 1, margin 0.1, level 10.  s = 20: ratio = min(1, 0.5/(2.0)) = 0.25, margin = 20*0.25*10*0.01 = 0.5, level 2.0
       (a single clipped order never takes the level under 2: it stays 2.0 for every s >= 5).
    D  s_dyn on C: thr 3 -> 1/(0.1 s) >= 3 -> s <= 3.3333 -> 3.33;  thr 2.0 -> 50 (level 2.0 at every s);  thr 1.5 -> 50.
    E  grid carried: pos 0, unit 0.007, open grid G0 = 60 (4 levels, nothing to add), eq 1: level at s = 0 is 1/(0.01*60) = 1.6667.
       thr 2 -> s_dyn 0 (even s = 0 fails).  thr 1.5: the FRESH scenario grows as G = 2 s (base 0.5 s, 4 levels, no clip
       binding) and passes the open grid at s = 30; level >= 1.5 needs G <= 66.667 -> s <= 33.333 -> 33.33."""
    ag, af, ao = 0.005, 0.01, 0.01
    rt = SimpleNamespace(ag=ag, af=af, ao=ao)
    st = lambda pos, unit: SimpleNamespace(starts=[0, 1], pos=[pos], unitp=[unit], unit=[unit], hour=[1])
    fresh = (0.0, 0.0, 0, 0.0, 0.0, 0.0)
    tk = [(16, 18, [(16, 18, 10.0)], 1, 0.0, True, 10.0, "x", (1.0,))]
    lv = lambda E, s, p, sn=fresh, c=0.5: level_at(E, 0, s, 1.0, sn, p, rt, c)
    sdy = lambda E, thr, p, sn=fresh: s_dyn(E, 0, 1.0, sn, p, rt, thr, 50.0)
    EA, EC, EE = st(2.0, 0.007), st(0.0, 1e9), st(0.0, 0.007)
    carried = (0.0, 60.0, 4, 15.0, 0.0, 0.0)
    t = [("A s=2 level 16.6667", lv(EA, 2.0, []), 1 / 0.06),
         ("B s=60 clip binds, level 1.0322581", lv(EA, 60.0, []), 1 / 0.96875),
         ("C s=1 level 10", lv(EC, 1.0, tk), 10.0),
         ("C s=20 level 2.0", lv(EC, 20.0, tk), 2.0),
         ("D thr 3 -> 3.33", sdy(EC, 3.0, tk), 3.33),
         ("D thr 2.0 -> 50", sdy(EC, 2.0, tk), 50.0),
         ("D thr 1.5 -> 50", sdy(EC, 1.5, tk), 50.0),
         ("E level at s=0 with G0 60: 1.6667", lv(EE, 0.0, [], carried), 1 / 0.6),
         ("E thr 2 -> 0", sdy(EE, 2.0, [], carried), 0.0),
         ("E thr 1.5 -> 33.33", sdy(EE, 1.5, [], carried), 33.33)]
    print("=" * 100)
    print("UNIT TEST U1 hand-computed projection and s_dyn (answers in the function's docstring)")
    oks = []
    for lab, got, want in t:
        ok = abs(got - want) < 1e-5
        oks.append(ok)
        print(f"  {lab}: got {got:.6f} -> {'PASS' if ok else 'FAIL'}")
    return all(oks)


def frozen_view(E, d, plan_d):
    """A copy of the edge set in which day d has no price move (returns, lows, highs, swap night = 0, no penalty), the
    grid step is the one the projection uses, and the day's tickets are the plan: the engine then books exactly the
    prices the projection sees."""
    V = copy.copy(E)
    a, e = E.starts[d], E.starts[d + 1]
    for nm in ("gret", "glow", "aret", "alo", "ahi", "night"):
        x = list(getattr(E, nm))
        x[a:e] = [0.0] * (e - a)
        setattr(V, nm, x)
    u = E.unitp[a] if E.unitp[a] > 0.0 else E.unit[a]
    x = list(E.unit)
    x[a:e] = [u] * (e - a)
    V.unit = x
    V.pen = 0.0
    V.tix = list(E.tix)
    V.tix[d] = list(plan_d)
    return V


def engine_levels(V, d, size, S, rt):
    """Run mod.ea_day (clip off) and return the margin levels the engine books at the opening instant of each order:
    after the hold order, after each grid level, and (at every ticket-loop step and after it) with the tickets opened so
    far. Read with a line tracer from the engine's own locals (eq, H, G, omm, tix, rat, hr, k0); mod is not edited."""
    lines, first = inspect.getsourcelines(mod.ea_day)
    find = lambda txt: [first + i for i, l_ in enumerate(lines) if l_.strip().startswith(txt)]
    l_hold, l_grid_add = find("eq -= add * HC"), find("G += n")
    l_tk, l_end = find("if rat[j] is None and t[0] <= hr < t[1]:"), find("omm = legs_margin(tix, rat, hr")
    assert len(l_hold) == 1 and len(l_grid_add) == 1 and len(l_tk) == 1 and len(l_end) == 1
    kind = {l_hold[0]: "hold", l_grid_add[0] + 1: "grid", l_tk[0]: "tk", l_end[0]: "tk"}
    code, rec = mod.ea_day.__code__, []
    ag, af, ao = rt.ag, rt.af, rt.ao

    def local(frame, event, arg):
        if event == "line" and frame.f_lineno in kind:
            f = frame.f_locals
            if kind[frame.f_lineno] == "tk":
                m_ = f["H"] * ag + f["G"] * af + mod.legs_margin(f["tix"], f["rat"], f["hr"], f["k0"], ag, af, ao)
            else:
                m_ = f["H"] * ag + f["G"] * af + f["omm"]
            if m_ > 0:
                rec.append(f["eq"] / m_)
        return local

    def glob(frame, event, arg):
        return local if frame.f_code is code else None

    hc, gc = mod.HC, mod.GC
    mod.HC = mod.GC = 0.0                                      # no order cost: eq stays eq0 on the frozen day
    sys.settrace(glob)
    try:
        stopped = mod.ea_day(V, d, size, S, ag, af, 0.0, lambda x: size, ao, 1, 1e12, True)
    finally:
        sys.settrace(None)
        mod.HC, mod.GC = hc, gc
    return rec, stopped


def unit_test_engine(E, plan_for, rt, day_ix):
    """U2: on to-2017 days, mod.ea_day at size s_dyn with the clip OFF (1e12; C1 no-clip branch), levels booked at each
    order's opening instant >= thr - 1e-9 whenever s_dyn > 0. Two states: flat (new_state) and carried (open hold, a
    2-level grid with stored base, floating pnl)."""
    thrs = [1.1, 1.25, 1.5, 2.0, 3.0]
    print("=" * 100)
    print(f"UNIT TEST U2 engine agreement, clip off, frozen day, {len(day_ix)} to-2017 days x {len(thrs)} thresholds x "
          f"2 states")
    runs = orders = bad = zero = 0
    worst = math.inf
    for d in day_ix:
        pl = plan_for(d)
        V = frozen_view(E, d, pl)
        for kind_ in ("flat", "carried"):
            for thr in thrs:
                S = mod.new_state()
                if kind_ == "carried":
                    S.update(eq=1.3, H=0.8, lv=[0.6, 0.6], s=1, base=0.6, fh=0.03, fg=-0.02)
                snap, eq = snap_of(S), S["eq"]
                sd = s_dyn(V, d, eq, snap, pl, rt, thr, BASE, clip=1e12)
                if sd <= 0:
                    zero += 1
                    continue
                rec, _ = engine_levels(V, d, sd, S, rt)
                runs += 1
                orders += len(rec)
                if rec:
                    worst = min(worst, min(rec) - thr)
                    bad += sum(1 for x in rec if x < thr - 1e-9)
    ok = bad == 0 and runs > 0
    print(f"  {runs} engine runs ({zero} with s_dyn 0 skipped), {orders} order-instant levels read, below thr - 1e-9: "
          f"{bad}; smallest (level - thr) {worst:.3e} -> {'PASS' if ok else 'FAIL'}")
    return ok


def unit_test_monotone(E, plan_for, rt, day_ix):
    """U3: the level is non-increasing in s on a 0.5 grid (what the bisection relies on), real plan, clip 0.5, counted
    where the level is >= 1.05 (the thresholds are >= 1.1; with the clip the level saturates at about 1.0 and wobbles
    by < 0.01 there, which the bisection never meets)."""
    print("=" * 100)
    grid = [0.5 * i for i in range(0, 101)]
    viol = 0
    n = 0
    worst_v = []
    d_str = lambda d: str(mod.DAYS_IDX[d].date())
    for d in day_ix:
        pl = plan_for(d)
        for snap, eq in (((0.0, 0.0, 0, 0.0, 0.0, 0.0), 1.0), ((0.8, 1.2, 2, 0.6, 0.03, -0.02), 1.3)):
            lv_ = [level_at(E, d, s, eq, snap, pl, rt, mod.CLIP) for s in grid]
            n += 1
            for i_, (x, y) in enumerate(zip(lv_, lv_[1:])):
                if y > x + 1e-9 and min(x, y) >= 1.05:          # below ~1.0 the clip saturates; no threshold lives there
                    viol += 1
                    if len(worst_v) < 5 or (y - x) > worst_v[-1][0]:
                        worst_v.append((y - x, d, grid[i_], x, y, snap))
                        worst_v.sort(key=lambda z: -z[0])
                        del worst_v[5:]
    for w_ in worst_v:
        print(f"  violation +{w_[0]:.4g} day {d_str(w_[1])} s {w_[2]}->{w_[2] + 0.5}: level {w_[3]:.5f} -> {w_[4]:.5f} snap {w_[5]}")
    ok = viol == 0
    print(f"UNIT TEST U3 level non-increasing in s (0.5 grid to 50), {n} day-states: violations {viol} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------- selection (as c2)

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

    print(SELECTION_RULE)
    print(f"PRE-REGISTERED dynamic thresholds (level eq/Mproj after the clip >= thr): {THRS}; statics {STATIC}; degeneracy "
          f"guard: bind share > 90% or < 5%, or median bound s_dyn < 15 -> DEGENERATE")
    print("=" * 100)

    # ---- part 0: data (as c2 / sc.main)
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
    print(f"CHECK 4 holdout: {len(all_months)} months {all_months[0][0]} .. {all_months[-1][0]}, last day used "
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

    # ---- the plan: fitted on 2010-06..2017-12 only
    days_ix = pd.DatetimeIndex(mod.DAYS_IDX)
    dst = np.array([t.dst().total_seconds() > 0 for t in (days_ix + pd.Timedelta(hours=12)).tz_localize("America/New_York")])
    sel_days = [i for i, d in enumerate(mod.DAYS_IDX) if pd.Timestamp("2010-06-01") <= d <= pd.Timestamp("2017-12-31")]
    plan = fit_plan(S[1.0].tix, L.fixday, dst, sel_days)
    plan_for = make_plan_for(plan, L.fixday, dst)
    DYN["plan_for"] = plan_for
    print("=" * 100)
    print(f"THE PLAN (per-leg constants per unit of eq*size, fitted on {len(sel_days)} days 2010-06..2017-12 only; every "
          f"leg on every day; FixDay x{mod.BOOST} on fix, cross, tokyo)")
    for (nm, dflag), p in sorted(plan.items()):
        print(f"  {nm:9s} DST {int(dflag)}: window {p['h0']}-{p['h1']}, segments "
              + ", ".join(f"{hs}-{he}: {nt:.3f}" for hs, he, nt in p["segs"])
              + f", parts {len(p['shares'])}, kind {('gold', 'fx', 'other')[p['kd']]}, modal shape in {p['n']} of "
              f"{p['of']} tickets")
    ex = next(d for d in sel_days if not L.fixday[d] and dst[d])
    print(f"  plan for a plain US-DST day ({mod.DAYS_IDX[ex].date()}): peak legs margin at size 1, rates ag/af/ao = "
          f"{rt.ag:.4f}/{rt.af:.4f}/{rt.ao:.4f}: "
          f"{mod.legs_margin(plan_for(ex), [1.0] * len(plan_for(ex)), 17, 1.0, rt.ag, rt.af, rt.ao):.4f} at hour 17 (unclipped)")

    # ---- unit tests
    ok_u1 = unit_test_hand()
    step_d = max(1, len(sel_days) // (40 if quick else 120))
    test_days = sel_days[100::step_d]
    ok_u2 = unit_test_engine(S[1.0], plan_for, rt, test_days)
    ok_u3 = unit_test_monotone(S[1.0], plan_for, rt, test_days[::2])
    ok3 = ok_u1 and ok_u2 and ok_u3
    print(f"CHECK 3 unit tests (U1 hand, U2 engine agreement, U3 monotone): {'PASS' if ok3 else 'FAIL'}")
    lap("unit tests")

    # ---- check 2: dynamic off == original run_round (own loop vs mod's original), every round
    mod.run_round = run_round_dyn
    print("=" * 100)
    mx, nflag, nr = 0.0, 0, 0
    for g in goals:
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

    # ---- check 4b: cap 50 reproduces runs 1 and 2 (all months, edge 1.0, full run only)
    want_pg = {3: 39.7, 4: 28.8, 5: 22.8}
    ok_rep = True
    if not quick:
        parts = []
        for g in goals:
            rows = [(p, *play(S[1.0], d0, d1, PRESET, g, rt)) for p, d0, d1 in months]
            pg = sc.metrics(rows, g)["pg"]
            ok = round(pg, 1) == want_pg[g]
            ok_rep &= ok
            parts.append(f"{g}x {pg:.1f}% (runs 1/2: {want_pg[g]})")
        print(f"CHECK 5 cap 50 reproduces runs 1/2, edge 1.0, all {len(months)} months: " + "; ".join(parts)
              + f" -> {'PASS' if ok_rep else 'FAIL'}")
    else:
        print("CHECK 5 skipped in --quick (first 40 months only)")

    # ---- degeneracy guard: BEFORE the sweep
    print("=" * 100)
    print("DEGENERACY GUARD (to-2017 days of the cap-50 path, edge 1.0, goals pooled; bind = s_dyn < goal_size)")
    probe = []
    DYN["probe"] = probe
    for g in goals:
        DYN["tag"] = g
        for p, d0, d1 in months:
            if p.year <= 2017:
                mod.go(S[1.0], d0, d1, DAYS, BASE, VOL, g, "lg", rt, thr=0.0)
    DYN["probe"] = None
    print(f"  {len(probe)} day-open sizing calls on the cap-50 path to 2017; median goal_size "
          f"{float(np.median([x[3] for x in probe])):.1f}, share of days size = 50: "
          f"{100 * float(np.mean([x[3] >= BASE - 1e-9 for x in probe])):.1f}%")
    lap("probe cap-50 path")
    degenerate, guard_thrs = {}, THRS if not quick else [1.5]
    for thr in guard_thrs:
        per = {}
        for g, d, eq, size, snap in probe:
            sd = s_dyn(S[1.0], d, eq, snap, plan_for(d), rt, thr, min(size, BASE))
            per.setdefault(g, []).append((sd < size - 1e-12, sd, size))
        allv = [x for v in per.values() for x in v]
        bound = [x[1] for x in allv if x[0]]
        share = 100 * float(np.mean([x[0] for x in allv]))
        med = float(np.median(bound)) if bound else float("nan")
        why = []
        if share > 90:
            why.append("bind share > 90%")
        if share < 5:
            why.append("bind share < 5%")
        if not bound or med < 15:
            why.append("median bound s_dyn < 15")
        degenerate[thr] = why
        pg = "; ".join(f"{g}x {100 * float(np.mean([x[0] for x in v])):.0f}% / "
                       f"{float(np.median([x[1] for x in v if x[0]])) if any(x[0] for x in v) else float('nan'):.1f}"
                       for g, v in sorted(per.items()))
        print(f"  thr {thr}: bind share {share:.1f}% of {len(allv)} days, median bound s_dyn {med:.1f} -> "
              f"{'DEGENERATE (' + ', '.join(why) + ')' if why else 'ok'}   [per goal: bind% / median bound: {pg}]")
    lap("guard")
    live = [t for t in guard_thrs if not degenerate[t]]
    if quick:
        live = [1.5]
    print(f"NON-DEGENERATE thresholds: {live if live else 'none'}")
    checks = (f"CHECKS: 1 (sc copy/identity/C1/unit) {'PASS' if chk1 else 'FAIL'} | 2 (thr 0 == cap 50, diff 0) "
              f"{'PASS' if ok2 else 'FAIL'} | 3 (unit U1/U2/U3) {'PASS' if ok3 else 'FAIL'} | 4 (holdout) "
              f"{'PASS' if ho_ok else 'FAIL'} | 5 (cap 50 reproduces runs 1/2) "
              f"{('PASS' if ok_rep else 'FAIL') if not quick else 'skipped (quick)'}")
    if not live:
        print("ALL DEGENERATE: no verdict, close with cap 50")
        print(checks)
        print("TRIALS: 0 new (no dynamic threshold was run); the statics are repeats of run 2")
        return

    pool = [("s", c) for c in STATIC] + [("d", t) for t in live]
    if quick:
        pool = [("s", 50), ("d", 1.5)]

    # ---- sweep
    print("=" * 100)
    print(f"SWEEP: variants {[name(v) for v in pool]}, goals {list(goals)}, edges {list(edges)}, {len(months)} month "
          f"rounds, {DAYS} days, vol {VOL}, mode lg, fixed sets")
    RAW, BINDR = {}, {}
    for g in goals:
        for e in edges:
            for v in pool:
                rows, bl = [], []
                for p, d0, d1 in months:
                    DYN["log"] = [] if (v[0] == "d" and e == 1.0) else None
                    x = play(S[e], d0, d1, v, g, rt)
                    if DYN["log"] is not None:
                        bl.append((p, sum(DYN["log"]), len(DYN["log"])))
                        DYN["log"] = None
                    rows.append((p, *x))
                RAW[(g, e, v)] = rows
                if bl:
                    BINDR[(g, v)] = bl
            print(f"  done goal {g}x edge {e} ({time.time() - T0[0]:.0f} s)")
    M = {}
    for (g, e, v), rows in RAW.items():
        for per in PERIODS:
            if sc.pick_rows(rows, per):                # --quick has no 2018-on months
                M[(g, e, v, per)] = sc.metrics(sc.pick_rows(rows, per), g)

    def bind_days(g, v, per):
        bl = [x for x in BINDR.get((g, v), []) if (per == "all" or (per == "to 2017") == (x[0].year <= 2017))]
        return 100 * sum(x[1] for x in bl) / max(1, sum(x[2] for x in bl)) if bl else float("nan")

    for g in goals:
        for e in edges:
            for per in PERIODS:
                if (g, e, PRESET, per) not in M:
                    continue
                print(f"\ngoal {g}x  edge {e}  period {per} ({M[(g, e, PRESET, per)]['n']} months)")
                print("  variant   | P(goal)%  P(SO)%  P(ruin)%  median end  10th pct end  bind days%")
                for v in pool:
                    x = M[(g, e, v, per)]
                    bd = f"{bind_days(g, v, per):9.1f}" if (v[0] == "d" and e == 1.0) else "        -"
                    print(f"  {name(v):9s} | {x['pg']:7.1f}  {x['pso']:6.1f}  {x['pru']:7.1f}  {x['med']:9.2f}x  "
                          f"{x['p10']:10.2f}x  {bd}{'   <- preset' if v == PRESET else ''}")
    lap("sweep and tables")

    if quick:
        print("QUICK run finished (no selection).")
        return

    # ---- selection
    print("=" * 100)
    print("SELECTION (chosen on 'to 2017' only)")
    pick, bst, why_, whys = {}, {}, {}, {}
    statics = [v for v in pool if v[0] == "s"]
    for g in goals:
        pick[g], why_[g] = select(g, M, pool)
        bst[g], whys[g] = select(g, M, statics)
        print(f"goal {g}x, all {len(pool)}:")
        for s_ in why_[g]:
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

    # ---- summary
    print("=" * 100)
    print("SIZE CAP 3 SUMMARY")
    print("selection rule: see the verbatim block at the top (highest P(goal) to 2017 at edge 1.0; lowest P(SO) within 1.0 "
          "pp; edge 0.7 floor; confirm on 2018 on against cap 50 and, if dynamic, against best static)")
    print("dynamic cap: margin level eq/Mproj AFTER the clip, hold -> grid (continue / fresh) -> plan tickets via "
          "mod.open_ratio and mod.legs_margin, peak over the hours; plan = per-leg constants fitted 2010-06..2017-12")
    print("degeneracy guard: " + "; ".join(f"thr {t}: {'DEGENERATE' if degenerate[t] else 'ok'}" for t in guard_thrs)
          + f" -> pool dynamic {live}")
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
        print("   s_dyn binds (days %, all months, edge 1.0): "
              + ", ".join(f"thr {t}: {bind_days(g, ('d', t), 'all'):.0f}" for t in live))
    print(checks)
    print(f"TRIALS: {len(live)} non-degenerate thresholds x 3 goals = {3 * len(live)} new trials in this run (the 7 statics "
          f"are repeats of run 2); the candidate's total is run 1's 27 + run 2's 36 + {3 * len(live)} = {63 + 3 * len(live)}")
    print("STATED LIMITS: the noise leg is round 4's constant ticket (marketdata/histdata/NSXUSD_M1.csv.gz is missing); "
          "noise pnl is not rescaled to the EA's vol sizing; the EA sizes on balance, the model on live equity; the other "
          "legs have no intraday path (booked at the close, their open loss never enters the stop-out check); P(goal) is an "
          "upper bound; the plan of the other legs is a per-leg constant (median notional of 2010-06..2017-12, every leg on "
          "every day, modal window) where the EA would compute its own planned legs; the projection ignores order costs "
          "and a panic-dead grid; the intraday sizef uses the day-open snapshot of the hold and the grid")
    lap("summary")


if __name__ == "__main__":
    try:
        main()
    finally:
        mod.run_round = _ORIG_RUN
        mod.open_ratio = sc._ORIG_OPEN
