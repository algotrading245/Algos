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
          EA+legs (round 4, the main mode): the other legs get their own margin and their own order clip. Every leg
          is a list of tickets (entry hour, segments (hour from, hour to, notional per unit of day-open equity * size),
          the day's pnl from marketdata/hydra_legs_daily.csv.gz / candidate_legs_daily.csv.gz, unchanged). At the first
          bar whose hour is inside the ticket's window ea_day sizes it as day-open equity * size * notional, clips it to
          CLIP * free margin of that moment (free = equity less hold, grid and the other legs already open), carries its
          margin (gold / FX / other rate of part 1, USD notional) in the stop-out check while the bars of its window run,
          and books its pnl * clip ratio at the day's close. NO INTRADAY PATH EXISTS for the legs (the files hold daily
          results), so the pnl is still booked at the close and the margin is released after the window; a leg's open
          loss never enters the stop-out check. A ticket whose window has no bar (hours 23 and 0, holidays) is booked
          unclipped without margin. E.res = E.other less all tickets (bell at 23:00, which has no bar, the quartet part
          that could not be split, hold / grid hourly against daily mismatch, the edge penalty, days with a pnl but no
          notional) is booked unclipped at the close, so for every edge the booked total equals E.other.
          Notionals (build_legs): fix, cross, fall, morning, after by the cost-linearity trick (their pnl is linear in
          the cost, the stop branch does not depend on it, so notional = (pnl at cost 0 - pnl) / (cost * 1e-4)); dip,
          Tokyo, Meridian from tools/quartet_model.py (weights replicated from backtest_hydra.quartet); breakout from
          the USD/JPY 01:00-09:00 range; noise a constant. Every leg, its hours, notional statistics and each assumption
          is printed by part 0. EA+OM stays as a comparison column; EA-like has no other margin at all.
  Part 3  (a) tester against model per month and goal, (b) month-start rounds 2010-06 on, (c) EA-like daily minimum
          margin level and the fixed size at which a month first ends in a stop-out or in ruin (percentiles across
          months), (d) per tester month: the other legs' realised pnl in the tester against the model's (clipped and
          before the clip), to split the tester/model gap into margin clip and leg fidelity (lesson 7).
  Part 4  self-checks: margin off equals one_round(); EA+legs with no clip and constant margin equals EA+OM; the legs'
          pnl, hold and grid add up to the daily file.
Round 4 changes against round 3: other legs with their own margin and clip (above); part 3c counts ruin as a hit
(own column next to stop-out) and words the day share precisely; the daily minimum margin level is recorded for every
day (inf when nothing was open) so the share can be given over all days too; v1 is no longer reported.
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
ACC = {}                         # run_round's by-products: ol (day, clipped, unclipped other-leg pnl), nobar, last, mins


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
        return 1 / 500, 1 / 500, 1 / 500, 0.0
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
    return a_gold, a_fx, a_oth, om


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
                        unitp=unitp[s0:], hour=idx.hour[s0:].to_numpy())
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
        unitp=b.unitp.tolist(), hour=b.hour.tolist())


# ---------------------------------------------------------------- the other legs as tickets (round 4)

def usdjpy_range(days):
    """Range of USD/JPY 01:00-09:00 server time of every day, as a fraction of the mid price (breakout leg: the
    London range the EA trades out of). M1 high/low, close if the file has none; NaN on days without data."""
    f = DATA / "USDJPY_M1.csv.gz"
    cols = list(pd.read_csv(f, nrows=0).columns)
    hl = "high" in cols and "low" in cols
    use = ["time", "high", "low"] if hl else ["time", "close"]
    d = pd.read_csv(f, usecols=use, dtype={c: (np.int64 if c == "time" else np.float64) for c in use})
    d = d[d.time < HOLD_EPOCH]
    mod = (d.time.to_numpy() % 86400) // 60
    d = d[(mod >= 60) & (mod < 540)]
    g = d.groupby(d.time // 86400)
    hi, lo = (g.high.max(), g.low.min()) if hl else (g.close.max(), g.close.min())
    del d
    key = ((days - pd.Timestamp("1970-01-01")) // pd.Timedelta(days=1)).to_numpy()
    h, l_ = hi.reindex(key).to_numpy(), lo.reindex(key).to_numpy()
    return (h - l_) / ((h + l_) / 2.0)


def _cut(x, days):
    """A daily series on the model's days through holdout.drop(), 0 where it has no value, as a numpy array."""
    return holdout.drop(x).reindex(days).fillna(0.0).to_numpy()


def build_legs(b):
    """The other legs as tickets, per model day. A ticket is (h0, h1, segs, kd, pnl, cmp, nmax, name): entry hour,
    exit hour (server clock, exclusive), segs = [(hour from, hour to, notional per unit of day-open equity * size)],
    kd 0 gold / 1 FX / 2 other (the margin rate), pnl = the leg's daily result at size 1 from the two gz files
    (unchanged), cmp True for the legs the tester's 'other symbols' comparison covers (not gold, not AUDCAD), nmax
    the largest notional of its segments (what the entry clip is sized on).
    Returns SimpleNamespace(tix, info, ok): tix[d] sorted by entry hour, info = rows for the printout."""
    days = b.days
    n = len(days)
    tix = [[] for _ in range(n)]
    info = []
    legs = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    cand = pd.read_csv(ROOT / "marketdata" / "candidate_legs_daily.csv.gz", index_col=0, parse_dates=True)
    need = {"quartet", "grid", "hold", "fix", "cross", "fall", "morning", "after"}
    if not need <= set(legs.columns) or not {"breakout", "noise"} <= set(cand.columns):
        raise SystemExit(f"legs files lack columns: have {list(legs.columns)} and {list(cand.columns)}")
    file_pnl = {c: _cut(legs[c], days) for c in need}
    file_pnl["breakout"] = _cut(cand["breakout"], days)
    file_pnl["noise"] = _cut(0.55 * cand["noise"], days)         # as m.daily(): 0.55 * the candidate file's noise
    dst = np.array([t.dst().total_seconds() > 0 for t in (days + pd.Timedelta(hours=12)).tz_localize("America/New_York")])

    def add(day, h0, h1, segs, kd, pnl, cmp, name):
        tix[day].append((h0, h1, segs, kd, float(pnl), cmp, max(s[2] for s in segs), name))

    def row(name, sym, kd, hours, nots, pnl_arr, ntix, source, note):
        nz = np.asarray(nots)
        nz = nz[nz > 0]
        has = np.array([any(t[7] == name for t in tix[d_]) for d_ in range(n)])
        got = float(sum(t[4] for d_ in range(n) for t in tix[d_] if t[7] == name))
        info.append(dict(name=name, sym=sym, kd=("gold", "fx", "other")[kd], hours=hours, n=ntix,
                         med=float(np.median(nz)) if len(nz) else 0.0, p90=float(np.percentile(nz, 90)) if len(nz) else 0.0,
                         mx=float(nz.max()) if len(nz) else 0.0, got=got, ref=float(pnl_arr.sum()),
                         nopnl=int(((pnl_arr != 0) & ~has).sum()), source=source, note=note))

    import backtest_hydra as bh
    # ---- fix / cross / fall / morning / after: pnl is linear in the cost (the stop branch does not depend on it),
    #      so notional per unit of equity = (pnl at cost 0 - pnl at cost c) / (c * 1e-4) = weight * risk / distance
    c_fix, c_cross, c_fall = 1.2, 2.0, 1.2
    pre0, post0 = bh.fix(0.005, cost=0.0, parts=True)
    pre1, post1 = bh.fix(0.005, cost=c_fix, parts=True)
    n_pre = _cut((pre0 - pre1) / (c_fix * 1e-4), days)
    n_post = _cut((post0 - post1) / (c_fix * 1e-4), days)
    re_fix = _cut(pre1 + post1, days)
    x0 = bh.fix(0.005, cost=0.0, pairs=bh.FIXCROSS, name="HYDRA_FIXX", after=False)
    x1 = bh.fix(0.005, cost=c_cross, pairs=bh.FIXCROSS, name="HYDRA_FIXX", after=False)
    n_cross = _cut((x0 - x1) / (c_cross * 1e-4), days)
    re_cross = _cut(x1, days)
    f0, f1 = bh.fall(0.005, cost=0.0), bh.fall(0.005, cost=c_fall)
    n_fall = _cut((f0 - f1) / (c_fall * 1e-4), days)
    re_fall = _cut(f1, days)
    n_morn, re_morn = np.zeros(n), np.zeros(n)
    for p, c in bh.MORNING.items():
        y0 = bh.morning(0.005, costx=0.0, pairs={p: c})
        y1 = bh.morning(0.005, costx=1.0, pairs={p: c})
        n_morn += _cut((y0 - y1) / (c * 1e-4), days)
        re_morn += _cut(y1, days)
    n_aft, re_aft = np.zeros(n), np.zeros(n)
    for p in ("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF"):
        c = bh.AFTER[p][1]
        y0 = bh.after(0.01, costx=0.0, pairs=(p,))
        y1 = bh.after(0.01, costx=1.0, pairs=(p,))
        n_aft += _cut((y0 - y1) / (c * 1e-4), days)
        re_aft += _cut(y1, days)
    for name, mine, key in (("fix", re_fix, "fix"), ("cross", re_cross, "cross"), ("fall", re_fall, "fall"),
                            ("morning", re_morn, "morning"), ("after", re_aft, "after")):
        print(f"  {name}: recomputed daily pnl against the file column: max abs diff {np.abs(mine - file_pnl[key]).max():.2e} "
              f"(sum recomputed {mine.sum():.4f}, file {file_pnl[key].sum():.4f})")
    k_cnt = defaultdict(int)
    for d_ in range(n):
        if n_pre[d_] > 1e-12 or n_post[d_] > 1e-12:
            segs = [(16, 18, n_pre[d_])] + ([(18, 19, n_post[d_])] if n_post[d_] > 1e-12 else [])
            add(d_, 16, 19, [s for s in segs if s[2] > 1e-12], 1, file_pnl["fix"][d_], True, "fix")
        if n_cross[d_] > 1e-12:
            add(d_, 16, 18, [(16, 18, n_cross[d_])], 1, file_pnl["cross"][d_], True, "cross")
        if n_fall[d_] > 1e-12:
            add(d_, 17, 18, [(17, 18, n_fall[d_])], 1, file_pnl["fall"][d_], True, "fall")
        if n_morn[d_] > 1e-12:
            s = int(dst[d_])
            add(d_, 1 + s, 4 + s, [(1 + s, 4 + s, n_morn[d_])], 1, file_pnl["morning"][d_], True, "morning")
        if n_aft[d_] > 1e-12:
            add(d_, 9, 15, [(9, 15, n_aft[d_])], 1, file_pnl["after"][d_], True, "after")
    cnt = lambda nm: sum(1 for d_ in range(n) for t in tix[d_] if t[7] == nm)
    row("fix", "EURUSD GBPUSD AUDUSD USDCAD USDCHF", 1, "16-18 (pre-fix), 18-19 (post-fix)", n_pre + n_post, file_pnl["fix"], cnt("fix"),
        "backtest_hydra.fix(0.005, cost=1.2, parts=True); window start -120..0 / 0..60 min round the London 4pm fix = server 18:00",
        "fix hour 18:00 fixed (the 2-3 weeks a year the US and UK DST differ are 1 h off); pre and post sized on max(n_pre, n_post)")
    row("cross", "AUDJPY CADJPY GBPJPY", 1, "16-18", n_cross, file_pnl["cross"], cnt("cross"),
        "backtest_hydra.fix(0.005, cost=2.0, pairs=FIXCROSS, name=HYDRA_FIXX, after=False)", "as fix")
    row("fall", "EURUSD GBPUSD AUDUSD USDCAD USDCHF", 1, "17-18", n_fall, file_pnl["fall"], cnt("fall"),
        "backtest_hydra.fall(0.005, cost=1.2), start -60 min before the fix", "as fix")
    row("morning", "EURJPY GBPJPY CADJPY", 1, "1-4 (US winter), 2-5 (US DST)", n_morn, file_pnl["morning"], cnt("morning"),
        "backtest_hydra.morning(0.005, costx=1.0), -60..+60 min round the 9:55 Tokyo fixing = server 02:55 (03:55 in US DST)",
        "window by the US DST flag of the day; the three pairs' notionals summed in one segment")
    row("after", "EURUSD GBPUSD AUDUSD USDCAD USDCHF", 1, "9-15", n_aft, file_pnl["after"], cnt("after"),
        "backtest_hydra.after(0.01, costx=1.0), 5..360 min after server 9:00", "the five pairs' notionals summed in one segment")
    # ---- the Quartet: dip, Tokyo fixing, EUR/USD midday (the bell at 23:00 has no bar)
    try:
        import quartet_model as qm
        cap = {}
        orig = (qm.q.bt.trades, qm.q.bm.trades)

        def wrap(key, fn):
            def g(*a, **k):
                w = fn(*a, **k)
                cap[key] = w[~w.index.duplicated()].copy()
                return w
            return g
        qm.q.bt.trades, qm.q.bm.trades = wrap("tokyo", orig[0]), wrap("meridian", orig[1])
        try:
            data = qm.datasets()
        finally:
            qm.q.bt.trades, qm.q.bm.trades = orig
        W = {leg: qm.walk(d, qm.FEATS + qm.EXTRA[leg], 2014, 0.5, 0.1) for leg, d in data.items()}
        for leg, d in data.items():                              # backtest_hydra.quartet(0.67, 0.80)
            lost = (d.r * d.mult).to_numpy() < 0
            k = np.zeros(len(d), int)
            for i in range(1, len(d)):
                k[i] = min(3, k[i - 1] + 1) if lost[i - 1] else 0
            W[leg] = W[leg] * 0.67 ** k / 0.80
        day_ix = {d: i for i, d in enumerate(days)}
        qpnl = np.zeros(n)
        bell = np.zeros(n)
        dip_n, tok_n, mer_n = np.zeros(n), np.zeros(n), np.zeros(n)
        full = {k: np.zeros(n) for k in ("dip", "tokyo", "meridian")}      # each leg's whole pnl, ticket or not
        clipped = 0
        for leg, d in data.items():
            w = np.nan_to_num(W[leg], nan=1.0)
            pnl_row = (qm.SIZE[leg] * d.r * d.mult).to_numpy() * w
            dayv = d.day.tolist()                                # Timestamps, hashable against day_ix
            if leg == "bell":
                for dv, p_ in zip(dayv, pnl_row):
                    if dv in day_ix:
                        bell[day_ix[dv]] += p_
                continue
            if leg != "dip":
                ref = cap[leg].ref.reindex(d.day).to_numpy()
                aa = cap[leg].a.reindex(d.day).to_numpy()
                bb = cap[leg].b.reindex(d.day).to_numpy() if "b" in cap[leg].columns else aa + 90
            for i in range(len(d)):
                di = day_ix.get(dayv[i])
                if di is None:
                    continue
                qpnl[di] += pnl_row[i]
                full[leg][di] += pnl_row[i]
                if leg == "dip":
                    a = int(round(d.tod.iloc[i] * 420 + 60))
                    nt, h0, h1 = qm.SIZE["dip"] * d.mult.iloc[i] * w[i], a // 60, -(-(a + 240) // 60)
                    dip_n[di] = max(dip_n[di], nt)
                    kd = 0
                else:
                    if not (ref[i] > 0) or np.isnan(aa[i]):
                        continue
                    nt = qm.SIZE[leg] * w[i] / (3.0 * ref[i] * 1e-4)
                    if nt > 30.0:
                        clipped += 1
                        nt = 30.0
                    a = int(aa[i])
                    b_ = int(bb[i]) if not np.isnan(bb[i]) else a + 90
                    h0, h1, kd = a // 60, -(-b_ // 60), 1
                    (tok_n if leg == "tokyo" else mer_n)[di] = max((tok_n if leg == "tokyo" else mer_n)[di], nt)
                if nt > 1e-12 and h1 > h0:
                    add(di, h0, h1, [(h0, h1, nt)], kd, pnl_row[i], leg != "dip", leg)
        print(f"  quartet legs rebuilt as backtest_hydra.quartet(0.67, 0.80): sum of the four legs against the file's "
              f"quartet column: max abs diff {np.abs(qpnl + bell - file_pnl['quartet']).max():.2e} on "
              f"{int((np.abs(qpnl + bell) > 0).sum())} days (the bell is {bell.sum():.3f} of it and stays in the residual)")
        print(f"  Tokyo / Meridian notional clipped at 30 on {clipped} tickets")
        tkt = lambda nm: [t for d_ in range(n) for t in tix[d_] if t[7] == nm]
        for nm, sym, kd, nn, src, note in (
                ("dip", "XAUUSD", 0, dip_n, "quartet_model.datasets()['dip'], SIZE['dip'] * mult * weight",
                 "entry minute a = tod * 420 + 60, held 4 h (EA text); gold rate"),
                ("tokyo", "USDJPY", 1, tok_n, "quartet_model.datasets()['tokyo'] + backtest_tokyo.trades(got=1) a, b, ref",
                 "notional = SIZE * weight / (3 * ref * 1e-4), ref in bp; hours from the trades frame (b missing: a + 90)"),
                ("meridian", "EURUSD", 1, mer_n, "quartet_model.datasets()['meridian'] + backtest_meridian.trades() a, b, ref",
                 "as Tokyo")):
            ts = tkt(nm)
            hh = sorted({(t[0], t[1]) for t in ts})
            ph = max(set((t[0], t[1]) for t in ts), key=lambda z: sum(1 for t in ts if (t[0], t[1]) == z)) if ts else None
            row(nm, sym, kd, f"{len(hh)} distinct windows, most common {ph[0]}-{ph[1]}" if ph else "none", nn, full[nm],
                len(ts), src, note)
        row("bell", "XAUUSD", 0, "23:00 (no bar)", np.zeros(n), bell, 0, "quartet_model.datasets()['bell']",
            "NO MARGIN AND NO CLIP: the hourly file has no bar at 23:00-00:00; its pnl stays in the residual")
    except Exception as ex:                                      # the quartet stays in the residual, visibly
        print(f"  !! QUARTET SPLIT FAILED ({type(ex).__name__}: {ex}); dip, Tokyo, Meridian and the bell stay in the "
              f"residual with NO margin and NO clip")
        info.append(dict(name="quartet", sym="XAUUSD USDJPY EURUSD", kd="-", hours="-", n=0, med=0.0, p90=0.0, mx=0.0,
                         got=0.0, ref=float(file_pnl["quartet"].sum()), nopnl=0, source="failed", note=str(ex)))
    # ---- breakout (USD/JPY London range) and noise (S&P 500, Nasdaq)
    try:
        rf = usdjpy_range(days)
        okb = (file_pnl["breakout"] != 0) & (rf > 0)
        nb = np.where(okb, np.minimum(0.00125 / np.where(rf > 0, rf, 1.0), 50.0), 0.0)
        const = False
    except Exception as ex:
        print(f"  !! breakout range failed ({type(ex).__name__}: {ex}); constant notional 0.5 on its trade days")
        nb = np.where(file_pnl["breakout"] != 0, 0.5, 0.0)
        const = True
    for d_ in range(n):
        if nb[d_] > 0:
            add(d_, 10, 18, [(10, 18, nb[d_])], 1, file_pnl["breakout"][d_], True, "breakout")
    row("breakout", "USDJPY", 1, "10-18 (entry at 10:00 assumed)", nb, file_pnl["breakout"], cnt("breakout"),
        "candidate_legs_daily.csv.gz; Legs.mqh breakout risk 0.125% of equity at the range distance",
        ("CONSTANT 0.5 (range failed); " if const else "") + "notional = 0.00125 / (USDJPY range 01:00-09:00 as a fraction of "
        "price), at most 50; entry hour 10 and exit 18 assumed, not read from a log")
    nn = np.where(file_pnl["noise"] != 0, 1.1, 0.0)
    for d_ in range(n):
        if nn[d_] > 0:
            add(d_, 16, 23, [(16, 23, nn[d_])], 2, file_pnl["noise"][d_], True, "noise")
    row("noise", "US500 NAS100", 2, "16-23 (16:30-23:00)", nn, file_pnl["noise"], cnt("noise"),
        "candidate_legs_daily.csv.gz x 0.55 (as m.daily()); InpNoiseMult 0.275",
        "constant notional 1.1 = 0.275 * 2 per index * 2 indices on days with a pnl; hours 16:30-23:00 assumed")
    for d_ in range(n):
        tix[d_].sort(key=lambda t: (t[0], t[7]))
    return SimpleNamespace(tix=tix, info=info, file_pnl=file_pnl)


def attach_legs(E, L):
    """Residual of edge set E: its daily other pnl less the tickets, booked unclipped at the close (see the docstring).
    The tickets are shared by all edge sets and always carry the edge-1.0 file pnl; for edge 0.7 the whole edge penalty
    (the day's other pnl less the tickets) therefore lands in the unclipped residual, so the booked total is still
    E.other. Intended: the clip then scales only the edge-1.0 part of each leg, and the legs' margin is the same."""
    E.tix = L.tix
    E.res = [E.other[d] - sum(t[4] for t in L.tix[d]) for d in range(len(E.other))]


def print_legs(L, rt):
    print("=" * 100)
    print("PART 0  the other legs as tickets with their own margin (round 4)")
    print(f"margin rates: gold {rt.ag:.5f}, FX {rt.af:.5f}, other {rt.ao:.5f} of USD notional; entry clip {CLIP} of free margin")
    print("leg       symbols  kind   hours (server)  tickets  notional per unit of equity*size on ticket days: median "
          " p90   max | pnl in tickets / file column (size 1, summed)  ticket-less days with pnl")
    for x in L.info:
        print(f"{x['name']:9s} {x['sym']}  [{x['kd']}]  {x['hours']}  tickets {x['n']}  notional {x['med']:.3f} {x['p90']:.3f} "
              f"{x['mx']:.3f} | pnl {x['got']:.3f} / {x['ref']:.3f}  days without ticket {x['nopnl']}")
        print(f"            source: {x['source']}")
        print(f"            assumption: {x['note']}")
    print("gold-only legs (hold, dip, bell) and the grid are not in the 'other symbols' comparison of part 3d; hold and "
          "grid are the hourly model itself. A leg's pnl is booked at the close (no intraday path), only its margin sits "
          "in the open hours.")


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
    (balance = eq - fh - fg), mins the daily minimum margin levels seen (inf: no margin open that day), ol per
    booked day (other legs' pnl of the tester-comparable legs after the clip, before it), nobar the tickets whose
    window had no bar."""
    return dict(eq=1.0, H=0.0, lv=[], s=0, base=0.0, pd=False, fh=0.0, fg=0.0, mins=[], ol=[], nobar=0)


def legs_margin(tix, rat, hr, k, ag, af, ao):
    """Margin of the open tickets in the bar of hour hr: k (= day-open equity * size) * sum over tickets with a clip
    ratio (opened) of ratio * notional * rate, for the segments with from <= hr < to."""
    tot = 0.0
    for j, t in enumerate(tix):
        c = rat[j]
        if c is None:
            continue
        rate = ag if t[3] == 0 else (af if t[3] == 1 else ao)
        for hs, he, nt in t[2]:
            if hs <= hr < he:
                tot += c * nt * rate
    return k * tot


def ea_day(E, d, size, S, ag, af, om, sizef, ao=0.0, lmode=0):
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
    Other legs, lmode 0: the rest of the day's pnl is booked at the day's close on the day-open size; their margin is
    om * day-open equity * size (constant) and counts in the free margin (EA+OM; om 0 is EA-like).
    lmode 1 (EA+legs): every ticket of the day (E.tix[d]) is opened at the first bar inside its window: notional =
    day-open equity * size * ticket notional, clipped to 50% of the free margin of that bar (equity at its start less
    hold, grid and the tickets already open), its margin (ratio * notional * rate by kind) counts in the stop-out check
    and the free margin while the bars of its segments run; its pnl * ratio is booked at the close together with the
    residual E.res (unclipped, no margin). A ticket with no bar in its window is booked at ratio 1 without margin.
    lmode 2 (plumbing check): tickets booked at ratio 1, margin the constant om * eo * size, so it must equal lmode 0.
    Stop-out inside a bar when equity at the bar's worst < 50% of margin: the round ends at 0.5 * margin."""
    a, e_ = E.starts[d], E.starts[d + 1]
    eq, H, lv, s, base = S["eq"], S["H"], S["lv"], S["s"], S["base"]
    pdead, fh, fg = S["pd"], S["fh"], S["fg"]
    eo = eq
    k0 = eo * size
    tix = E.tix[d] if lmode else ()
    rat = [None] * len(tix) if lmode == 1 else None
    omm = om * eo * size if lmode != 1 else 0.0
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
        if tix and rat is not None:                           # EA+legs: open the tickets whose window has started
            hr = E.hour[i]
            for j, t in enumerate(tix):
                if rat[j] is None and t[0] <= hr < t[1]:
                    free = max(eq - H * ag - G * af - legs_margin(tix, rat, hr, k0, ag, af, ao), 0.0)
                    want = k0 * t[6] * (ag if t[3] == 0 else (af if t[3] == 1 else ao))
                    rat[j] = min(1.0, CLIP * free / want) if want > 0 else 1.0
            omm = legs_margin(tix, rat, hr, k0, ag, af, ao)
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
    if lmode:
        book = E.res[d]
        cl = un = 0.0
        for j, t in enumerate(tix):
            c = 1.0
            if rat is not None:
                if rat[j] is None:
                    S["nobar"] += 1                           # no bar inside the window: booked unclipped, no margin
                else:
                    c = rat[j]
            book += c * t[4]
            if t[5]:
                cl += c * t[4]
                un += t[4]
        eq = max(0.0, eq + k0 * book)
        S["ol"].append((d, k0 * cl, k0 * un))
    else:
        eq = max(0.0, eq + eo * size * E.other[d])
    S.update(eq=eq, H=H, lv=lv, s=s, base=base, pd=pdead, fh=fh, fg=fg)
    S["mins"].append(mn)
    return False


def run_round(E, d0, d1, days, cap, vol, goal, margin, a_gold=0.0, a_fx=0.0, ea=False, om=0.0, fixed=None,
              mins=None, ao=0.0, lmode=0):
    """One goal round from day d0 over at most `days` days of the month (d0, d1). Returns (min(eq, goal), stopped).
    margin False: the daily totals of one_round(). margin True: the first margin model (size-1 hold and grid
    re-sized every day). ea True: the EA-like model (ea_day), flat at the round's start, om = other legs' margin
    (OTHER_MARGIN) as a share of day-open equity * size. fixed: a constant size instead of GoalSize (the round then
    only ends at a stop-out or ruin, pass goal 1e9). mins: list that collects the daily minimum margin levels
    (EA-like). ao = margin rate of the 'other' kind; lmode 0 EA+OM, 1 EA+legs, 2 plumbing check (see ea_day).
    LAST[0] = day of the stop-out; ACC = booked other-leg pnl per day, unbooked tickets, last day, daily minima."""
    eq, stopped = 1.0, False
    LAST[0] = -1
    d = d0 - 1
    S = new_state()
    st = [E.gex[E.starts[d0]], 1.0]
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
            stopped = ea_day(E, d, size, S, a_gold, a_fx, om, sizef, ao, lmode)
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
    ACC.update(ol=S["ol"], nobar=S["nobar"], last=d, mins=S["mins"])
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
    worst, n = margin_off_diff(E1, runs)
    print(f"no-margin hourly model against one_round(), preset, edge 1.0, {n} month-goal rounds: "
          f"max abs difference {worst:.2e}")


def margin_off_diff(E1, runs):
    """Worst |one_round() - run_round(margin False)| over the tester months at every goal, and the round count."""
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
    return worst, n


# ---------------------------------------------------------------- part 3

def go(E, d0, d1, days, cap, vol, goal, mode, rt, **kw):
    """One round in a mode. nm: no margin; ea: EA-like (no other legs' margin); om: EA+OM (constant share); lg: EA+legs
    (tickets with their own margin and clip); lg0: the plumbing check (tickets at ratio 1, constant margin of om, must
    equal om). rt = SimpleNamespace(ag, af, ao, om). Returns (min(eq, goal), stopped)."""
    if mode == "nm":
        return run_round(E, d0, d1, days, cap, vol, goal, False)
    k = dict(a_gold=rt.ag, a_fx=rt.af, ea=True, ao=rt.ao)
    if mode == "om":
        k["om"] = rt.om
    elif mode == "lg":
        k["lmode"] = 1
    elif mode == "lg0":
        k.update(lmode=2, om=rt.om)
    k.update(kw)
    return run_round(E, d0, d1, days, cap, vol, goal, True, **k)


MODES = (("ea", "EA-like"), ("om", "EA+OM"), ("lg", "EA+legs"))


def part3a(E1, runs, rt):
    print("=" * 100)
    print(f"PART 3a  tester against model, 21 months, preset (23 days, cap 50, vol 0.0156), edge 1.0, "
          f"a_gold {rt.ag:.5f}, a_fx {rt.af:.5f}, a_other {rt.ao:.5f}, OTHER_MARGIN {rt.om:.3f}")
    print("EA-like: live-equity sizes, grid base from balance, panic exit, no other legs' margin; EA+OM adds a constant "
          "share for them (a sensitivity, not a fit); EA+legs (main) gives each leg its own margin and clip")
    for goal in (3, 4, 5):
        print(f"\n=== goal {goal}x")
        print("month    tester  tester SO date | no margin | EA-like  SO  date       | EA+OM   SO  date       "
              "| EA+legs SO  date       nobar")
        c = defaultdict(int)
        for run in runs[goal]:
            d0, d1 = MONTHS[pd.Period(f"{run['month'][:4]}-{run['month'][4:]}", "M")]
            nm, _ = go(E1, d0, d1, *PRESET[:2], PRESET[2], goal, "nm", rt)
            res = {}
            for key, _ in MODES:
                v, so = go(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, key, rt)
                res[key] = (v, so, str(DAYS_IDX[LAST[0]].date()) if so else "", ACC["nobar"])
            tso = run["so"] is not None
            tdate = run["rows"][run["so"]][0][:10] if tso else ""
            cells = " | ".join(f"{res[k][0]:6.2f}x {'yes' if res[k][1] else 'no ':3s} {res[k][2]:10s}" for k, _ in MODES)
            print(f"{run['month']}  {run['mult']:5.2f}x  {tdate:10s}     | {nm:6.2f}x   | {cells}  {res['lg'][3]:3d}")
            c["months"] += 1
            c["tester_reach"] += run["mult"] >= goal * TOL
            c["nm_reach"] += nm >= goal * TOL
            c["tester_so"] += tso
            for key, _ in MODES:
                v, st_ = res[key][0], res[key][1]
                c[key + "_reach"] += v >= goal * TOL
                c[key + "_so"] += st_
                c[key + "_agree"] += tso == st_
                c[key + "_both"] += tso and st_
        print(f"goal {goal}x: months {c['months']}; goal reached (0.3% tolerance) tester {c['tester_reach']}, "
              f"no margin {c['nm_reach']}, EA-like {c['ea_reach']}, EA+OM {c['om_reach']}, EA+legs {c['lg_reach']}; "
              f"stop-outs tester {c['tester_so']}, EA-like {c['ea_so']}, EA+OM {c['om_so']}, EA+legs {c['lg_so']}; "
              f"stop-out agreement (month by month, months stopped in both in brackets) EA-like {c['ea_agree']} "
              f"({c['ea_both']}), EA+OM {c['om_agree']} ({c['om_both']}), EA+legs {c['lg_agree']} ({c['lg_both']}) "
              f"of {c['months']}")


def stats(rows, goal):
    """rows: (period, no margin, EA, EA stopped, EA+OM, EA+OM stopped, EA+legs, EA+legs stopped). Returns months,
    P(goal) without margin, then (P(goal), P(stop-out), P(ruin), median) for EA-like, EA+OM, EA+legs."""
    c = [np.array([x[i] for x in rows], dtype=float) for i in range(1, 8)]
    out = [len(rows), np.mean(c[0] >= goal * TOL)]
    for v, so in ((1, 2), (3, 4), (5, 6)):
        out += [np.mean(c[v] >= goal * TOL), np.mean(c[so]), np.mean(c[v] <= m.RUIN + 1e-9), np.median(c[v])]
    return tuple(out)


def part3b(sets, rt):
    print("=" * 100)
    print("PART 3b  month-start rounds, every month with >= 15 days, 2010-06 to 2025-09 (history from the legs file)")
    months = [(p, d0, d1) for p, (d0, d1) in MONTHS.items() if d1 - d0 >= 15]
    print(f"{len(months)} months {months[0][0]} .. {months[-1][0]}; a_gold {rt.ag:.5f}, a_fx {rt.af:.5f}, "
          f"a_other {rt.ao:.5f}, OTHER_MARGIN {rt.om:.3f}")
    print("EA-like = lots kept, 25% hold band, grid base from balance and live size, level clip, panic exit, live-equity "
          "sizes, no other legs' margin; EA+OM adds a constant share for the other legs; EA+legs (main) their own "
          "margin and entry clip. P(SO) = broker stop-out, P(ruin) = round ends at or below 0.2x (either way)")
    print("goal  settings  edge  period       months | P(goal) no margin | EA-like: P(goal) P(SO) P(ruin) median | "
          "EA+OM: P(goal) P(SO) P(ruin) median | EA+legs: P(goal) P(SO) P(ruin) median")
    for goal in (3, 4, 5):
        for name, days, cap in (("odds", 21, 20.0), ("preset", 23, 50.0)):
            for edge, E in sets.items():
                vol = E.vol if name == "odds" else PRESET[2]
                rows = []
                for p, d0, d1 in months:
                    nm, _ = go(E, d0, d1, days, cap, vol, goal, "nm", rt)
                    ea, so1 = go(E, d0, d1, days, cap, vol, goal, "ea", rt)
                    eo, so2 = go(E, d0, d1, days, cap, vol, goal, "om", rt)
                    lg, so3 = go(E, d0, d1, days, cap, vol, goal, "lg", rt)
                    rows.append((p, nm, ea, so1, eo, so2, lg, so3))
                for label, sel in (("all", rows), ("to 2017", [x for x in rows if x[0].year <= 2017]),
                                   ("2018 on", [x for x in rows if x[0].year >= 2018])):
                    r_ = stats(sel, goal)
                    cols = " | ".join(f"{100 * r_[k]:6.1f}% {100 * r_[k + 1]:5.1f}% {100 * r_[k + 2]:5.1f}% "
                                      f"{r_[k + 3]:6.2f}x" for k in (2, 6, 10))
                    print(f"{goal}x    {name:8s} {edge:3.1f}   {label:8s}   {r_[0]:5d} | {100 * r_[1]:10.1f}%       | "
                          f"{cols}")


def part3c(E1, rt):
    print("=" * 100)
    print("PART 3c  margin level and the size that reaches the stop-out or ruin (edge 1.0, month-start rounds)")
    months = [(p, d0, d1) for p, (d0, d1) in MONTHS.items() if d1 - d0 >= 15]
    print("Daily minimum margin level = the lowest (equity at the bar's worst) / margin over the day's bars. 'Days with "
          "margin open' = days with any margin open in some bar (hold, grid or a leg); the share below 100% is "
          "stated both over those days and over all days played (a day with nothing open has level inf and counts "
          "as not below).")
    for goal in (3, 4, 5):
        for key, tag in MODES:
            mins = []
            ends = []
            for p, d0, d1 in months:
                v, so = go(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, key, rt, mins=mins)
                ends.append((v <= m.RUIN + 1e-9, so))
            allx = np.array(mins, dtype=float)
            x = 100 * allx[np.isfinite(allx)]
            print(f"goal {goal}x {tag:8s}: {len(allx)} days played in {len(months)} rounds, {len(x)} with margin open; "
                  f"minimum level of those days, %: 0.1th {np.percentile(x, 0.1):.0f}  1st {np.percentile(x, 1):.0f}  "
                  f"5th {np.percentile(x, 5):.0f}  50th {np.percentile(x, 50):.0f} | share of days with margin open "
                  f"whose minimum level < 100%: {100 * np.mean(x < 100):.1f}%, < 70%: {100 * np.mean(x < 70):.1f}% | "
                  f"over all days: < 100% {100 * np.sum(x < 100) / len(allx):.1f}%, < 70% {100 * np.sum(x < 70) / len(allx):.1f}% "
                  f"| rounds ending in stop-out {sum(e[1] for e in ends)}, in ruin (<= {m.RUIN}x) "
                  f"{sum(e[0] for e in ends)}, of {len(ends)}")
    sizes = (2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 70, 100)
    print("\nsize at which the month first ends badly: for each month-start round (23 days) the smallest FIXED size of "
          f"{sizes} at which the round ends in a stop-out ('stop-out size'), and the smallest at which it ends in a "
          f"stop-out OR in ruin (equity <= {m.RUIN}x, 'hit size'); percentiles across the {len(months)} months "
          "(inf = not reached up to the largest size)")
    for key, tag in MODES:
        first, hit = [], []
        for p, d0, d1 in months:
            so_sz = any_sz = math.inf
            for sz in sizes:
                v, so = go(E1, d0, d1, 23, 1e9, 1.0, 1e9, key, rt, fixed=float(sz))
                if any_sz == math.inf and (so or v <= m.RUIN + 1e-9):
                    any_sz = sz
                if so:
                    so_sz = sz
                    break
            first.append(so_sz)
            hit.append(any_sz)
        for lab, arr in (("stop-out size", first), ("hit size     ", hit)):
            f = np.array(arr, dtype=float)
            pc = " ".join(f"{q}th {np.percentile(f, q):g}" for q in (1, 5, 10, 25, 50))
            print(f"{tag:8s} {lab}: min {f.min():g}  {pc}  never {int(np.isinf(f).sum())}  | share of months hit at size "
                  f"5: {100 * np.mean(f <= 5):.1f}%, 10: {100 * np.mean(f <= 10):.1f}%, 20: {100 * np.mean(f <= 20):.1f}%, "
                  f"50: {100 * np.mean(f <= 50):.1f}%")


def tester_other(run):
    """Net pnl (commission + swap + profit) per day and symbol of the tester's non-gold, non-AUDCAD symbols,
    from the deal rows. {'YYYY.MM.DD': {symbol: net}} and the last deal date."""
    out = defaultdict(lambda: defaultdict(float))
    last = ""
    for x in run["rows"]:
        sym = x[2].upper()
        if not sym or x[3] not in ("buy", "sell"):
            continue
        last = max(last, x[0][:10])
        if sym.startswith("XAU") or sym == "AUDCAD":
            continue
        out[x[0][:10]][sym] += num(x[8]) + num(x[9]) + num(x[10])
    return out, last


def part3d(E1, runs, rt):
    print("=" * 100)
    print("PART 3d  other legs per tester month: tester realised pnl against the model's (lesson 7), preset, edge 1.0")
    print("Other legs = every tester symbol except XAU* and AUDCAD; the model side = the tickets marked comparable "
          "(fix, cross, fall, morning, after, Tokyo, Meridian, breakout, noise; not dip or the bell). Both over the "
          "same days: the model's booked days up to the tester's last deal date; shares of the round's start equity "
          "(tester: net / deposit). 'clipped' = EA+legs after the entry clip, 'unclipped' = same model before it. "
          "Stopped: tester / model.")
    tot = defaultdict(float)
    per = defaultdict(lambda: defaultdict(float))
    rows_all = []
    for goal in (3, 4, 5):
        print(f"\n=== goal {goal}x")
        print("month    days | tester other | model clipped | model unclipped | clip effect | fidelity (tester - unclipped) "
              "| stopped t/m | unopened tickets")
        for run in runs[goal]:
            d0, d1 = MONTHS[pd.Period(f"{run['month'][:4]}-{run['month'][4:]}", "M")]
            _, so = go(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, "lg", rt)
            ol, nob = list(ACC["ol"]), ACC["nobar"]
            net, last = tester_other(run)
            keep = [(d, cl, un) for d, cl, un in ol if DAYS_IDX[d].strftime("%Y.%m.%d") <= last]
            dates = {DAYS_IDX[d].strftime("%Y.%m.%d") for d, _, _ in keep}
            tst = 0.0
            for dt in dates:
                for sym, v in net.get(dt, {}).items():
                    tst += v / run["deposit"]
                    per[goal][sym] += v / run["deposit"]
            cl = sum(x[1] for x in keep)
            un = sum(x[2] for x in keep)
            tso = run["so"] is not None
            rows_all.append((tst, cl, un))
            for k_, v_ in (("t", tst), ("c", cl), ("u", un)):
                tot[(goal, k_)] += v_
            print(f"{run['month']}  {len(keep):3d} | {100 * tst:+10.1f}% | {100 * cl:+11.1f}% | {100 * un:+13.1f}% | "
                  f"{100 * (cl - un):+9.1f}% | {100 * (tst - un):+10.1f}% | "
                  f"{'yes' if tso else 'no ':3s} / {'yes' if so else 'no ':3s} | {nob}")
        t, c_, u = tot[(goal, "t")], tot[(goal, "c")], tot[(goal, "u")]
        print(f"goal {goal}x sum over the months: tester {100 * t:+.1f}%, model clipped {100 * c_:+.1f}%, unclipped "
              f"{100 * u:+.1f}% of start equity; tester - clipped {100 * (t - c_):+.1f}% = clip effect "
              f"{100 * (c_ - u):+.1f}% (model clipped less unclipped) + fidelity {100 * (t - u):+.1f}% "
              f"(tester less unclipped)")
        print("   tester other-leg pnl by symbol, summed over the months, % of start equity: "
              + "  ".join(f"{s} {100 * v:+.1f}" for s, v in sorted(per[goal].items(), key=lambda kv: kv[1])))
    a = np.array(rows_all)
    print(f"\nall 63 rounds: median per round tester {100 * np.median(a[:, 0]):+.1f}%, clipped {100 * np.median(a[:, 1]):+.1f}%, "
          f"unclipped {100 * np.median(a[:, 2]):+.1f}%; median clip effect {100 * np.median(a[:, 1] - a[:, 2]):+.2f}%, "
          f"median fidelity {100 * np.median(a[:, 0] - a[:, 2]):+.1f}%; sums tester {100 * a[:, 0].sum():+.1f}%, "
          f"clipped {100 * a[:, 1].sum():+.1f}%, unclipped {100 * a[:, 2].sum():+.1f}%")


def part4(E1, runs, rt, L, b):
    print("=" * 100)
    print("PART 4  self-checks")
    worst, n = margin_off_diff(E1, runs)
    print(f"(1) margin off against one_round(): max abs difference {worst:.2e} over {n} rounds "
          f"({'OK' if worst < 1e-9 else 'DIFFERENT'})")
    dmax, flags, n2 = 0.0, 0, 0
    for goal in (3, 4, 5):
        for run in runs[goal]:
            d0, d1 = MONTHS[pd.Period(f"{run['month'][:4]}-{run['month'][4:]}", "M")]
            v1, s1 = go(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, "om", rt)
            v2, s2 = go(E1, d0, d1, PRESET[0], PRESET[1], PRESET[2], goal, "lg0", rt)
            dmax = max(dmax, abs(v1 - v2))
            flags += s1 != s2
            n2 += 1
    print(f"(2) EA+legs with every clip ratio 1 and the constant margin against EA+OM: max abs end-equity difference "
          f"{dmax:.2e}, stop-out flags different in {flags} of {n2} rounds ({'OK' if dmax < 1e-9 and flags == 0 else 'DIFFERENT'})")
    n_d = len(E1.other)
    sum_t = np.array([sum(t[4] for t in L.tix[d]) for d in range(n_d)])
    res = np.array(E1.res)
    hg = day_sums(np.array(E1.hinc) + np.array(E1.ginc), b)
    fp = L.file_pnl
    daily = m.daily().reindex(b.days).fillna(0.0).to_numpy()
    cols = sum(fp[c] for c in fp)
    print(f"(3a) the ten file columns summed against m.daily(): max abs diff {np.abs(cols - daily).max():.2e} over {n_d} days "
          f"(a nonzero value means the legs file has more columns than the ten used)")
    print(f"(3b) tickets + residual + hourly hold + hourly grid against the model's daily total (edge 1.0): max abs diff "
          f"{np.abs(sum_t + res + hg - np.array(E1.rr)).max():.2e}; tickets + residual against E.other: "
          f"{np.abs(sum_t + res - np.array(E1.other)).max():.2e}")
    named = {c for c in fp if c not in ("quartet", "grid", "hold")}
    exp = fp["quartet"] + fp["grid"] + fp["hold"] - hg
    tick_named = defaultdict(lambda: np.zeros(n_d))
    for d in range(n_d):
        for t in L.tix[d]:
            tick_named[t[7] if t[7] in named else "quartet"][d] += t[4]
    for c in named | {"quartet"}:
        exp = exp + (fp[c] if c in named else 0.0) - tick_named[c] if c != "quartet" else exp - tick_named[c]
    print(f"(3c) residual against its parts (legs' file less tickets, quartet file less its tickets, hold+grid file less "
          f"hourly): max abs diff {np.abs(exp - res).max():.2e}")
    print(f"     the residual itself: max abs {100 * np.abs(res).max():.3f}% of equity at size 1, mean abs "
          f"{100 * np.abs(res).mean():.4f}%, days with |res| > 0.05% {int((np.abs(res) > 5e-4).sum())} of {n_d}")


def main():
    runs = scan_runs()
    print("tester runs found: " + ", ".join(f"{g}x {len(v)}" for g, v in runs.items()))
    a_gold, a_fx, a_oth, om = part1(runs)
    rt = SimpleNamespace(ag=a_gold, af=a_fx, ao=a_oth, om=om)
    b = build_bars()
    print("KNOWN LIMITATION (lesson 9): server hours 23 and 0 have no data in the hourly file, so no bar, panic, "
          "stop-out or grid action is modelled in them; a move there shows up only in the next bar's return")
    r = m.daily().reindex(b.days).fillna(0.0)
    E1, E7 = edge_set(b, r, 1.0), edge_set(b, r, 0.7)
    L = build_legs(b)
    attach_legs(E1, L)
    attach_legs(E7, L)
    print_legs(L, rt)
    part2_checks(b, E1, m.daily(), runs)
    part3a(E1, runs, rt)
    part3b({1.0: E1, 0.7: E7}, rt)
    part3c(E1, rt)
    part3d(E1, runs, rt)
    part4(E1, runs, rt, L, b)


if __name__ == "__main__":
    main()
