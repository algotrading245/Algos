"""The AurumHydra goal model with margin and a broker stop-out, hour by hour.

The tester (FTMO data, 1:500, deposit 10000) ended 7 / 10 / 9 of 21 single-month goal runs (3x / 4x / 5x,
2024.01-2025.09) in a stop-out (margin level below 50%, deal comment "so 4x.xx%", median multiple 0.5x), while
research/hydra_t5b_months_model.py has no margin and rides the same hours out. This script adds margin to the model.

  Part 1  margin per notional, measured from the tester's own stop-outs: for each run with a "so " deal the open
          positions just before it (net signed lots per symbol) are turned into USD notional (gold, FX, other), and
          margin = equity / (level / 100) is fitted by non-negative least squares. Rates are used as fitted.
  Part 2  the hourly model: grid and gold hold at size 1 from tools/backtest_hydra.py (logic copied), with the
          hour's worst price from the M1 high/low (server hours 23 and 0 are not in the hourly file, lesson 9).
          A round steps day by day with the goal size of one_round(); inside a day equity = day-open equity *
          (1 + size * (hold + grid pnl so far at the hour's worst)); the other legs are booked at the day's close.
          Margin = day-open equity * size * (|hold| * a_gold + |grid| * a_fx); equity / margin < 0.5 ends the
          round at 0.5 * margin (at most the equity at the start of that hour). The hold entry and every new grid
          level are clipped to 50% of the free margin. MARGIN False gives the daily totals of one_round().
          EA-like mode (ea_day): lots kept between days, hold 25% band, grid cycle base from BALANCE (equity less the
          floating pnl of hold and grid, tracked) times GoalSize of the LIVE equity at the cycle's first level, hold
          target from the day's first hour, panic exit at |z| >= 6 compared with the margin stop by the share of the
          bar's adverse path, other legs booked at the close on day-open size. EA+OM adds OTHER_MARGIN (median ratio
          of non-AUDCAD FX + other margin to equity * size at the tester's stop-outs) as a constant share of
          day-open equity * size: a sensitivity, not a fit.
  Part 3  (a) tester against model per month and goal, (b) month-start rounds 2010-06 on, (c) EA-like daily minimum
          margin level and the fixed size at which a month first ends in a stop-out (percentiles across months).
Known limitation: server hours 23 and 0 have no data (lesson 9), nothing is modelled in them.

Units. The grid's pnl at size 1 is 0.035 * wt[|q|] * sign * (log price move) / (risk * unit), so the notional of
the grid as a fraction of equity is 0.035 * wt[|q|] / (risk * unit) (unit = one step in log terms, risk = steps
lost at the stop-out = 10 for 4 levels). Its base is AUD, a USD notional of AUD, which is what the AUD fit uses.
The hold's notional as a fraction of equity is pos = sig * 0.107 / vol, at most 3.

    python research/hydra_goal_margin_model.py
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.stats import norm

import hydra_t5b_months_model as m
from hydra_goal_202410_compare import deal_rows
from hydra_j6_compare import parse_report

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

DATA = ROOT / "marketdata" / "histdata"
MARGIN = True                      # False: the hourly code without margin (daily totals of one_round())
TOL = 0.997                        # lesson 18: goal reached counts at 0.3% below
STOP_LEVEL = 0.5                   # broker stop-out at margin level 50%
CLIP = 0.5                         # one order may use at most half of the free margin (InpMarginPct 50)
GRID_RISK, HOLD_TARGET, HOLD_SWAP, HOLD_COST = 0.035, 0.107, 0.068, 0.8
START_DAY = "2010-06-01"           # the legs file starts here
HOLD_EPOCH = int((holdout.START - pd.Timestamp("1970-01-01")).total_seconds())
FX_CCY = {"USD", "EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY"}
PRESET = (23, 50.0, 0.0156)
MONTHS = {}                        # Period -> (first day index, one past the last), filled by build_bars()
HOLD_BAND = 0.25                   # InpHoldBand: no trade when |target - held| <= band * max(target, held)
GRID_LEVELS, GRID_RISK_STEPS = 4, 10.0   # 4 levels, mult 1: steps lost at the grid's stop-out = 4+3+2+1
SWAP_LONG, SWAP_SHORT = 0.42, -0.95      # AUDCAD swap per night, 1e-4 of notional (Thursday counts 3)
HC, GC = HOLD_COST * 1e-4 / 2, 1.8e-4 / 2   # cost per unit of traded notional, hold and grid
DAYS_IDX = []                      # the model's days (Timestamps), filled by build_bars()
GRID_PANIC = 1.0                   # InpGridPanic: the grid is closed inside the hour at levels + 1 + this many steps
LAST = [-1]                      # day index of the last stop-out seen by run_round (-1: none)


def num(s):
    return parse_report.num(s) or 0.0


# ---------------------------------------------------------------- tester runs

def scan_runs():
    """goal -> list of dicts (month 'YYYYMM', tester multiple, deal rows, index of the first stop-out row or None)."""
    out = {}
    for goal in (3, 4, 5):
        out[goal] = []
        for res_path in sorted(ROOT.glob(f"backtests/2026-10-18_*_AurumHydra_t{goal}b_20????/result.json")):
            folder = res_path.parent
            res = json.loads(res_path.read_text())
            rows = deal_rows(folder.relative_to(ROOT))
            k = next((i for i, x in enumerate(rows) if x[12].startswith("so ")), None)
            mult = res["curve"][-1][1] / res["deposit"] if res["curve"] else 1.0
            out[goal].append(dict(month=folder.name[-6:], folder=folder.name, mult=mult, rows=rows, so=k,
                                  deposit=float(res["deposit"]), goal=goal))
    return out


# ---------------------------------------------------------------- part 1

_M1 = {}


def m1_close(pair):
    if pair not in _M1:
        d = pd.read_csv(DATA / f"{pair}_M1.csv.gz", usecols=["time", "close"],
                        dtype={"time": np.int64, "close": np.float64})
        d = d[(d.time >= 1672531200) & (d.time < HOLD_EPOCH)].sort_values("time")
        _M1[pair] = (d.time.to_numpy(), d.close.to_numpy())
    return _M1[pair]


def hist_price(pair, t):
    ts, cs = m1_close(pair)
    return float(cs[max(int(np.searchsorted(ts, t, side="right")) - 1, 0)])


def usd_per_unit(ccy, t):
    """USD value of one unit of ccy at server time t (epoch seconds), from the histdata M1 closes."""
    if ccy == "USD":
        return 1.0
    if (DATA / f"{ccy}USD_M1.csv.gz").exists():
        return hist_price(ccy + "USD", t)
    return 1.0 / hist_price("USD" + ccy, t)


def kind(sym):
    s = sym.upper()
    if s.startswith("XAU"):
        return "gold"
    if len(s) == 6 and s[:3] in FX_CCY and s[3:] in FX_CCY:
        return "fx"
    return "other"


def open_lots(rows):
    """Net signed lots per symbol from the deals (buy +, sell -), balance rows left out."""
    net = defaultdict(float)
    for x in rows:
        if x[3] in ("buy", "sell") and x[2]:
            net[x[2]] += (1.0 if x[3] == "buy" else -1.0) * num(x[5])
    return {s: v for s, v in net.items() if abs(v) > 1e-6}


def stopout_obs(run):
    """One stop-out: time, level, equity, USD notional by kind. Contracts: gold 100 oz, FX 100000 base units,
    other symbols lots * price (contract size unknown, own bucket). Cross bases use the histdata M1 close."""
    rows, k = run["rows"], run["so"]
    t = rows[k][0]
    level = float(re.search(r"so ([\d.]+)%", rows[k][12]).group(1))
    at_t = [x for x in rows if x[0] == t]
    old_equity = num([x for x in at_t if x[12].startswith("so ")][-1][11])    # balance after the last "so" close
    equity = num(at_t[-1][11])          # balance after every close at t ("end of test" closes the rest at once)
    px = {x[2]: num(x[6]) for x in at_t if x[2]}
    before = [x for x in rows if x[0] < t]
    epoch = int(pd.Timestamp(t.replace(".", "-", 2)).value // 10 ** 9)
    note = {"gold": 0.0, "fx": 0.0, "other": 0.0, "fxaud": 0.0}
    for sym, lots in open_lots(before).items():
        price = px.get(sym) or next((num(x[6]) for x in reversed(before) if x[2] == sym), 0.0)
        kd = kind(sym)
        if kd == "gold":
            note[kd] += abs(lots) * 100.0 * price
        elif kd == "fx":
            base, quote = sym[:3].upper(), sym[3:6].upper()
            unit = price if quote == "USD" and price else usd_per_unit(base, epoch)
            note[kd] += abs(lots) * 100000.0 * unit
            if sym.upper() == "AUDCAD":
                note["fxaud"] += abs(lots) * 100000.0 * unit
        else:
            note[kd] += abs(lots) * price
    bal_before = next((num(x[11]) for x in reversed(rows) if x[0][:10] < t[:10]), run["deposit"])
    return dict(run=run["folder"][run["folder"].find("_t") + 1:], time=t, level=level, equity=equity,
                old_equity=old_equity, bal_before=bal_before, month=run["month"], goal=run["goal"], **note)


def part1(runs):
    print("=" * 100)
    print("PART 1  margin per notional from the tester's stop-outs")
    obs = [stopout_obs(r) for goal in runs for r in runs[goal] if r["so"] is not None]
    if not obs:
        print("no stop-outs found, using 1:500 for both")
        return 1 / 500, 1 / 500, 0.0
    print("equity = balance of the last deal row at the stop-out second (all closes, 'end of test' included); "
          "notionals = every position open just before that second")
    use = [c for c in ("gold", "fx", "other") if any(o[c] > 0 for o in obs)]
    A = np.array([[o[c] / o["equity"] for c in use] for o in obs])
    b = np.array([100.0 / o["level"] for o in obs])             # margin / equity at the stop-out
    coef, _ = nnls(A, b)
    rate = dict(zip(use, coef))
    fit = A @ coef
    print(f"{len(obs)} stop-outs; columns {use}; fit of margin/equity, equity-weighted rows (each row in units of "
          f"its own equity)")
    print("run              time                 level  equity(old) equity(new)   gold $      fx $  of it AUDCAD   "
          "other $   fit margin  implied   fit/impl  level at 1:500")
    for o, f, imp in zip(obs, fit, b):
        notional = o["gold"] + o["fx"] + o["other"]
        lvl500 = 100.0 * o["equity"] / (notional / 500.0) if notional else float("nan")
        print(f"{o['run']:16s} {o['time']}  {o['level']:5.1f} {o['old_equity']:10,.0f} {o['equity']:10,.0f} "
              f"{o['gold']:10,.0f} {o['fx']:10,.0f} {o['fxaud']:10,.0f} {o['other']:10,.0f}  "
              f"{f * o['equity']:10,.0f} {imp * o['equity']:9,.0f}   {f / imp:6.2f}   {lvl500:8.1f}%")
    fx_all, fx_aud = sum(o["fx"] for o in obs), sum(o["fxaud"] for o in obs)
    print(f"FX notional at the stop-outs that is NOT AUDCAD: {100 * (1 - fx_aud / fx_all) if fx_all else 0:.0f}% of the "
          f"FX total; per stop-out median {np.median([100 * (1 - o['fxaud'] / o['fx']) if o['fx'] else 0 for o in obs]):.0f}%")
    rel = np.abs(fit / b - 1.0)
    for c, v in rate.items():
        print(f"fitted {c:5s}: margin = {v:.5f} of USD notional  ->  1:{1 / v:,.0f} leverage equivalent"
              if v > 0 else f"fitted {c:5s}: 0 (nnls dropped it)")
    print(f"pure 1:500 would be 0.00200 of notional for every kind (median level at the stop-outs: "
          f"{np.nanmedian([100.0 * o['equity'] / ((o['gold'] + o['fx'] + o['other']) / 500.0) for o in obs]):.0f}% "
          f"against the tester's {np.median([o['level'] for o in obs]):.0f}%)")
    print(f"fit quality: median |fit/implied - 1| {100 * np.median(rel):.0f}%, max {100 * rel.max():.0f}%"
          + ("  -> POOR (median error above 25%), the rates below are used as fitted anyway" if np.median(rel) > 0.25
             else ""))
    if "other" in rate and rate["other"] > 0:
        print("note: 'other' symbols (contract size unknown) carry margin in the fit; the model has no such leg and "
              "ignores that rate")
    a_gold, a_fx = rate.get("gold", 0.0), rate.get("fx", 0.0)
    if a_gold <= 0 or a_fx <= 0:
        print("WARNING: a fitted rate is 0, the model will carry no margin for that leg")
    print(f"used by the model: a_gold {a_gold:.5f} (1:{1 / a_gold if a_gold else float('inf'):,.0f}), "
          f"a_fx {a_fx:.5f} (1:{1 / a_fx if a_fx else float('inf'):,.0f})")
    # other legs' margin as a share of (day-open equity * size): median over the stop-outs of
    # (non-AUDCAD FX notional * a_fx + other notional * rate) / (tester balance before the stop-out day * size then)
    a_oth = rate.get("other", 0.0) or a_fx
    print("other-legs margin sensitivity: margin of non-AUDCAD FX and other notional / (balance before the stop-out "
          f"day * GoalSize then); 'other' rate {a_oth:.5f}{'' if rate.get('other', 0.0) else ' (= a_fx, nnls gave 0)'}")
    ratios = []
    for o in obs:
        mt = pd.Timestamp(o["month"][:4] + "-" + o["month"][4:] + "-01")
        stop_day = pd.Timestamp(o["time"][:10].replace(".", "-"))
        left = max(PRESET[0] - int(np.busday_count(mt.date(), stop_day.date())), 1)
        size = goal_size(o["bal_before"] / 10000.0, o["goal"], left, PRESET[1], PRESET[2])
        mg = (o["fx"] - o["fxaud"]) * a_fx + o["other"] * a_oth
        ratios.append(mg / (o["bal_before"] * size))
        print(f"  {o['run']:16s} {o['time'][:10]}  balance before {o['bal_before']:9,.0f}  days left {left:2d}  "
              f"size {size:5.1f}  non-AUDCAD margin {mg:9,.0f}  ratio {ratios[-1]:.3f}")
    om = float(np.median(ratios))
    print(f"OTHER_MARGIN (median of the {len(ratios)} ratios) = {om:.3f} of day-open equity * size")
    return a_gold, a_fx, om


# ---------------------------------------------------------------- part 2: bars

def grid_hourly(p, ma=5, step=1.0, levels=4, cost=1.8, mult=1.0, swap=(0.42, -0.95)):
    """Copy of tools/backtest_hydra.grid on hourly closes p that also returns the position held in every bar.
    Returns (pnl, expo): per bar, in fractions of equity at size 1 (0.035 * result / risk), and the signed
    notional / equity held during the bar (0.035 * sign * wt[|q|] / (risk * unit))."""
    wt = np.concatenate([[0.0], np.cumsum(mult ** np.arange(levels))])
    risk = sum(mult ** (k - 1) * (levels + 1 - k) for k in range(1, levels + 1))
    lp = np.log(p.to_numpy())
    avg = pd.Series(lp).rolling(ma * 22).mean().to_numpy()
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40).std() * np.sqrt(22)).shift(1).to_numpy()
    out = np.zeros(len(lp))
    expo = np.zeros(len(lp))
    q, dead, unit = 0, False, 1.0
    night = np.r_[False, p.index.normalize()[1:] != p.index.normalize()[:-1]] * np.where(p.index.dayofweek == 3, 3, 1)
    for i in range(len(lp)):
        if q:
            out[i] = np.sign(q) * wt[abs(q)] * r[i] / unit
            expo[i] = np.sign(q) * wt[abs(q)] / unit
            if night[i]:
                out[i] += wt[abs(q)] * swap[q < 0] * night[i] * 1e-4 / unit
        if np.isnan(avg[i]) or np.isnan(dv[i]) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (step * dv[i])
        az, side = abs(z), (1 if z > 0 else -1)
        if dead:
            dead = az >= 0.5
            continue
        if q == 0:
            unit = step * dv[i]
        if az >= levels + 1:
            new, dead = 0, True
        else:
            cur = abs(q) if q * side < 0 else 0
            new = -side * max(min(int(az), levels), min(cur, int(np.ceil(az))))
        if new != q:
            out[i] -= abs(np.sign(new) * wt[abs(new)] - np.sign(q) * wt[abs(q)]) * cost * 1e-4 / 2 / unit
            q = new
    k = GRID_RISK / risk
    return out * k, expo * k


def grid_signals(p, ma=5, step=1.0, levels=GRID_LEVELS):
    """What the EA's Grid() sees at every hourly close, independent of the open positions (the target itself
    depends on the levels actually open and is built in ea_day). mode 0 no signal yet, 1 dead (target 0), 2 stop-out
    now (target 0), 3 live. Also |z|, the side of z, the step in log terms (the cycle's unit) and the nights of
    swap charged in the bar (Thursday 3)."""
    lp = np.log(p.to_numpy())
    avg = pd.Series(lp).rolling(ma * 22).mean().to_numpy()
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40).std() * np.sqrt(22)).shift(1).to_numpy()
    n = len(lp)
    mode, azv, sd, unit = np.zeros(n, np.int8), np.zeros(n), np.zeros(n, np.int8), np.zeros(n)
    night = np.r_[False, p.index.normalize()[1:] != p.index.normalize()[:-1]] * np.where(p.index.dayofweek == 3, 3, 1)
    dead = False
    for i in range(n):
        if np.isnan(avg[i]) or np.isnan(dv[i]) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (step * dv[i])
        azv[i], sd[i], unit[i] = abs(z), (1 if z > 0 else -1), step * dv[i]
        if dead:
            dead = azv[i] >= 0.5
            mode[i] = 1
        elif azv[i] >= levels + 1:
            dead, mode[i] = True, 2
        else:
            mode[i] = 3
    return mode, azv, sd, unit, night.astype(np.float64), avg


def hold_pos(gold):
    """Copy of tools/backtest_hydra.hold: the day's position (notional / equity) and the day's fixed costs
    (turnover cost and yearly charge), both indexed by date; the position is decided at yesterday's 22:00 close."""
    D = gold[gold.index.hour == 22]
    D.index = D.index.normalize()
    R = np.log(D).diff()
    vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
    sig = sum(np.sign(D / D.shift(k) - 1) for k in (20, 60, 120, 250)) / 4
    sig = sig.clip(lower=0)
    pos = (sig * HOLD_TARGET / vol).clip(-3, 3).shift(1)
    fixed = -pos.diff().abs() * HOLD_COST * 1e-4 / 2 - pos.clip(lower=0) * HOLD_SWAP / 252
    return pos, fixed


def hour_extremes(symbol, index, close_ln):
    """ln of the highest high and the lowest low of each server hour of `index` (M1 high/low; close if the file
    has no high/low, close of the bar if the hour has no minute data)."""
    f = DATA / f"{symbol}_M1.csv.gz"
    cols = list(pd.read_csv(f, nrows=0).columns)
    hl = "high" in cols and "low" in cols
    use = ["time", "high", "low"] if hl else ["time", "close"]
    d = pd.read_csv(f, usecols=use, dtype={c: (np.int64 if c == "time" else np.float64) for c in use})
    d = d[d.time < HOLD_EPOCH]
    g = d.groupby(d.time // 3600)
    hi, lo = (g.high.max(), g.low.min()) if hl else (g.close.max(), g.close.min())
    del d
    keys = ((index - pd.Timestamp("1970-01-01")) // pd.Timedelta(hours=1)).to_numpy()
    lhi = np.log(hi.reindex(keys).to_numpy())
    llo = np.log(lo.reindex(keys).to_numpy())
    print(f"  {symbol}: hour extremes from M1 {'high/low' if hl else 'close only (no high/low columns)'}, "
          f"{int(np.isnan(lhi).sum())} of {len(keys)} hours without data (bar close used)")
    return np.where(np.isnan(lhi), close_ln, lhi), np.where(np.isnan(llo), close_ln, llo)


def build_bars():
    """Size-1 arrays per hourly bar (server hours 1-22, weekdays, from START_DAY) and the day boundaries."""
    print("building hourly bars ...")
    f = DATA / "HYDRA_H1.csv.gz"
    if not f.exists():
        raise SystemExit(f"{f} missing: run tools/backtest_hydra.hourly() once to build it")
    H = holdout.drop(pd.read_csv(f, index_col=0, parse_dates=True))[["AUDCAD", "XAUUSD"]]
    idx = H.index
    lp_g, lp_a = np.log(H.XAUUSD.to_numpy()), np.log(H.AUDCAD.to_numpy())
    prev_g, prev_a = np.r_[lp_g[0], lp_g[:-1]], np.r_[lp_a[0], lp_a[:-1]]
    hi_a, lo_a = hour_extremes("AUDCAD", idx, lp_a)
    _, lo_g = hour_extremes("XAUUSD", idx, lp_g)
    ginc, gex = grid_hourly(H.AUDCAD)
    gwr = np.where(gex > 0, gex * (lo_a - prev_a), np.where(gex < 0, gex * (hi_a - prev_a), 0.0))
    pos_d, fixed_d = hold_pos(H.XAUUSD)
    dates = idx.normalize()
    pos = pos_d.reindex(dates).fillna(0.0).to_numpy()
    hinc = pos * (lp_g - prev_g)
    hwr = pos * (lo_g - prev_g)
    uniq, first = np.unique(dates.to_numpy(), return_index=True)
    starts_all = np.r_[first, len(idx)]
    last = starts_all[1:] - 1
    hinc[last] += fixed_d.reindex(pd.DatetimeIndex(uniq)).fillna(0.0).to_numpy()   # fixed costs at the day's close
    k0 = int(np.searchsorted(uniq, np.datetime64(START_DAY)))
    s0 = int(starts_all[k0])
    days = pd.DatetimeIndex(uniq[k0:])
    gmode, gaz, gsd, gunit, gnight, gavg = grid_signals(H.AUDCAD)
    avgp, unitp = np.r_[gavg[0], gavg[:-1]], np.r_[0.0, gunit[:-1]]    # the average and step the previous close set
    b = SimpleNamespace(days=days, starts=(starts_all[k0:] - s0), pos=pos[s0:], gex=gex[s0:], hinc=hinc[s0:],
                        hwr=hwr[s0:], ginc=ginc[s0:], gwr=gwr[s0:],
                        gret=(lp_g - prev_g)[s0:], glow=(lo_g - prev_g)[s0:], aret=(lp_a - prev_a)[s0:],
                        alo=(lo_a - prev_a)[s0:], ahi=(hi_a - prev_a)[s0:], mode=gmode[s0:], az=gaz[s0:],
                        sd=gsd[s0:], unit=gunit[s0:], night=gnight[s0:], apr=prev_a[s0:], avgp=avgp[s0:],
                        unitp=unitp[s0:])
    b.hinc[0] = 0.0
    per = days.to_period("M")
    for p in per.unique():
        ix = np.flatnonzero(per == p)
        MONTHS[p] = (int(ix[0]), int(ix[-1]) + 1)
    print(f"  {len(days)} days {days[0].date()} .. {days[-1].date()}, {len(b.pos)} hourly bars")
    DAYS_IDX[:] = list(days)
    return b


def day_sums(x, b):
    return np.add.reduceat(x, b.starts[:-1])


def edge_set(b, r, edge):
    """Edge-adjusted lists for the round: hourly hold and grid pnl less (1 - edge) * their mean hourly pnl, daily
    totals rr = r - (1 - edge) * mean(r) as in the existing scripts, other = rr less the hourly hold+grid sum."""
    k = 1.0 - edge
    mu_h, mu_g = b.hinc.mean(), b.ginc.mean()
    hinc, ginc = b.hinc - k * mu_h, b.ginc - k * mu_g
    rr = (r - k * r.mean()).to_numpy()
    return SimpleNamespace(
        edge=edge, rr=rr.tolist(), rr_np=rr, hinc=hinc.tolist(), hwr=(b.hwr - k * mu_h).tolist(),
        ginc=ginc.tolist(), gwr=(b.gwr - k * mu_g).tolist(), gex=b.gex.tolist(), pos=b.pos.tolist(),
        starts=b.starts.tolist(), other=(rr - day_sums(hinc + ginc, b)).tolist(), vol=float(np.std(rr, ddof=1)),
        pen=k * (mu_h + mu_g), gret=b.gret.tolist(), glow=b.glow.tolist(), aret=b.aret.tolist(),
        alo=b.alo.tolist(), ahi=b.ahi.tolist(), mode=b.mode.tolist(), az=b.az.tolist(), sd=b.sd.tolist(),
        unit=b.unit.tolist(), night=b.night.tolist(), apr=b.apr.tolist(), avgp=b.avgp.tolist(),
        unitp=b.unitp.tolist())


# ---------------------------------------------------------------- part 2: rounds

def goal_size(eq, goal, left, cap, vol):
    x = min(max(eq / goal, 1e-6), 1 - 1e-6)
    return min(cap, m.SCALE * norm.pdf(norm.ppf(x)) / (x * np.sqrt(left)) / vol)


def margin_day(E, d, size, st, a_gold, a_fx):
    """One day with margin, in units of the day-open equity. st = [grid target held in the previous bar, clip ratio
    actual / target of the grid position]. Returns (equity factor, stopped out)."""
    a, b = E.starts[d], E.starts[d + 1]
    prev_t, rho = st
    hm_full = size * E.pos[a] * a_gold
    gm_carry = size * rho * abs(prev_t) * a_fx
    ch = min(1.0, CLIP * max(0.0, 1.0 - gm_carry) / hm_full) if hm_full > 0 else 1.0   # hold entry clip
    hm = hm_full * ch
    cum_h = cum_g = 0.0
    for i in range(a, b):
        t = E.gex[i]
        eq_s = 1.0 + size * (cum_h + cum_g)
        if t == 0.0:
            rho = 1.0
        elif prev_t == 0.0 or t * prev_t < 0.0:                          # a fresh grid cycle: its whole size is new
            want = size * abs(t) * a_fx
            rho = min(1.0, CLIP * max(eq_s - hm, 0.0) / want) if want > 0 else 1.0
        elif abs(t) > abs(prev_t) + 1e-12:                               # further levels on the same side
            have = rho * abs(prev_t)
            room = CLIP * max(eq_s - hm - size * have * a_fx, 0.0) / (size * a_fx) if a_fx > 0 else float("inf")
            rho = (have + min(abs(t) - abs(prev_t), room)) / abs(t)
        prev_t = t                                                       # levels closed: the ratio is kept
        margin = hm + size * rho * abs(t) * a_fx
        eq_w = 1.0 + size * (cum_h + ch * E.hwr[i] + cum_g + rho * E.gwr[i])
        if margin > 0 and eq_w < STOP_LEVEL * margin:
            st[0], st[1] = prev_t, rho
            return max(0.0, min(STOP_LEVEL * margin, eq_s)), True        # closed as the level touches 50%
        cum_h += ch * E.hinc[i]
        cum_g += rho * E.ginc[i]
    st[0], st[1] = prev_t, rho
    return max(0.0, 1.0 + size * (cum_h + cum_g + E.other[d])), False


def new_state():
    """EA-like state: eq equity, H held gold notional, lv open grid level notionals, s side, base cycle level
    notional, pd grid killed by the panic exit (until |z| < 0.5), fh / fg floating pnl of the hold and the grid
    (balance = eq - fh - fg), mins the daily minimum margin levels seen."""
    return dict(eq=1.0, H=0.0, lv=[], s=0, base=0.0, pd=False, fh=0.0, fg=0.0, mins=[])


def ea_day(E, d, size, S, ag, af, om, sizef):
    """One day the way the EA trades it. All notionals in USD of the round's equity units (start 1.0).
    Returns stopped. size = GoalSize at the day's first hour (live equity then); sizef(eq) = GoalSize at the live
    equity of the moment (same goal, days left, cap, vol).
    Hold (Hold(), once a day at the open): target = equity * size * pos; no trade inside the 25% band; a buy is
    clipped to 50% of the free margin, a sell is not. The held notional moves with gold.
    Grid (Grid(), at every hourly close): the target is built from the levels actually open; a new cycle fixes its
    per-level notional as BALANCE (equity less the floating pnl of hold and grid) * sizef(live equity then) * 0.035 /
    (risk * step); each new level is clipped to 50% of the free margin and the grid stops adding levels when nothing
    is left. The cycle and its levels carry across days.
    Panic exit (InpGridPanic): inside an hour, when the adverse extreme gets to |z| >= levels + 1 + panic steps from
    the average the grid closes at that price and stays dead until |z| < 0.5 at a close. Bars carry no order inside
    the hour, so panic and the margin stop are compared by the fraction of the bar's adverse path at which each is
    reached (the less extreme price wins).
    Other legs (the rest of the day's pnl) are booked at the day's close on the day-open size; their margin is
    om * day-open equity * size (constant) and counts in the free margin.
    Stop-out inside a bar when equity at the bar's worst < 50% of margin: the round ends at 0.5 * margin."""
    a, e_ = E.starts[d], E.starts[d + 1]
    eq, H, lv, s, base = S["eq"], S["H"], S["lv"], S["s"], S["base"]
    pdead, fh, fg = S["pd"], S["fh"], S["fg"]
    eo = eq
    omm = om * eo * size
    G = sum(lv)
    mn = math.inf
    T = eq * size * E.pos[a]
    if T <= 0.0:
        if H > 0.0:
            eq -= H * HC
            H, fh = 0.0, 0.0
    else:
        diff = T - H
        if abs(diff) > HOLD_BAND * max(T, H):
            if diff > 0.0:
                free = max(eq - H * ag - G * af - omm, 0.0)
                add = min(diff, CLIP * free / ag) if ag > 0 else diff
                H += add
                eq -= add * HC
            else:
                eq -= -diff * HC
                fh *= T / H if H > 0 else 0.0
                H = T
    pen = eo * size * E.pen
    panic_at = GRID_LEVELS + 1 + GRID_PANIC
    for i in range(a, e_):
        marg = H * ag + G * af + omm
        ext = (E.alo[i] if s > 0 else E.ahi[i]) if s else 0.0
        adv = s * G * ext + H * math.expm1(E.glow[i])
        if marg > 0.0:
            mn = min(mn, (eq + adv) / marg)
        phm = math.inf
        if marg > 0.0 and eq + adv < STOP_LEVEL * marg:
            phm = max(0.0, (eq - STOP_LEVEL * marg) / -adv) if adv < 0.0 else 0.0
        php = math.inf
        if lv and E.unitp[i] > 0.0 and s * ext < 0.0:
            u = E.unitp[i]
            dpan = (E.avgp[i] - panic_at * u - E.apr[i]) if s > 0 else (E.avgp[i] + panic_at * u - E.apr[i])
            f = dpan / ext
            if f <= 1.0:
                php = max(0.0, f)
        if php < phm:                                         # the grid's panic exit first
            eq += s * G * php * ext - G * GC
            lv, G, s, base, fg, pdead = [], 0.0, 0, 0.0, 0.0, True
            m2 = H * ag + omm
            if m2 > 0.0 and eq + H * math.expm1(E.glow[i]) < STOP_LEVEL * m2:
                S.update(eq=max(0.0, min(STOP_LEVEL * m2, eq)), H=H, lv=lv, s=s, base=base, pd=pdead, fh=fh, fg=fg)
                S["mins"].append(mn)
                return True
            gp = 0.0
        elif phm < math.inf:
            S.update(eq=max(0.0, min(STOP_LEVEL * marg, eq)), H=H, lv=lv, s=s, base=base, pd=pdead, fh=fh, fg=fg)
            S["mins"].append(mn)
            return True
        else:
            gp = s * G * E.aret[i] if s else 0.0
            fg += gp
        hp = H * math.expm1(E.gret[i])
        sw = G * (SWAP_LONG if s > 0 else SWAP_SHORT) * E.night[i] * 1e-4 if (s and E.night[i]) else 0.0
        eq += gp + sw + hp - pen
        fh += hp
        H *= math.exp(E.gret[i])
        mode = E.mode[i]
        if mode == 0:
            continue
        if pdead:
            pdead = E.az[i] >= 0.5
            continue
        if mode == 3:
            sd, azv = E.sd[i], E.az[i]
            cur = len(lv) if s * sd < 0 else 0
            t = -sd * max(min(int(azv), GRID_LEVELS), min(cur, math.ceil(azv)))
        else:
            t = 0
        if lv and (t == 0 or (t > 0) != (s > 0)):
            eq -= G * GC                                  # the whole grid is closed, floating pnl is realised
            lv, G, s, base, fg = [], 0.0, 0, 0.0, 0.0
        if abs(t) > len(lv):
            if not lv:
                s = 1 if t > 0 else -1
                base = max(eq - fh - fg, 0.0) * sizef(eq) * GRID_RISK / (GRID_RISK_STEPS * E.unit[i])
            for _ in range(len(lv), abs(t)):
                free = max(eq - H * ag - G * af - omm, 0.0)
                n = min(base, CLIP * free / af) if af > 0 else base
                if n <= 1e-9:
                    break                                 # no free margin: no more levels this cycle
                lv.append(n)
                G += n
                eq -= n * GC
            if not lv:
                s, base = 0, 0.0
        elif 0 < abs(t) < len(lv):
            g0 = G
            while len(lv) > abs(t):
                n = lv.pop()
                G -= n
                eq -= n * GC
            fg *= G / g0 if g0 > 0 else 0.0
    eq -= H * HOLD_SWAP / 252.0
    eq = max(0.0, eq + eo * size * E.other[d])
    S.update(eq=eq, H=H, lv=lv, s=s, base=base, pd=pdead, fh=fh, fg=fg)
    if mn < math.inf:
        S["mins"].append(mn)
    return False


def run_round(E, d0, d1, days, cap, vol, goal, margin, a_gold=0.0, a_fx=0.0, ea=False, om=0.0, fixed=None,
              mins=None):
    """One goal round from day d0 over at most `days` days of the month (d0, d1). Returns (min(eq, goal), stopped).
    margin False: the daily totals of one_round(). margin True: the first margin model (size-1 hold and grid
    re-sized every day). ea True: the EA-like model (ea_day), flat at the round's start, om = other legs' margin
    (OTHER_MARGIN) as a share of day-open equity * size. fixed: a constant size instead of GoalSize (the round then
    only ends at a stop-out or ruin, pass goal 1e9). mins: list that collects the daily minimum margin levels
    (EA-like). LAST[0] = day of the stop-out."""
    eq, stopped = 1.0, False
    LAST[0] = -1
    st = [E.gex[E.starts[d0]], 1.0]
    S = new_state()
    for k in range(min(days, d1 - d0)):
        d = d0 + k
        if ea:
            eq = S["eq"]
        if fixed is not None:
            size = fixed
            sizef = lambda x: fixed
        else:
            size = goal_size(eq, goal, days - k, cap, vol)
            sizef = lambda x, left=days - k: goal_size(x, goal, left, cap, vol)
        if ea:
            stopped = ea_day(E, d, size, S, a_gold, a_fx, om, sizef)
            eq = S["eq"]
            if stopped:
                LAST[0] = d
                break
        elif margin:
            f, stopped = margin_day(E, d, size, st, a_gold, a_fx)
            eq = eq * f
            if stopped:
                LAST[0] = d
                break
        else:
            eq *= max(0.0, 1.0 + size * E.rr[d])
        if eq >= goal or eq <= m.RUIN:
            break
    if mins is not None and ea:
        mins.extend(S["mins"])
    return min(eq, goal), stopped


def part2_checks(b, E1, r, runs):
    print("=" * 100)
    print("PART 2  hourly model checks")
    legs = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    ref = (legs.grid + legs.hold).reindex(b.days)
    mine = pd.Series(day_sums(b.hinc + b.ginc, b), index=b.days)
    ok = ref.notna()
    d = (mine[ok] - ref[ok]).abs()
    print(f"hourly hold+grid summed per day against the daily file's grid+hold, {int(ok.sum())} days: "
          f"correlation {np.corrcoef(mine[ok], ref[ok])[0, 1]:.4f}, mean abs diff {100 * d.mean():.4f}% of equity, "
          f"max {100 * d.max():.3f}%, days in the model not in the file {int((~ok).sum())}")
    miss = len(r.index.difference(b.days))
    print(f"days in the daily() series not in the hourly bars: {miss}")
    worst = 0.0
    n = 0
    for goal in (3, 4, 5):
        m.GOAL = float(goal)
        for run in runs[goal]:
            d0, d1 = MONTHS[pd.Period(f"{run['month'][:4]}-{run['month'][4:]}", "M")]
            ref_v = m.one_round(E1.rr_np[d0:d1], *PRESET)
            mine_v, _ = run_round(E1, d0, d1, *PRESET[:2], PRESET[2], goal, False)
            worst = max(worst, abs(ref_v - mine_v))
            n += 1
    print(f"no-margin hourly model against one_round(), preset, edge 1.0, {n} month-goal rounds: "
          f"max abs difference {worst:.2e}")


# ---------------------------------------------------------------- part 3

def part3a(E1, runs, a_gold, a_fx, om):
    print("=" * 100)
    print(f"PART 3a  tester against model, 21 months, preset (23 days, cap 50, vol 0.0156), edge 1.0, "
          f"a_gold {a_gold:.5f}, a_fx {a_fx:.5f}, OTHER_MARGIN {om:.3f}")
    print("EA-like: live-equity sizes, grid base from balance, panic exit; EA+OM adds the other legs' margin "
          "(a sensitivity, not a fit)")
    for goal in (3, 4, 5):
        print(f"\n=== goal {goal}x")
        print("month    tester  tester SO date | no margin | v1  SO  date       | EA-like  SO  date       "
              "| EA+OM   SO  date")
        c = defaultdict(int)
        for run in runs[goal]:
            d0, d1 = MONTHS[pd.Period(f"{run['month'][:4]}-{run['month'][4:]}", "M")]
            nm, _ = run_round(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, False)
            mg, so = run_round(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, True, a_gold, a_fx)
            dv1 = str(DAYS_IDX[LAST[0]].date()) if so else ""
            ea, so2 = run_round(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, True, a_gold, a_fx, ea=True)
            dv2 = str(DAYS_IDX[LAST[0]].date()) if so2 else ""
            eo, so3 = run_round(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, True, a_gold, a_fx, ea=True, om=om)
            dv3 = str(DAYS_IDX[LAST[0]].date()) if so3 else ""
            tso = run["so"] is not None
            tdate = run["rows"][run["so"]][0][:10] if tso else ""
            print(f"{run['month']}  {run['mult']:5.2f}x  {tdate:10s}     | {nm:6.2f}x   | {mg:6.2f}x "
                  f"{'yes' if so else 'no ':3s} {dv1:10s} | {ea:6.2f}x  {'yes' if so2 else 'no ':3s} {dv2:10s} | "
                  f"{eo:6.2f}x {'yes' if so3 else 'no ':3s} {dv3:10s}")
            c["months"] += 1
            c["tester_reach"] += run["mult"] >= goal * TOL
            c["nm_reach"] += nm >= goal * TOL
            c["tester_so"] += tso
            for key, val, st_ in (("v1", mg, so), ("ea", ea, so2), ("eo", eo, so3)):
                c[key + "_reach"] += val >= goal * TOL
                c[key + "_so"] += st_
                c[key + "_agree"] += tso == st_
                c[key + "_both"] += tso and st_
        print(f"goal {goal}x: months {c['months']}; goal reached (0.3% tolerance) tester {c['tester_reach']}, "
              f"no margin {c['nm_reach']}, v1 {c['v1_reach']}, EA-like {c['ea_reach']}, EA+OM {c['eo_reach']}; "
              f"stop-outs tester {c['tester_so']}, v1 {c['v1_so']}, EA-like {c['ea_so']}, EA+OM {c['eo_so']}; "
              f"stop-out agreement (month by month, both stopped in brackets) v1 {c['v1_agree']} ({c['v1_both']}), "
              f"EA-like {c['ea_agree']} ({c['ea_both']}), EA+OM {c['eo_agree']} ({c['eo_both']}) of {c['months']}")


def stats(rows, goal):
    """rows: (period, no margin, v1, v1 stopped, EA, EA stopped, EA+OM, EA+OM stopped). Returns, for no margin,
    v1, EA and EA+OM: months, then (P(goal), P(stop-out), P(ruin), median) per variant."""
    c = [np.array([x[i] for x in rows], dtype=float) for i in range(1, 8)]
    out = [len(rows), np.mean(c[0] >= goal * TOL)]
    for v, so in ((1, 2), (3, 4), (5, 6)):
        out += [np.mean(c[v] >= goal * TOL), np.mean(c[so]), np.mean(c[v] <= m.RUIN + 1e-9), np.median(c[v])]
    return tuple(out)


def part3b(sets, a_gold, a_fx, om):
    print("=" * 100)
    print("PART 3b  month-start rounds, every month with >= 15 days, 2010-06 to 2025-09 (history from the legs file)")
    months = [(p, d0, d1) for p, (d0, d1) in MONTHS.items() if d1 - d0 >= 15]
    print(f"{len(months)} months {months[0][0]} .. {months[-1][0]}; a_gold {a_gold:.5f}, a_fx {a_fx:.5f}, "
          f"OTHER_MARGIN {om:.3f}")
    print("v1 = size-1 hold and grid re-sized every day; EA = EA-like hold (lots kept, 25% band, diff-only clip), "
          "grid (cycle base from balance and live size, level clip, panic exit), live-equity sizes; EA+OM adds the "
          "other legs' margin")
    print("goal  settings  edge  period       months | P(goal) no margin | v1: P(goal) P(SO) P(ruin) median | "
          "EA: P(goal) P(SO) P(ruin) median | EA+OM: P(goal) P(SO) P(ruin) median")
    for goal in (3, 4, 5):
        for name, days, cap in (("odds", 21, 20.0), ("preset", 23, 50.0)):
            for edge, E in sets.items():
                vol = E.vol if name == "odds" else PRESET[2]
                rows = []
                for p, d0, d1 in months:
                    nm, _ = run_round(E, d0, d1, days, cap, vol, goal, False)
                    mg, so = run_round(E, d0, d1, days, cap, vol, goal, True, a_gold, a_fx)
                    ea, so2 = run_round(E, d0, d1, days, cap, vol, goal, True, a_gold, a_fx, ea=True)
                    eo, so3 = run_round(E, d0, d1, days, cap, vol, goal, True, a_gold, a_fx, ea=True, om=om)
                    rows.append((p, nm, mg, so, ea, so2, eo, so3))
                for label, sel in (("all", rows), ("to 2017", [x for x in rows if x[0].year <= 2017]),
                                   ("2018 on", [x for x in rows if x[0].year >= 2018])):
                    r_ = stats(sel, goal)
                    cols = " | ".join(f"{100 * r_[k]:6.1f}% {100 * r_[k + 1]:5.1f}% {100 * r_[k + 2]:5.1f}% "
                                      f"{r_[k + 3]:6.2f}x" for k in (2, 6, 10))
                    print(f"{goal}x    {name:8s} {edge:3.1f}   {label:8s}   {r_[0]:5d} | {100 * r_[1]:10.1f}%       | "
                          f"{cols}")


def part3c(E1, a_gold, a_fx, om):
    print("=" * 100)
    print("PART 3c  margin level and the size that reaches the stop-out, from EA-like state (edge 1.0)")
    months = [(p, d0, d1) for p, (d0, d1) in MONTHS.items() if d1 - d0 >= 15]
    for goal in (3, 4, 5):
        for tag, o in (("EA-like", 0.0), ("EA+OM", om)):
            mins = []
            for p, d0, d1 in months:
                run_round(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, True, a_gold, a_fx, ea=True, om=o,
                          mins=mins)
            x = 100 * np.array(mins)
            print(f"goal {goal}x {tag:8s}: daily minimum margin level over the days the goal rounds traded "
                  f"({len(x)} days, {len(months)} month-start rounds), % : 0.1th {np.percentile(x, 0.1):.0f}  "
                  f"1st {np.percentile(x, 1):.0f}  5th {np.percentile(x, 5):.0f}  50th {np.percentile(x, 50):.0f}  "
                  f"share of days below 100% {100 * np.mean(x < 100):.1f}%, below 70% {100 * np.mean(x < 70):.1f}%")
    sizes = (2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 70, 100)
    print("\nsize at which the margin level hits 50%: for each month-start round (23 days) the smallest FIXED size of "
          f"{sizes} at which EA-like state ends in a stop-out; percentiles across the {len(months)} months "
          "(inf = no stop-out up to the largest size)")
    for tag, o in (("EA-like", 0.0), ("EA+OM", om)):
        first = []
        for p, d0, d1 in months:
            hit = math.inf
            for sz in sizes:
                _, so = run_round(E1, d0, d1, 23, 1e9, 1.0, 1e9, True, a_gold, a_fx, ea=True, om=o, fixed=float(sz))
                if so:
                    hit = sz
                    break
            first.append(hit)
        f = np.array(first, dtype=float)
        pc = " ".join(f"{q}th {np.percentile(f, q):g}" for q in (1, 5, 10, 25, 50))
        print(f"{tag:8s}: min {f.min():g}  {pc}  months never stopped {int(np.isinf(f).sum())}  "
              f"| share of months stopped at size 5: ", end="")
        print(f"{100 * np.mean(f <= 5):.1f}%, 10: {100 * np.mean(f <= 10):.1f}%, 20: {100 * np.mean(f <= 20):.1f}%, "
              f"50: {100 * np.mean(f <= 50):.1f}%")


def main():
    runs = scan_runs()
    print("tester runs found: " + ", ".join(f"{g}x {len(v)}" for g, v in runs.items()))
    a_gold, a_fx, om = part1(runs)
    b = build_bars()
    print("KNOWN LIMITATION (lesson 9): server hours 23 and 0 have no data in the hourly file, so no bar, panic, "
          "stop-out or grid action is modelled in them; a move there shows up only in the next bar's return")
    r = m.daily().reindex(b.days).fillna(0.0)
    E1 = edge_set(b, r, 1.0)
    part2_checks(b, E1, m.daily(), runs)
    part3a(E1, runs, a_gold, a_fx, om)
    part3b({1.0: E1, 0.7: edge_set(b, r, 0.7)}, a_gold, a_fx, om)
    part3c(E1, a_gold, a_fx, om)


if __name__ == "__main__":
    main()
