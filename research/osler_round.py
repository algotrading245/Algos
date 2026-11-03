"""Round-number stop cascades (Osler, NY Fed Staff Reports 150 and 125): enter in the direction of a cross of a 00 or 50
level, against random "arbitrary" level grids.

Paper (both read in full): after price crosses a level whose last two digits are 00 or 50 it keeps going for 1-2 hours
(stop-loss buys sit just above round numbers, stop-loss sells just below); touches without a cross reverse more often at
round levels than at arbitrary ones (58-60% vs 55-57%).  Gross effect in the paper 0.3-2.4 bp, measured with an ex post cross.

Rule tested (real-time version): levels at 00 and 50 (USDJPY xx.00/xx.50, EURUSD 1.xx00/1.xx50), or 00 only.  Entry at the
first M1 close k = 1, 3, 5, 10 pips beyond a level, given a close on the other side of that level within the previous 15
minutes.  Direction = the cross.  Exit after 15, 30, 60, 120 minutes, or (stop variant) when the M1 high/low (low for longs,
high for shorts) reaches the level minus/plus k pips; the exit is then at that stop price.  Without a stop: exit at the M1
close of the hold minute.  One trade per level per clock hour (earliest).  Sessions (server clock, = New York + 7 h):
all (01:15-23:00), London (10:00-18:00), New York (15:00-23:00 = 08:00-16:00 ET), New York after 12:30 ET (19:30-23:00).
Rollover: entries only from server 01:15 (the 15-minute look-back then starts after the 23:00-01:00 spike hours) and every
exit must fall before server 23:00 (so entry minute + hold < 23:00); weekends excluded.  No trade is entered or closed
inside the spike hours.

Costs: bid-only data, so the full round trip is charged per trade in bp of price: USDJPY 1.2 bp (measured on ticks,
research/breakout_ticks.py), EURUSD 0.8 bp (the cost the repo uses for it: london_breakout.py, atlas_scan.py).  Stress
series at 1.5x.  Sizing of the daily series: fixed notional, 1x equity per trade (overlapping trades add); gates.py fits the
weight, so scale is not critical.  Daily Sharpe over all weekdays (no-trade days are zero), sqrt(252).

Null: the identical rule on arbitrary level grids of the same spacing (50 pips; 100 pips for the 00-only variant) shifted
by random offsets that stay >= 5 pips from 00/50 (--grids, default 300).  Per variant: round minus arbitrary per trade (bp,
gross = net), percentile of the round mean in the distribution of per-grid arbitrary means, share of 10-day blocks in
which round's mean beats the pooled arbitrary mean (one-sided binomial p).  Touch reversal rate: the first time a bar's
high (low) comes within 0.01% of a level not touched in the previous 15 minutes, approaching from below (above): share
that is back on the near side 15 minutes later (round vs arbitrary 50-pip grids).

Selection and pass rule: the variant (pair x levels x k x hold x stop x session) with the best net Sharpe to 2017 (at least
300 trades to 2017); its from-2018 figures are then reported untouched.  Pass to step 8 only if round minus arbitrary is
positive in both halves AND net Sharpe at the real cost is >= 0.5 in both halves.  Arbitrary levels as good as round ones =
generic breakout, a fail.

    python research/osler_round.py            # full run (writes the trials line; candidate files only on a pass)
    python research/osler_round.py --quick    # USDJPY, 2017-2018, 20 grids, writes nothing
    python research/osler_round.py --grids 1000

Result (2026-10-18, full run, 512 variants, 300 grids): FAIL, rejected at steps 5-7.  0 of 512 variants have net
Sharpe >= 0.5 in both halves; median gross per trade -0.46 / -0.22 bp, median round minus arbitrary -0.14 / -0.09 bp.
Chosen on data to 2017 (USDJPY 00, k=1, hold 120, no stop, NY after 12:30 ET): net Sharpe -0.16 / -0.69, round minus
arbitrary +0.86 / -0.46 bp.  Touch reversal at round levels is 1-3 pp LOWER than at arbitrary ones (paper: higher).
"""
import argparse
import json
import math
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", RuntimeWarning)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "marketdata" / "histdata"
CAND = ROOT / "marketdata" / "candidates"
TRIALS = ROOT / "docs" / "trials.jsonl"
LEGS = ROOT / "marketdata" / "candidate_legs_daily.csv.gz"

PAIRS = {"USDJPY": dict(pip=0.01, cost=1.2), "EURUSD": dict(pip=0.0001, cost=0.8)}
KS = (1, 3, 5, 10)
HOLDS = (15, 30, 60, 120)
SESS = ("all", "london", "ny", "ny_late")
LOOK = 15
NV = len(KS) * len(HOLDS) * 2 * len(SESS)
SPLIT_DAY = int(np.datetime64("2018-01-01").astype("datetime64[D]").astype(int))
AR = np.arange(1, 121)


def vid(ki, hi, st, s):
    return ((ki * len(HOLDS) + hi) * 2 + st) * len(SESS) + s


def vdecode(v):
    s = v % 4
    v //= 4
    st = v % 2
    v //= 2
    hi = v % 4
    ki = v // 4
    return KS[ki], HOLDS[hi], st, SESS[s]


def sharpe(x):
    x = np.asarray(x, float)
    return x.mean() / x.std() * math.sqrt(252) if x.size > 1 and x.std() > 0 else float("nan")


def binom_p(w, n):
    """One-sided P(X >= w), X ~ Binomial(n, 0.5)."""
    if n == 0:
        return float("nan")
    return sum(math.comb(n, i) for i in range(w, n + 1)) / 2.0 ** n


# --------------------------------------------------------------------------------------------- data and step 5 checks
class Pair:
    def __init__(self, name, quick):
        self.name = name
        self.pip = PAIRS[name]["pip"]
        self.cost = PAIRS[name]["cost"]
        raw = pd.read_csv(DATA / f"{name}_M1.csv.gz")
        print(f"\n=== {name}: step 5 data check ===")
        print("columns:", list(raw.columns))
        if quick:
            a = int(pd.Timestamp("2017-01-01").timestamp())
            b = int(pd.Timestamp("2019-01-01").timestamp())
            raw = raw[(raw.time >= a) & (raw.time < b)]
        raw = raw.sort_values("time")
        dup = int(raw.time.duplicated().sum())
        raw = raw.drop_duplicates("time")
        t = raw.time.to_numpy(np.int64)
        print(f"rows {len(raw):,} (after dropping {dup} duplicate timestamps); "
              f"{pd.to_datetime(t[0], unit='s')} to {pd.to_datetime(t[-1], unit='s')} (timestamps used as server clock)")
        dt = np.diff(t)
        dts = pd.to_datetime(t[:-1], unit="s")
        big = (dt > 86400 * 1.01) & ~((dts.dayofweek == 4) & (dt <= 86400 * 3.2))
        print(f"gaps > 1 day outside Fri->Mon weekends: {int(big.sum())}", end="")
        if big.sum():
            print("  first:", [(str(dts[i].date()), round(dt[i] / 86400, 1)) for i in np.flatnonzero(big)[:8]])
        else:
            print()
        c0 = raw.close.to_numpy(float)
        ok = dt == 60
        ret = np.abs(np.diff(np.log(c0))) * 1e4
        hh = ((t[1:] % 86400) // 3600)[ok]
        rr = ret[ok]
        med = pd.Series(rr).groupby(hh).median()
        p999 = pd.Series(rr).groupby(hh).quantile(0.999)
        print("median |1-min return| bp by server hour:")
        print("  " + " ".join(f"{h:02d}:{med.get(h, float('nan')):.2f}" for h in range(24)))
        print("99.9th pct |1-min return| bp by server hour (rollover spikes show here):")
        print("  " + " ".join(f"{h:02d}:{p999.get(h, float('nan')):.1f}" for h in range(24)))
        dow = pd.to_datetime(t, unit="s").dayofweek
        mod_raw = (t % 86400) // 60
        fri = pd.Series(mod_raw[dow == 4]).groupby(pd.to_datetime(t[dow == 4], unit="s").normalize()).max()
        sun = pd.Series(mod_raw[dow == 6]).groupby(pd.to_datetime(t[dow == 6], unit="s").normalize()).min()
        print(f"last Friday bar, most common server minute-of-day {int(fri.mode().iloc[0])} "
              f"(1439 = 23:59); first Sunday bar most common {int(sun.mode().iloc[0]) if len(sun) else -1}")

        t = (t // 60) * 60
        self.t0m = int(t[0] // 60)
        n = int((t[-1] - t[0]) // 60) + 1
        self.n = n
        ix = ((t - t[0]) // 60).astype(np.int64)
        present = np.zeros(n, bool)
        present[ix] = True
        self.present = present

        def full(col):
            a = np.full(n, np.nan)
            a[ix] = raw[col].to_numpy(float)
            return a

        c = pd.Series(full("close")).ffill().to_numpy()
        lo = np.where(present, full("low"), c)
        hi = np.where(present, full("high"), c)
        self.c = c
        absmin = self.t0m + np.arange(n, dtype=np.int64)
        self.MOD = (absmin % 1440).astype(np.int32)
        dnum = absmin // 1440
        self.dnum = dnum
        self.dn0 = int(dnum[0])
        self.nd = int(dnum[-1]) - self.dn0 + 1
        wd = ((np.arange(self.nd) + self.dn0 + 3) % 7) < 5
        self.wd = wd
        dow = (dnum + 3) % 7
        inrange = present & (dow < 5) & (self.MOD >= 1380 - 1380 + 60) & (self.MOD < 1380)
        full_exp = int(((np.arange(n) >= 0) & (dow < 5) & (self.MOD >= 60) & (self.MOD < 1380)).sum())
        print(f"present minutes server 01:00-23:00 Mon-Fri: {int(inrange.sum()):,} of {full_exp:,} "
              f"({inrange.sum() / full_exp:.1%}); missing minutes are forward-filled and cannot be an entry or a no-stop exit")
        pip10 = self.pip / 10.0
        self.pip10 = pip10
        self.p = np.rint(c / self.pip * 10).astype(np.int32)
        self.lowp = np.rint(lo / self.pip * 10).astype(np.int32)
        self.highp = np.rint(hi / self.pip * 10).astype(np.int32)
        p = self.p
        pprev = np.concatenate([p[:1], p[:-1]])
        sp = pd.Series(p.astype(np.float32))
        rmin = np.nan_to_num(sp.rolling(LOOK).min().shift(1).to_numpy(), nan=0.0).astype(np.int32)
        rmax = np.nan_to_num(sp.rolling(LOOK).max().shift(1).to_numpy(), nan=0.0).astype(np.int32)
        elig = present & (dow < 5) & (self.MOD >= 60 + LOOK) & (self.MOD < 1380 - 15)
        elig[:LOOK + 2] = False
        elig[-125:] = False
        self.elig = elig
        self.gL = np.flatnonzero(elig & (p > pprev) & (rmin <= p - 10))
        self.gS = np.flatnonzero(elig & (p < pprev) & (rmax >= p + 10))
        self.PL = p[self.gL]
        self.DPL = pprev[self.gL] - self.PL
        self.RML = rmin[self.gL]
        self.PS = -p[self.gS]
        self.DPS = -pprev[self.gS] - self.PS
        self.RMS = -rmax[self.gS]
        self.blk0 = (self.dn0 - SPLIT_DAY) // 10
        blk_end = (int(dnum[-1]) - SPLIT_DAY) // 10
        self.B = blk_end - self.blk0 + 1
        self.bh = (self.blk0 + np.arange(self.B)) >= 0
        self.years = self.nd / 365.25
        print(f"eligible entry minutes {int(elig.sum()):,}; look-back bars {LOOK}; years {self.years:.1f}; "
              f"blocks {self.B}", flush=True)


# --------------------------------------------------------------------------------------------- the rule
def side_events(P, DP, RM, o, S):
    d = (P - o) % S
    L = P - d
    m = d >= 10
    m &= (DP + d) < 100
    m &= RM < L
    j = np.flatnonzero(m)
    return j, L[j], d[j], DP[j] + d[j]


def run_grid(P, o, S, keep):
    """All variants for the grid of levels o + S*m (tenth-pips).  Returns sums and counts per variant per 10-day block,
    and (keep) the trades per variant as (day index, gross bp)."""
    oS = (-o) % S
    jl, Ll, dl, dpl = side_events(P.PL, P.DPL, P.RML, o, S)
    gl = P.gL[jl]
    js, Ls, ds, dps = side_events(P.PS, P.DPS, P.RMS, oS, S)
    gs = P.gS[js]
    Lsa = -Ls
    GS = np.zeros((NV, P.B))
    GC = np.zeros((NV, P.B))
    trades = {} if keep else None
    n = P.n
    for ki, k in enumerate(KS):
        k10 = k * 10
        ml = (dl >= k10) & (dpl < k10)
        ms = (ds >= k10) & (dps < k10)
        gi = np.concatenate([gl[ml], gs[ms]])
        if gi.size == 0:
            continue
        sign = np.concatenate([np.ones(int(ml.sum())), -np.ones(int(ms.sum()))])
        L = np.concatenate([Ll[ml], Lsa[ms]]).astype(np.int64)
        order = np.argsort(gi, kind="stable")
        gi, sign, L = gi[order], sign[order], L[order]
        hr = (P.t0m + gi) // 60 - P.t0m // 60
        _, f = np.unique(L * 262144 + hr, return_index=True)
        f.sort()
        gi, sign, L = gi[f], sign[f], L[f]
        E = gi.size
        ent = P.c[gi]
        modg = P.MOD[gi]
        dn = P.dnum[gi]
        blk = (dn - SPLIT_DAY) // 10 - P.blk0
        dayi = dn - P.dn0
        lg = sign > 0
        W = np.minimum(gi[:, None] + AR[None, :], n - 1)
        X = np.empty((E, AR.size), np.int32)
        if lg.any():
            X[lg] = P.lowp[W[lg]]
        if (~lg).any():
            X[~lg] = -P.highp[W[~lg]]
        stp = np.where(lg, L - k10, L + k10)
        thr = np.where(lg, stp, -stp)
        stopped = X <= thr[:, None]
        anyh = stopped.any(1)
        fh = np.where(anyh, stopped.argmax(1) + 1, 999)
        gstop = sign * (stp * P.pip10 - ent) / ent * 1e4
        sm = (np.ones(E, bool), (modg >= 600) & (modg < 1080), modg >= 900, modg >= 1170)
        for hi, h in enumerate(HOLDS):
            okt = (modg + h) < 1380
            ex = np.minimum(gi + h, n - 1)
            pres = P.present[ex]
            ret_ns = sign * (P.c[ex] - ent) / ent * 1e4
            hit = fh <= h
            for st in (0, 1):
                if st == 0:
                    val = ret_ns
                    valid = okt & pres
                else:
                    val = np.where(hit, gstop, ret_ns)
                    valid = okt & (hit | pres)
                for s in range(len(SESS)):
                    mk = valid & sm[s]
                    v = vid(ki, hi, st, s)
                    if not mk.any():
                        continue
                    b = blk[mk]
                    GS[v] = np.bincount(b, val[mk], minlength=P.B)
                    GC[v] = np.bincount(b, minlength=P.B)
                    if keep:
                        trades[v] = (dayi[mk], val[mk], modg[mk])
    return GS, GC, trades


def halves(P, GS, GC):
    s = np.stack([GS[:, ~P.bh].sum(1), GS[:, P.bh].sum(1)], axis=1)
    c = np.stack([GC[:, ~P.bh].sum(1), GC[:, P.bh].sum(1)], axis=1)
    return s, c


def evaluate(P, ls, S, ngrids, seed, TR):
    t_start = time.time()
    label = f"{P.name} levels={ls}"
    GSr, GCr, trades = run_grid(P, 0, S, True)
    sR, cR = halves(P, GSr, GCr)
    AS = np.zeros((ngrids, NV, 2))
    AC = np.zeros((ngrids, NV, 2))
    poolS = np.zeros((NV, P.B))
    poolC = np.zeros((NV, P.B))
    rng = np.random.default_rng(seed)
    for g in range(ngrids):
        x = int(rng.integers(50, 451 if S == 500 else 851))
        if S == 1000 and x > 450:
            x += 100
        GS, GC, _ = run_grid(P, x, S, False)
        AS[g], AC[g] = halves(P, GS, GC)
        poolS += GS
        poolC += GC
        if (g + 1) % 25 == 0 or g + 1 == ngrids:
            print(f"  {label}: grid {g + 1}/{ngrids}  {time.time() - t_start:.0f}s", flush=True)
    mR = np.where(cR > 0, sR / np.maximum(cR, 1), np.nan)
    arbm = np.where(AC > 0, AS / np.maximum(AC, 1), np.nan)
    arbavg = np.nanmean(arbm, axis=0)
    valid = ~np.isnan(arbm)
    pct = ((arbm <= mR[None]) & valid).sum(0) / np.maximum(valid.sum(0), 1)
    mR_all = sR.sum(1) / np.maximum(cR.sum(1), 1)
    arb_all_g = AS.sum(2) / np.where(AC.sum(2) > 0, AC.sum(2), np.nan)
    arb_all = np.nanmean(arb_all_g, axis=0)
    pct_all = (((arb_all_g <= mR_all[None]) & ~np.isnan(arb_all_g)).sum(0)
               / np.maximum((~np.isnan(arb_all_g)).sum(0), 1))
    okb = (GCr > 0) & (poolC > 0)
    rm = GSr / np.maximum(GCr, 1)
    am = poolS / np.maximum(poolC, 1)
    win = (rm > am) & okb
    rows = []
    for v in range(NV):
        k, h, st, sess = vdecode(v)
        n_all = int(cR[v].sum())
        tr = trades.get(v)
        if tr is None or n_all == 0:
            continue
        TR[(P.name, ls, v)] = tr
        day, val, _ = tr
        net = val - P.cost
        daily = np.bincount(day, net, minlength=P.nd)[P.wd] / 1e4
        dd = np.arange(P.nd)[P.wd] + P.dn0
        pre = dd < SPLIT_DAY
        wn = int(win[v].sum())
        nb = int(okb[v].sum())
        rows.append(dict(
            pair=P.name, levels=ls, k=k, hold=h, stop=st, sess=sess, v=v, n=n_all,
            tpy=n_all / P.years, n_pre=int(cR[v, 0]), n_post=int(cR[v, 1]),
            gross_pre=mR[v, 0], gross_post=mR[v, 1], gross=mR_all[v],
            net_pre=mR[v, 0] - P.cost, net_post=mR[v, 1] - P.cost,
            sh_pre=sharpe(daily[pre]), sh_post=sharpe(daily[~pre]), sh_all=sharpe(daily),
            arb_pre=arbavg[v, 0], arb_post=arbavg[v, 1], arb=arb_all[v],
            diff_pre=mR[v, 0] - arbavg[v, 0], diff_post=mR[v, 1] - arbavg[v, 1], diff=mR_all[v] - arb_all[v],
            pct_pre=pct[v, 0], pct_post=pct[v, 1], pct=pct_all[v],
            blk_win=wn, blk_n=nb, blk_p=binom_p(wn, nb)))
    print(f"  {label} done in {time.time() - t_start:.0f}s", flush=True)
    return rows


# --------------------------------------------------------------------------------------------- touch reversals
def touch_rates(P, S, o_list):
    """Reversal share after the first touch (within 0.01%) of a level from one side: price back on the near side 15 min
    later.  Returns for each offset: [[all_pre, all_post],[ny_pre, ny_post]] as (n_touch, n_reverse)."""
    n = P.n
    tol = int(round(1e-4 * float(np.median(P.c)) / P.pip * 10))
    sh = pd.Series(P.highp.astype(np.float32))
    sl = pd.Series(P.lowp.astype(np.float32))
    hmax = np.nan_to_num(sh.rolling(LOOK).max().shift(1).to_numpy(), nan=0.0).astype(np.int32)
    lmin = np.nan_to_num(sl.rolling(LOOK).min().shift(1).to_numpy(), nan=0.0).astype(np.int32)
    pres15 = np.zeros(n, bool)
    pres15[:-15] = P.present[15:]
    ok = P.elig & pres15
    iu = np.flatnonzero(ok & (P.highp > hmax))
    idn = np.flatnonzero(ok & (P.lowp < lmin))
    sets = []
    for ii, HU, HM, C15 in ((iu, P.highp[iu], hmax[iu], P.p[iu + 15]),
                            (idn, -P.lowp[idn], -lmin[idn], -P.p[idn + 15])):
        sets.append((HU, HM, C15, P.dnum[ii] >= SPLIT_DAY, P.MOD[ii] >= 960))
    out = []
    for o in o_list:
        res = np.zeros((2, 2, 2))
        for side, (HU, HM, C15, post, ny) in enumerate(sets):
            oo = o if side == 0 else (-o) % S
            L = HM - ((HM - oo) % S) + S
            reach = (HU >= L - tol) & (HM < L - tol)
            rev = reach & (C15 < L)
            for hf in (0, 1):
                mh = post == bool(hf)
                res[0, hf, 0] += (reach & mh).sum()
                res[0, hf, 1] += (rev & mh).sum()
                res[1, hf, 0] += (reach & mh & ny).sum()
                res[1, hf, 1] += (rev & mh & ny).sum()
        out.append(res)
    return out


# --------------------------------------------------------------------------------------------- reporting
def fmt(df, cols):
    return df[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}")


def daily_series(P, tr, cost):
    day, val, _ = tr
    d = np.bincount(day, val - cost, minlength=P.nd)[P.wd] / 1e4
    idx = pd.to_datetime(np.arange(P.nd)[P.wd] + P.dn0, unit="D")
    return pd.Series(d, index=idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grids", type=int, default=300)
    ap.add_argument("--touch-grids", type=int, default=100)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--seed", type=int, default=20261018)
    a = ap.parse_args()
    ngrids = 20 if a.quick else a.grids
    ntouch = min(ngrids, 20 if a.quick else a.touch_grids)
    names = ["USDJPY"] if a.quick else list(PAIRS)
    T0 = time.time()
    TR = {}
    rows = []
    touch = {}
    pairs = {}
    for name in names:
        P = Pair(name, a.quick)
        pairs[name] = P
        for ls, S in (("00/50", 500), ("00", 1000)):
            print(f"\n--- {name} levels {ls}: round + {ngrids} arbitrary grids ---", flush=True)
            rows += evaluate(P, ls, S, ngrids, a.seed + (1 if ls == "00" else 0) + (7 if name == "EURUSD" else 0), TR)
        rng = np.random.default_rng(a.seed + 99)
        offs = [0] + [int(x) for x in rng.integers(50, 451, ntouch)]
        res = touch_rates(P, 500, offs)
        rd = res[0]
        ar = np.sum(res[1:], axis=0)
        touch[name] = (rd, ar)
    df = pd.DataFrame(rows)
    count = len(df) if False else len(names) * 2 * len(KS) * len(HOLDS) * 2 * len(SESS)
    print(f"\n\n##### RESULTS (elapsed {time.time() - T0:.0f}s); variants evaluated on round levels: {count}")

    cols = ["pair", "levels", "k", "hold", "stop", "sess", "tpy", "gross_pre", "gross_post", "net_pre", "net_post",
            "sh_pre", "sh_post", "diff_pre", "diff_post", "pct_pre", "pct_post", "blk_win", "blk_n", "blk_p"]
    ref = df[(df.k == 3) & (df.hold == 30) & (df.stop == 0)]
    print("\nReference variants (k=3 pips, hold 30 min, no stop); gross/net/diff in bp per trade, sh = net daily Sharpe,"
          " pct = share of arbitrary grids with a lower mean than round, blk = 10-day blocks round beats arbitrary:")
    print(fmt(ref, cols))
    el = df[(df.n_pre >= 300) & df.sh_pre.notna()].sort_values("sh_pre", ascending=False)
    print("\nTop 15 variants by net Sharpe to 2017 (information; the single best is the chosen one):")
    print(fmt(el.head(15), cols))
    both_pos = df[(df.diff_pre > 0) & (df.diff_post > 0)]
    sh_both = df[(df.sh_pre >= 0.5) & (df.sh_post >= 0.5)]
    print(f"\nDiagnostics over {len(df)} variants: round minus arbitrary > 0 in both halves: {len(both_pos)}; "
          f"net Sharpe >= 0.5 in both halves: {len(sh_both)}; both: "
          f"{len(both_pos[(both_pos.sh_pre >= 0.5) & (both_pos.sh_post >= 0.5)])}")
    print(f"Median round-minus-arbitrary over all variants (bp): to 2017 {df.diff_pre.median():+.3f}, "
          f"from 2018 {df.diff_post.median():+.3f}; median gross per trade {df.gross_pre.median():+.3f} / "
          f"{df.gross_post.median():+.3f}")

    print("\nTouch-without-cross reversal share (15 min after first touch within 0.01%; 50-pip grids), round vs arbitrary "
          f"({ntouch} grids); paper 58-60% vs 55-57%:")
    for name, (rd, ar) in touch.items():
        for i, nm in enumerate(("all hours", "NY hours (server 16:00-23:00)")):
            for hf, hn in enumerate(("to 2017", "from 2018")):
                rr = rd[i, hf, 1] / max(rd[i, hf, 0], 1)
                aa = ar[i, hf, 1] / max(ar[i, hf, 0], 1)
                print(f"  {name} {nm} {hn}: round {rr:.1%} ({int(rd[i, hf, 0]):,} touches) vs arbitrary {aa:.1%}  "
                      f"diff {100 * (rr - aa):+.2f} pp")

    # ---- selection
    if el.empty:
        print("\nNo variant has >= 300 trades to 2017; nothing to choose.")
        return
    best = el.iloc[0]
    P = pairs[best.pair]
    print("\n##### CHOSEN on data to 2017 (best net Sharpe to 2017):")
    print(f"  {best.pair} levels {best.levels} k={best.k} hold={best.hold} stop={'k pips' if best.stop else 'none'} "
          f"session={best.sess}")
    print(f"  to 2017 : trades {best.n_pre}, gross {best.gross_pre:+.3f} bp, net {best.net_pre:+.3f} bp, net Sharpe "
          f"{best.sh_pre:+.2f}, arbitrary {best.arb_pre:+.3f} -> round minus arbitrary {best.diff_pre:+.3f} bp "
          f"(round above {best.pct_pre:.0%} of arbitrary grids)")
    print(f"  from 2018: trades {best.n_post}, gross {best.gross_post:+.3f} bp, net {best.net_post:+.3f} bp, net Sharpe "
          f"{best.sh_post:+.2f}, arbitrary {best.arb_post:+.3f} -> round minus arbitrary {best.diff_post:+.3f} bp "
          f"(round above {best.pct_post:.0%} of arbitrary grids)")
    print(f"  all years: {best.tpy:.0f} trades/yr, net Sharpe {best.sh_all:+.2f}, round minus arbitrary "
          f"{best['diff']:+.3f} bp, percentile {best.pct:.0%}; 10-day blocks round beats arbitrary in "
          f"{best.blk_win}/{best.blk_n} (one-sided binomial p {best.blk_p:.3g})")
    c1 = best.diff_pre > 0 and best.diff_post > 0
    c2 = best.sh_pre >= 0.5 and best.sh_post >= 0.5
    passed = bool(c1 and c2)
    print(f"  pass rule: round minus arbitrary positive in both halves: {c1}; net Sharpe >= 0.5 in both halves: {c2} "
          f"-> {'PASS (to step 8)' if passed else 'FAIL'}")

    tr = TR[(best.pair, best.levels, int(best.v))]
    ser = daily_series(P, tr, P.cost)
    ser_s = daily_series(P, tr, P.cost * 1.5)
    share = float(((tr[2] >= 600) & (tr[2] < 1080)).mean())
    print(f"  stress (1.5x cost) net Sharpe {sharpe(ser_s.to_numpy()):+.2f} "
          f"(to 2017 {sharpe(ser_s[:'2017'].to_numpy()):+.2f}, from 2018 {sharpe(ser_s['2018':].to_numpy()):+.2f})")
    print(f"  share of trades with entry inside server 10:00-18:00: {share:.0%}")
    try:
        legs = pd.read_csv(LEGS, index_col=0, parse_dates=True)
        col = [c for c in legs.columns if "breakout" in c.lower()]
        print(f"  candidate_legs columns: {list(legs.columns)}")
        if col:
            b = legs[col[0]]
            j = pd.concat([ser.rename("o"), b.rename("b")], axis=1, join="inner").fillna(0)
            print(f"  daily-return correlation with {col[0]} leg: {j.o.corr(j.b):+.3f} "
                  f"(to 2017 {j.o[:'2017'].corr(j.b[:'2017']):+.3f}, from 2018 {j.o['2018':].corr(j.b['2018':]):+.3f}; "
                  f"{len(j)} days)")
    except Exception as e:
        print("  could not read breakout leg:", e)

    if a.quick:
        print("\n--quick: nothing written (no trials line, no candidate files).")
        return
    verdict = ("pass rule met" if passed else
               f"fails: diff {best.diff_pre:+.2f}/{best.diff_post:+.2f} bp, net Sharpe {best.sh_pre:+.2f}/{best.sh_post:+.2f}")
    line = json.dumps({"id": "osler_round:grid", "when": datetime.now().isoformat(timespec="seconds"),
                       "verdict": verdict, "count": count})
    txt = TRIALS.read_text() if TRIALS.exists() else ""
    with open(TRIALS, "a") as f:
        if txt and not txt.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
    print(f"\ntrials line appended: {line}")
    if passed:
        CAND.mkdir(parents=True, exist_ok=True)
        for fn, s in (("osler_round.csv", ser), ("osler_round_stress.csv", ser_s)):
            pd.DataFrame({"day": s.index.strftime("%Y-%m-%d"), "r": s.to_numpy()}).to_csv(CAND / fn, index=False)
        print(f"wrote {CAND / 'osler_round.csv'} and {CAND / 'osler_round_stress.csv'}")
        print("next: python tools/gates.py osler_round")
    else:
        print("pass rule not met: no candidate files written, gates.py not to be run.")


if __name__ == "__main__":
    main()
