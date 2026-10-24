"""Chinese macro releases and AUD/USD (Mathews, RBA Bulletin Dec 2016, Table A1): does a breakout of the 10-minute
pre-release range pay on release days, against the same clock minute on non-release days?

Paper (read in full): Chinese GDP, activity (industrial output, retail sales, FAI) and CPI/trade releases add 0.03-0.06 %
of extra absolute AUD/USD move in the -10..+10 minute window around the release (2008-16: GDP 0.06, activity 0.04, trade
0.03, CPI 0.04).  Volatility only: the paper has no direction and no cost, and does not test continuation, so the test
here compares event days with same-clock non-event days.

Data: marketdata/china_calendar_nbs.csv (NBS calendar 2015-01 to 2025-09; rows with a missing / non-HH:MM time are dropped and
counted; rows with a `note` are "flagged": kept in the main run, dropped in a robustness line; rows on one date and UTC
minute are merged into one event).  Prices: marketdata/histdata/AUDUSD_M1.csv.gz (main) and AUDCAD_M1.csv.gz (check), bid M1,
timestamps on the broker server clock (= New York local + 7 h).  Event UTC time -> America/New_York -> +7 h.  Every price
frame goes through holdout.drop() and is cut at 2025-09-30.  Weekdays only.

Step 5 (printed first, they decide whether step 6 means anything):
  a) events per series per year, dropped and flagged rows, five sample conversions;
  b) minute profile -30..+30 of mean |1-min return| (bp) on event days vs control days; control day = same server clock minute
     on every weekday of the same calendar month that is not an event day of any series.  The peak must sit at 0..+2;
  c) Table A1 replication: mean |close(t+10)-close(t-11)|/close(t-11) in %, event minus control (paired per event, the
     controls of an event averaged), bootstrap 90 % interval (2000 resamples, seed 1) per series and pooled, two periods;
  d) per event |move| over t-1..t+5 vs the 75th percentile of its control days: the events that do not exceed it are listed.

Step 6-7, the rule (fixed in advance, no grid, no fitting): R = high-low of the 10 M1 bars t-10..t-1 (t = release minute).
From bar t to bar t+59: buy stop at the range high and sell stop at the range low, each side at most once; fill at the level
or at the bar open if it gaps past it.  Stop of a long = range low, of a short = range high (same fill rule).  A bar that
touches both an entry and that trade's stop books the stop.  A bar that touches both range sides before any entry books a
long stopped out (-1 R) and nothing else for that bar.  Open trades exit at the close of bar t+59.  Round-trip cost in bp of
price: AUDUSD 1.1 (stress 2.2), AUDCAD 2.0 (stress 4.0).  Net R of a trade = (pnl/entry*1e4 - cost_bp)/(R/entry*1e4).  Events
with R = 0 are skipped and counted.  Control = the same rule at the same server minute on the control days.  Per event day
the trade results are summed in R (unit 1 R per trade).  Net Sharpe: daily series over all weekdays of the half (event-day
net R sum, 0 otherwise), sqrt(252).  Continuation diagnostic: Pearson correlation of ret over bars t-1..t+2
(close t+2 / close t-2) with ret close t+2 -> close t+60, event vs control days.

Pass rule: PASS only if, for AUDUSD at the base cost, net mean R per trade > 0 in BOTH halves (2015-2017, 2018-2025.09), event
minus control (net R per event) > 0 in BOTH halves, and net Sharpe >= 0.5 in BOTH halves.  AUDCAD is a check (same three
tests).  Per-series and pre-range-tercile splits are diagnostics only.

Limits: the sample starts 2015 (the 2010-14 calendar is missing), no trade (customs) releases, the calendar was read from
WebFetch summaries (dates / times may be wrong; section d tests that), the first half is only 3 years (about 90 events).

    python research/china_release_aud.py

Result: (not yet run; the orchestrator pastes the verdict here).
"""
import json
import math
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", RuntimeWarning)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

CAL = ROOT / "marketdata" / "china_calendar_nbs.csv"
DATA = ROOT / "marketdata" / "histdata"
OUTF = ROOT / "research" / "china_release_aud.out.txt"
TRIALS = ROOT / "docs" / "trials.jsonl"
TRIAL_ID = "china_release_aud:run2"

END = pd.Timestamp("2025-09-30 23:59:00")
SPLIT = pd.Timestamp("2018-01-01")
HALVES = (("2015-2017", pd.Timestamp("2015-01-01"), pd.Timestamp("2017-12-31")),
          ("2018-2025.09", pd.Timestamp("2018-01-01"), pd.Timestamp("2025-09-30")))
PAIRS = (("AUDUSD", "AUDUSD_M1.csv.gz", 1.1, 2.2), ("AUDCAD", "AUDCAD_M1.csv.gz", 2.0, 4.0))
HOLD = 60
PRE = 10
MARGIN = 80
OUT = []


def p(s=""):
    print(s)
    OUT.append(str(s))


def f(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "nan"
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def boot(x, n=2000, seed=1):
    """90 % bootstrap interval of the mean of the valid values of x."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(np.percentile(m, 5)), float(np.percentile(m, 95))


def tstat(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def sharpe(day_r, start, end):
    """day_r: Series indexed by date (event-day net R sums). All weekdays start..end, zeros elsewhere."""
    idx = pd.bdate_range(start, end)
    s = day_r.groupby(level=0).sum().reindex(idx).fillna(0.0) if len(day_r) else pd.Series(0.0, index=idx)
    sd = s.std(ddof=1)
    return float(s.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan")


# ---------------------------------------------------------------- calendar
def load_calendar():
    raw = pd.read_csv(CAL, dtype=str, keep_default_na=False)
    p(f"calendar rows read: {len(raw)}")
    hhmm = r"^\d{1,2}:\d{2}$"
    bad = ~(raw.time_utc.str.strip().str.match(hhmm) & raw.time_bjt.str.strip().str.match(hhmm))
    p(f"rows dropped (time missing or not HH:MM): {int(bad.sum())}")
    if bad.any():
        for _, r in raw[bad].iterrows():
            p(f"   dropped: {r.date} {r.series} bjt='{r.time_bjt}' utc='{r.time_utc}' note='{r.note}'")
    c = raw[~bad].copy()
    c["flagged"] = c.note.str.strip() != ""
    utc = pd.to_datetime(c.date.str.strip() + " " + c.time_utc.str.strip().str.zfill(5))
    bj = pd.to_datetime("2000-01-01 " + c.time_bjt.str.strip().str.zfill(5))
    ub = pd.to_datetime("2000-01-01 " + c.time_utc.str.strip().str.zfill(5))
    mism = (((bj - ub).dt.total_seconds() / 60 - 480) % 1440 != 0)
    p(f"rows whose BJT time is not UTC + 8 h: {int(mism.sum())}")
    c["utc"] = utc
    c["server"] = (utc.dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
                   + pd.Timedelta(hours=7))
    n0 = len(c)
    c = c[c.server.dt.dayofweek < 5]
    p(f"rows dropped (weekend on the server clock): {n0 - len(c)}")
    n0 = len(c)
    c = c[c.server <= END]
    p(f"rows dropped (after 2025-09-30): {n0 - len(c)}")
    c["year"] = c.server.dt.year
    p(f"rows kept: {len(c)}; flagged rows kept: {int(c.flagged.sum())}")
    for _, r in c[c.flagged].iterrows():
        p(f"   flagged: {r.date} {r.series} {r.time_bjt} BJT  note='{r.note}'")
    return c


def merge_events(c):
    rows = []
    for ts, g in c.groupby("server"):
        rows.append((ts, tuple(sorted(set(g.series))), bool(g.flagged.any()), g.utc.iloc[0]))
    ev = pd.DataFrame(rows, columns=["ts", "series", "flagged", "utc"])
    ev["date"] = ev.ts.dt.normalize()
    ev["half"] = (ev.date >= SPLIT).astype(int)
    return ev


# ---------------------------------------------------------------- prices
def load_prices(fn):
    df = pd.read_csv(DATA / fn, usecols=["time", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("time"), unit="s")
    df = holdout.drop(df)
    df = df[(df.index <= END) & (df.index >= pd.Timestamp("2014-12-01"))]
    mins = df.index.values.astype("datetime64[m]").astype("int64")
    t0 = int(mins.min())
    n = int(mins.max()) - t0 + 1
    arr = {}
    for k in ("open", "high", "low", "close"):
        a = np.full(n, np.nan)
        a[mins - t0] = df[k].to_numpy()
        arr[k] = a
    return arr, t0, n, df.index.min(), df.index.max()


def win(a, idx, lo, hi):
    return a[np.asarray(idx)[:, None] + np.arange(lo, hi + 1)[None, :]]


# ---------------------------------------------------------------- the rule
def sim(O, H, L, C, i):
    """Return None (no data), 'zero' (R = 0) or (g_bp array, r_bp array, prerange_bp)."""
    ph, pl = H[i - PRE:i], L[i - PRE:i]
    ok = ~(np.isnan(ph) | np.isnan(pl))
    if ok.sum() < 8:
        return None
    hi, lo = float(ph[ok].max()), float(pl[ok].min())
    R = hi - lo
    if R <= 0:
        return "zero"
    o, h, l, c = (x[i:i + HOLD].tolist() for x in (O, H, L, C))
    xc = None
    for v in reversed(c):
        if v == v:
            xc = v
            break
    if xc is None:
        return None
    trades = []
    lng = sht = None
    ldone = sdone = False
    for k in range(HOLD):
        oo, hh, ll = o[k], h[k], l[k]
        if oo != oo or hh != hh or ll != ll:
            continue
        if lng is not None and ll <= lo:
            ex = oo if oo < lo else lo
            trades.append((ex - lng, lng))
            lng = None
        if sht is not None and hh >= hi:
            ex = oo if oo > hi else hi
            trades.append((sht - ex, sht))
            sht = None
        l_ok = (not ldone) and hh >= hi
        s_ok = (not sdone) and ll <= lo
        if l_ok and s_ok and not ldone and not sdone:
            en = oo if oo > hi else hi
            ex = oo if oo < lo else lo
            trades.append((ex - en, en))
            ldone = True
            continue
        if l_ok:
            en = oo if oo > hi else hi
            ldone = True
            if ll <= lo:
                ex = oo if oo < lo else lo
                trades.append((ex - en, en))
            else:
                lng = en
        if s_ok:
            en = oo if oo < lo else lo
            sdone = True
            if hh >= hi:
                ex = oo if oo > hi else hi
                trades.append((en - ex, en))
            else:
                sht = en
    if lng is not None:
        trades.append((xc - lng, lng))
    if sht is not None:
        trades.append((sht - xc, sht))
    g = np.array([t[0] / t[1] * 1e4 for t in trades])
    r = np.array([R / t[1] * 1e4 for t in trades])
    return g, r, R / ((hi + lo) / 2) * 1e4


def trade_stats(g, r, cost):
    if len(g) == 0:
        return dict(n=0, win=float("nan"), gR=float("nan"), nR=float("nan"), nbp=float("nan"), t=float("nan"))
    nb = g - cost
    nr = nb / r
    return dict(n=len(g), win=float((nr > 0).mean()), gR=float((g / r).mean()), nR=float(nr.mean()),
                nbp=float(nb.mean()), t=tstat(nr))


class Sim:
    pass


def run_sim(arr, ev_idx, ctl_idx):
    O, H, L, C = arr["open"], arr["high"], arr["low"], arr["close"]
    s = Sim()
    E = len(ev_idx)
    s.ok = np.zeros(E, bool)
    s.zero = 0
    s.nodata = 0
    s.czero = 0
    s.cnodata = 0
    s.Eg, s.Er, s.Rbp = [None] * E, [None] * E, np.full(E, np.nan)
    s.Cg, s.Cr = [[] for _ in range(E)], [[] for _ in range(E)]
    for e in range(E):
        res = sim(O, H, L, C, int(ev_idx[e]))
        if res is None:
            s.nodata += 1
        elif isinstance(res, str):
            s.zero += 1
        else:
            s.ok[e] = True
            s.Eg[e], s.Er[e], s.Rbp[e] = res
        for j in ctl_idx[e]:
            if j < 0:
                continue
            rc = sim(O, H, L, C, int(j))
            if rc is None:
                s.cnodata += 1
            elif isinstance(rc, str):
                s.czero += 1
            else:
                s.Cg[e].append(rc[0])
                s.Cr[e].append(rc[1])
    return s


def eval_set(s, ev, sel, cost):
    """Per half and all: dict with event / control trade stats, diff, Sharpe."""
    out = {}
    sel = np.asarray(sel) & s.ok
    parts = [(HALVES[0][0], sel & (ev.half.to_numpy() == 0), HALVES[0][1], HALVES[0][2]),
             (HALVES[1][0], sel & (ev.half.to_numpy() == 1), HALVES[1][1], HALVES[1][2]),
             ("all", sel, HALVES[0][1], HALVES[1][2])]
    dates = ev.date.to_numpy()
    for name, m, st, en in parts:
        es = np.where(m)[0]
        eg = np.concatenate([s.Eg[e] for e in es]) if len(es) else np.array([])
        er = np.concatenate([s.Er[e] for e in es]) if len(es) else np.array([])
        cg_l = [g for e in es for g in s.Cg[e]]
        cr_l = [r for e in es for r in s.Cr[e]]
        cg = np.concatenate(cg_l) if cg_l else np.array([])
        cr = np.concatenate(cr_l) if cr_l else np.array([])
        evR = np.array([((s.Eg[e] - cost) / s.Er[e]).sum() for e in es])
        cm = np.array([np.mean([((g - cost) / r).sum() for g, r in zip(s.Cg[e], s.Cr[e])]) if s.Cg[e] else np.nan
                       for e in es])
        diff = evR - cm
        lo, hi = boot(diff)
        dr = pd.Series(evR, index=pd.DatetimeIndex(dates[es])) if len(es) else pd.Series(dtype=float)
        out[name] = dict(ne=len(es), ev=trade_stats(eg, er, cost), nc=len(cg_l), ct=trade_stats(cg, cr, cost),
                         diff=float(np.nanmean(diff)) if len(es) and (~np.isnan(diff)).any() else float("nan"),
                         lo=lo, hi=hi, sh=sharpe(dr, st, en))
    return out


def print_eval(res, indent="  "):
    p(indent + f"{'period':<13}{'events':>7}{'trades':>7}{'win%':>6}{'grossR':>8}{'netR':>8}{'net bp':>8}{'t':>7} |"
      f"{'ctl trd':>8}{'win%':>6}{'grossR':>8}{'netR':>8}{'net bp':>8}{'t':>7} |{'ev-ctl R/ev':>12}{'90% CI':>18}{'Sharpe':>8}")
    for k, v in res.items():
        e, c = v["ev"], v["ct"]
        p(indent + f"{k:<13}{v['ne']:>7}{e['n']:>7}{f(e['win'] * 100, 1):>6}{f(e['gR'], 3, True):>8}{f(e['nR'], 3, True):>8}"
          f"{f(e['nbp'], 2, True):>8}{f(e['t'], 2, True):>7} |{c['n']:>8}{f(c['win'] * 100, 1):>6}{f(c['gR'], 3, True):>8}"
          f"{f(c['nR'], 3, True):>8}{f(c['nbp'], 2, True):>8}{f(c['t'], 2, True):>7} |{f(v['diff'], 3, True):>12}"
          f"{'[' + f(v['lo'], 3, True) + ',' + f(v['hi'], 3, True) + ']':>18}{f(v['sh'], 2, True):>8}")


# ---------------------------------------------------------------- one instrument
def run_instrument(name, fn, cost, cost_s, ev_all):
    p("\n" + "=" * 118)
    p(f"{name}  ({fn})   cost {cost} bp base, {cost_s} bp stress")
    p("=" * 118)
    arr, t0, n, first, last = load_prices(fn)
    O, H, L, C = arr["open"], arr["high"], arr["low"], arr["close"]
    p(f"prices (after holdout.drop and the 2025-09-30 cut): {first} .. {last}, grid {n} minutes, "
      f"{int((~np.isnan(C)).sum())} bars present")

    ev = ev_all.copy()
    ev["idx"] = (ev.ts.values.astype("datetime64[m]").astype("int64") - t0)
    inb = (ev.idx >= MARGIN) & (ev.idx < n - MARGIN)
    p(f"events outside the price range dropped: {int((~inb).sum())}")
    ev = ev[inb].reset_index(drop=True)
    p("sample conversions (UTC release -> server clock = NY + 7 h):")
    step = max(1, len(ev) // 5)
    for _, r in ev.iloc[::step].head(5).iterrows():
        p(f"   {r.utc}  UTC  ->  {r.ts}  server   {'+'.join(r.series)}   bar close at that minute: "
          f"{C[int(r.idx)]:.5f}")
    ev_dates = set(ev_all.date)
    # controls
    ctl = []
    for _, r in ev.iterrows():
        d0 = r.date.replace(day=1)
        days = pd.bdate_range(d0, d0 + pd.offsets.MonthEnd(0))
        days = [d for d in days if d not in ev_dates and d <= pd.Timestamp("2025-09-30")]
        mod = r.ts.hour * 60 + r.ts.minute
        ix = np.array([int(d.to_datetime64().astype("datetime64[D]").astype("int64")) * 1440 + mod - t0 for d in days],
                      dtype=np.int64)
        ix = ix[(ix >= MARGIN) & (ix < n - MARGIN)]
        ctl.append(ix)
    K = max(len(x) for x in ctl)
    cm = np.full((len(ev), K), -1, dtype=np.int64)
    for e, x in enumerate(ctl):
        cm[e, :len(x)] = x
    p(f"events {len(ev)}; control days per event: mean {np.mean([len(x) for x in ctl]):.1f}, min {min(len(x) for x in ctl)}")
    eidx = ev.idx.to_numpy()
    half = ev.half.to_numpy()
    valid = cm >= 0

    def paired(fn_):
        a = fn_(eidx)
        flat = fn_(cm[valid])
        b = np.full((cm.shape[0], K) + flat.shape[1:], np.nan)
        b[valid] = flat
        return a, b

    # ---- b) minute profile
    p("\n-- Step 5b: minute profile, mean |1-min close-to-close return| in bp --")
    ms = np.arange(-30, 31)

    def f_prof(ix):
        w = win(C, ix, -31, 30)
        return np.abs(w[:, 1:] / w[:, :-1] - 1) * 1e4

    pe, pc = paired(f_prof)
    ev_m = np.nanmean(pe, axis=0)
    ct_m = np.nanmean(pc.reshape(-1, 61), axis=0)
    ev_h, ct_h = [], []
    for h in (0, 1):
        ev_h.append(np.nanmean(pe[half == h], axis=0))
        ct_h.append(np.nanmean(pc[half == h].reshape(-1, 61), axis=0))
    p(f"  {'min':>4}{'event':>9}{'control':>9}{'ratio':>7}{'ratio h1':>10}{'ratio h2':>10}")
    for j, m in enumerate(ms):
        p(f"  {m:>+4}{ev_m[j]:>9.3f}{ct_m[j]:>9.3f}{ev_m[j] / ct_m[j]:>7.2f}{ev_h[0][j] / ct_h[0][j]:>10.2f}"
          f"{ev_h[1][j] / ct_h[1][j]:>10.2f}")
    peaks = {"pooled": int(ms[np.argmax(ev_m)]), HALVES[0][0]: int(ms[np.argmax(ev_h[0])]),
             HALVES[1][0]: int(ms[np.argmax(ev_h[1])])}
    p(f"  peak minute of the event profile: {peaks}")
    bad = [k for k, v in peaks.items() if not (0 <= v <= 2)]
    if bad:
        p(f"  *** WARNING *** the spike is NOT at minute 0..+2 for {bad}: the clock conversion (or the calendar) is "
          f"probably wrong, step 6 means nothing here ***")
    else:
        p("  spike sits at minute 0..+2: clock conversion consistent with the data.")

    # ---- c) Table A1
    p("\n-- Step 5c: Table A1 replication, extra mean |close(t+10)-close(t-11)|/close(t-11) in %, event minus control --")
    p("   (paper 2008-16: GDP 0.06, activity 0.04, CPI 0.04, trade 0.03; merged events count under each of their series)")

    def f_a1(ix):
        return np.abs(C[ix + 10] - C[ix - 11]) / C[ix - 11] * 100

    ae, ac = paired(f_a1)
    extra = ae - np.nanmean(ac, axis=1)
    sers = [("pooled", np.ones(len(ev), bool))] + [(s_, np.array([s_ in x for x in ev.series])) for s_ in
                                                     ("GDP", "ACTIVITY", "CPI")]
    p(f"  {'series':<10}{'period':<14}{'events':>7}{'event %':>9}{'control %':>10}{'extra %':>9}{'90% CI':>20}")
    for sn, sm in sers:
        for pn, pm in (("2015-2017", half == 0), ("2018-2025.09", half == 1)):
            m = sm & pm & ~np.isnan(extra)
            if m.sum() == 0:
                p(f"  {sn:<10}{pn:<14}{0:>7}")
                continue
            lo, hi = boot(extra[m])
            p(f"  {sn:<10}{pn:<14}{int(m.sum()):>7}{np.nanmean(ae[m]):>9.4f}{np.nanmean(np.nanmean(ac, axis=1)[m]):>10.4f}"
              f"{extra[m].mean():>9.4f}{'[' + f(lo, 4, True) + ',' + f(hi, 4, True) + ']':>20}")

    # ---- d) calendar check
    p("\n-- Step 5d: calendar check: |close(t+5)/close(t-1)-1| per event vs the 75th pct of its control days --")

    def f_d(ix):
        return np.abs(C[ix + 5] / C[ix - 1] - 1) * 1e4

    de, dc = paired(f_d)
    p75 = np.nanpercentile(dc, 75, axis=1)
    okm = ~(np.isnan(de) | np.isnan(p75))
    exc = okm & (de > p75)
    p(f"  events with data {int(okm.sum())}; exceed the control 75th percentile: {int(exc.sum())} "
      f"({exc.sum() / max(1, okm.sum()):.0%}; 25% expected for a dead calendar, higher = real events)")
    for h, (hn, _, _) in enumerate(HALVES):
        mh = okm & (half == h)
        p(f"    {hn}: {int((exc & (half == h)).sum())} of {int(mh.sum())} ({(exc & (half == h)).sum() / max(1, mh.sum()):.0%})")
    p("  events that do NOT exceed it (date, server time, series, move bp, control p75 bp, flagged):")
    for e in np.where(okm & ~exc)[0]:
        r = ev.iloc[e]
        p(f"    {r.date.date()} {r.ts.strftime('%H:%M')} {'+'.join(r.series):<14}{de[e]:>7.2f}{p75[e]:>8.2f}"
          f"{'  flagged' if r.flagged else ''}")
    for e in np.where(~okm)[0]:
        r = ev.iloc[e]
        p(f"    {r.date.date()} {r.ts.strftime('%H:%M')} {'+'.join(r.series):<14}  no price data")
    sus = ev[ev.date == pd.Timestamp("2018-01-18")]
    for e in sus.index:
        r = ev.iloc[e]
        st = "no data" if not okm[e] else ("exceeds" if exc[e] else "does NOT exceed")
        p(f"  note 2018-01-18 (printed 15:00 BJT, suspect): {r.ts.strftime('%H:%M')} server {'+'.join(r.series)}: {st}"
          f" (move {f(float(de[e]))} bp vs p75 {f(float(p75[e]))})")

    # ---- continuation
    p("\n-- Continuation diagnostic: corr( ret close t-2 -> t+2 , ret close t+2 -> t+60 ) --")

    def f_cont(ix):
        return np.stack([C[ix + 2] / C[ix - 2] - 1, C[ix + 60] / C[ix + 2] - 1], axis=1)

    ce, cc = paired(f_cont)

    def corr(a):
        a = a.reshape(-1, 2)
        a = a[~np.isnan(a).any(axis=1)]
        if len(a) < 5:
            return float("nan"), len(a)
        return float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]), len(a)

    for nm, m in (("2015-2017", half == 0), ("2018-2025.09", half == 1), ("all", half >= 0)):
        (rc_e, ne_), (rc_c, nc_) = corr(ce[m]), corr(cc[m])
        p(f"  {nm:<13} event {f(rc_e, 3, True)} (n {ne_})   control {f(rc_c, 3, True)} (n {nc_})")

    # ---- rule
    p("\n-- Step 6-7: the breakout rule --")
    s = run_sim(arr, eidx, cm)
    p(f"  events skipped: R = 0: {s.zero}, no data: {s.nodata}; control days skipped: R = 0: {s.czero}, no data: {s.cnodata}")
    allm = np.ones(len(ev), bool)
    flagm = ~ev.flagged.to_numpy()

    p(f"\n  MAIN: all events, base cost {cost} bp")
    main = eval_set(s, ev, allm, cost)
    print_eval(main)
    p(f"\n  Robustness: flagged rows dropped ({int(ev.flagged.sum())} flagged events removed), base cost")
    print_eval(eval_set(s, ev, flagm, cost))
    p(f"\n  Robustness: stress cost {cost_s} bp, all events")
    stress = eval_set(s, ev, allm, cost_s)
    print_eval(stress)

    p("\n  Diagnostics only (not selection): per series (merged events count under each series), base cost")
    for sn in ("GDP", "ACTIVITY", "CPI"):
        p(f"   [{sn}]")
        print_eval(eval_set(s, ev, np.array([sn in x for x in ev.series]), cost), indent="    ")
    p("  Diagnostics only: pre-range width terciles (cutoffs from all events), base cost")
    rb = s.Rbp
    q1, q2 = np.nanpercentile(rb, [100 / 3, 200 / 3])
    p(f"   pre-range width bp: tercile cutoffs {q1:.2f} / {q2:.2f}")
    for tn, tm in (("narrow", rb <= q1), ("middle", (rb > q1) & (rb <= q2)), ("wide", rb > q2)):
        p(f"   [{tn}]")
        print_eval(eval_set(s, ev, tm, cost), indent="    ")

    # ---- the three tests
    tests = {}
    for hn, _, _ in HALVES:
        v = main[hn]
        tests[hn] = dict(nR=v["ev"]["nR"] > 0, diff=v["diff"] > 0, sh=v["sh"] >= 0.5)
    p(f"\n  {name} pass tests at base cost:")
    for hn, t in tests.items():
        v = main[hn]
        p(f"    {hn}: net mean R/trade {f(v['ev']['nR'], 3, True)} {'ok' if t['nR'] else 'FAIL'} | "
          f"event minus control {f(v['diff'], 3, True)} {'ok' if t['diff'] else 'FAIL'} | "
          f"net Sharpe {f(v['sh'], 2, True)} {'ok' if t['sh'] else 'FAIL'}")
    return tests


def failures(tests):
    names = {"nR": "net R/trade > 0", "diff": "event minus control > 0", "sh": "net Sharpe >= 0.5"}
    return [f"{hn}: {names[k]}" for hn, t in tests.items() for k, v in t.items() if not v]


def main():
    p("china_release_aud: Chinese macro releases and AUD breakouts (run 2)")
    p(f"run at {datetime.now().isoformat(timespec='seconds')}")
    p("PASS RULE: AUDUSD at the base cost (1.1 bp): net mean R per trade > 0 in BOTH halves (2015-2017, 2018-2025.09), "
      "event minus control > 0 in BOTH halves, net Sharpe >= 0.5 in BOTH halves.  Otherwise FAIL.  AUDCAD (2.0 bp) is a "
      "check with the same three tests.\n")
    p("-- Step 5a: calendar --")
    cal = load_calendar()
    p("events (rows) per series per year:")
    p(pd.crosstab(cal.series, cal.year, margins=True).to_string())
    ev_all = merge_events(cal)
    p(f"merged events (same date and UTC minute): {len(ev_all)}; rows merged away: {len(cal) - len(ev_all)}; "
      f"multi-series events: {int((ev_all.series.apply(len) > 1).sum())}; flagged events: {int(ev_all.flagged.sum())}")
    p(f"events per half: {int((ev_all.half == 0).sum())} / {int((ev_all.half == 1).sum())}")
    res = {}
    for name, fn, c, cs in PAIRS:
        res[name] = run_instrument(name, fn, c, cs, ev_all)

    p("\n" + "=" * 118)
    fu, fc = failures(res["AUDUSD"]), failures(res["AUDCAD"])
    p(f"AUDCAD check: {'all three tests pass in both halves' if not fc else 'fails: ' + '; '.join(fc)}")
    if not fu:
        verdict = "PASS"
        vtxt = "pass rule met"
    else:
        verdict = "FAIL"
        vtxt = "fails: " + "; ".join(fu)
    p(f"VERDICT: {verdict} (AUDUSD, base cost) -- {vtxt}")

    line = json.dumps({"id": TRIAL_ID, "when": datetime.now().isoformat(timespec="seconds"),
                       "verdict": f"{verdict}: {vtxt}", "count": 2})
    txt = TRIALS.read_text() if TRIALS.exists() else ""
    have = False
    for ln in txt.splitlines():
        try:
            if json.loads(ln).get("id") == TRIAL_ID:
                have = True
        except Exception:
            pass
    if have:
        p(f"\ntrials line for {TRIAL_ID} already present: not appended.")
    else:
        with open(TRIALS, "a") as fh:
            if txt and not txt.endswith("\n"):
                fh.write("\n")
            fh.write(line + "\n")
        p(f"\ntrials line appended: {line}")
    OUTF.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"report written to {OUTF}")


if __name__ == "__main__":
    main()
