"""Backtest of AurumLattice: a reverse grid around the price at the start of the session.

Rule (server time):
  At --start the price is taken as the anchor A. The step is g = --step times the average high-low range of the
  same window over the previous --days trading days. The position is always q units, where q is the number of
  whole steps the price has gone away from A (q > 0 above A, q < 0 below), at most --levels: one unit is bought
  each time the price reaches the next level above and sold again when it comes one step back, and the mirror
  below A (--side 1 trades only above A, --side -1 only below). A day that runs n steps one way earns g * n * (n - 1) / 2 per unit, every swing of one step and back
  loses g. When the day has lost --cap steps everything is closed and the day is over, and at --end everything
  is closed at the market.
  --fade turns the grid round (position -q, the classical grid that sells rises and buys falls); it then stops at
  level --levels + 1. It is here to show that the classical grid loses on the same data.
Size: the unit is chosen so that --cap steps are --risk of the balance (with --fade: the loss at the outer level).
Cost is --cost price units per round trip of one unit. Bars are bid prices; a 1-minute bar is walked open, low,
high, close when it closed up and open, high, low, close when it closed down. A level jumped over between two
bars is filled at the open of the new bar when that is the worse price.

Usage: python tools/backtest_lattice.py [--start 900] [--end 1380] [--step 0.4] [--levels 6] [--cap 6] [--side 0] [--grid]
"""
import argparse
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd

_cache = {}


def _tables():
    """Open, high, low, close of every 1-minute bar, one row per day and one column per minute of the day."""
    if not _cache:
        m = rd.bars("M1")
        day, mod = m.dt.dt.normalize(), m.dt.dt.hour * 60 + m.dt.dt.minute
        for f in ("open", "high", "low", "close"):
            _cache[f] = m.pivot_table(index=day, columns=mod, values=f, aggfunc="first").reindex(columns=range(1440))
    return _cache


def days(start=900, end=1380, step=0.4, levels=6, cap=6.0, ndays=60, cost=0.17, fade=False, side=0):
    """One row per day: step, round trips, net result per unit and in units of the risk."""
    T = _tables()
    O, H, L, C = (T[f].iloc[:, start:end].to_numpy() for f in ("open", "high", "low", "close"))
    idx = T["open"].index
    ok = ~np.isnan(O[:, 0]) & (np.isnan(O).mean(1) < 0.5)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                   # days without any bar in the window
        rng = pd.Series(np.where(ok, np.nanmax(H, 1) - np.nanmin(L, 1), np.nan), index=idx).dropna()
    ref = rng.rolling(ndays, min_periods=ndays // 2).mean().shift(1).reindex(idx).to_numpy()
    ok &= ref > 0
    O, H, L, C, idx, ref = O[ok], H[ok], L[ok], C[ok], idx[ok], ref[ok]
    n, A, g = len(idx), O[:, 0].copy(), step * ref
    sgn = -1.0 if fade else 1.0                                           # position = sgn * q
    risk = g * (levels * (levels + 1) / 2 if fade else cap)
    q, cash, cnt = np.zeros(n), np.zeros(n), np.zeros(n)
    live, last = np.ones(n, bool), A.copy()

    def close(m, p):
        cash[m] += sgn * q[m] * p[m]
        cnt[m] += np.abs(q[m])
        q[m] = 0
        live[m] = False

    def move(p, gap):
        """Walk every live day to price p, trading one unit at each level crossed."""
        nonlocal q
        m = live & ~np.isnan(p)
        x = np.where(m, (p - A) / g, 0.0)
        tgt = np.where(x > q, np.maximum(q, np.floor(x + 1e-9)), np.minimum(q, np.ceil(x - 1e-9)))
        tgt = np.where(m, np.clip(tgt, -levels if side <= 0 else 0, levels if side >= 0 else 0), q)
        k = tgt - q                                                       # levels q+1..tgt going up, q-1..tgt going down
        fill = A + np.where(k > 0, (q + 1 + tgt) / 2, (q - 1 + tgt) / 2) * g
        if gap:                                                           # jumped levels fill at the open when that is worse
            worse = (p > fill) == (sgn * k > 0)
            fill = np.where(worse, p, fill)
        cash[:] -= np.where(k != 0, sgn * k * fill, 0.0)
        cnt[:] += np.abs(k)
        q = tgt
        if fade:
            close(m & (np.abs(x) >= levels + 1), np.where(x > 0, np.maximum(A + (levels + 1) * g, p), np.minimum(A - (levels + 1) * g, p)))
        else:
            eq = cash + sgn * q * np.where(m, p, 0.0) - (cnt + np.abs(q)) * cost / 2
            close(m & (eq <= -cap * g), np.where(m, p, 0.0))

    for t in range(O.shape[1]):
        o, h, l, c = O[:, t], H[:, t], L[:, t], C[:, t]
        upbar = c >= o
        move(o, True)
        move(np.where(upbar, l, h), False)
        move(np.where(upbar, h, l), False)
        move(c, False)
        last = np.where(np.isnan(c), last, c)
    stopped = ~live
    close(live.copy(), last)
    d = pd.DataFrame({"g": g, "trades": cnt / 2, "net": cash - cnt * cost / 2, "stopped": stopped}, index=idx)
    d["r"] = d.net / risk
    return d


def report(d, risk=0.01, label=""):
    ret = risk * d.r
    eq = (1 + ret).cumprod()
    years = (d.index[-1] - d.index[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    ts = lambda z: z.mean() / (z.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else 0.0
    h = d.index < pd.Timestamp("2018-01-01")
    print(f"{label}{len(d):4d} days, {d.trades.sum() / years:4.0f} round trips/yr, days won {100 * (d.net > 0).mean():2.0f}%, "
          f"stopped {100 * d.stopped.mean():4.1f}%, t {ts(d.r):+.1f} (to 2017 {ts(d.r[h]):+.1f}, from 2018 {ts(d.r[~h]):+.1f}), "
          f"CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):5.1f}%, maxDD {100 * dd:4.1f}%, "
          f"worst day {100 * ret.min():+.1f}%, best {100 * ret.max():+.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=900, help="anchor time, minutes after midnight server time")
    ap.add_argument("--end", type=int, default=1380, help="everything is closed at this time")
    ap.add_argument("--step", type=float, default=0.4, help="grid step in average window ranges")
    ap.add_argument("--levels", type=int, default=6, help="levels on each side of the anchor")
    ap.add_argument("--cap", type=float, default=6.0, help="the day is over after losing this many steps")
    ap.add_argument("--days", type=int, default=60, help="days in the average range")
    ap.add_argument("--risk", type=float, default=0.01, help="fraction of the balance lost on a capped day")
    ap.add_argument("--cost", type=float, default=0.17, help="round-trip cost of one unit, price units")
    ap.add_argument("--side", type=int, default=0, choices=(-1, 0, 1), help="1 only above the anchor (long), -1 only below, 0 both")
    ap.add_argument("--fade", action="store_true", help="the classical grid: sell rises, buy falls")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(start=a.start, end=a.end, step=a.step, levels=a.levels, cap=a.cap, ndays=a.days, cost=a.cost, fade=a.fade, side=a.side)
    if a.grid:
        var = lambda name, vals, fmt: [report(days(**{**kw, name: v}), a.risk, f"{name} {format(v, fmt):>5s} | ") for v in vals]
        var("cost", (0.0, 0.17, 0.25, 0.35, 0.50), ".2f")
        var("step", (0.15, 0.25, 0.30, 0.40, 0.50, 0.60), ".2f")
        var("levels", (1, 2, 3, 4, 6, 10), "d")
        var("cap", (2, 3, 4, 6, 10, 99), "d")
        var("ndays", (20, 60, 120), "d")
        var("side", (-1, 0, 1), "d")
        print("other windows of the day:")
        for s, e in ((60, 480), (480, 900), (480, 1380), (780, 1380), (840, 1380), (900, 1380), (960, 1380), (900, 1260), (60, 1380)):
            report(days(**{**kw, "start": s, "end": e}), a.risk, f"{s:4d}-{e:4d} | ")
        print("the classical grid, same settings:")
        for s, e in ((60, 480), (480, 900), (900, 1380), (60, 1380)):
            report(days(**{**kw, "start": s, "end": e, "fade": True}), a.risk, f"{s:4d}-{e:4d} | ")
    else:
        d = days(**kw)
        report(d, a.risk)
        y = d.groupby(d.index.year).r.agg(lambda z: 100 * ((1 + a.risk * z).prod() - 1))
        print("by year, %:", "  ".join(f"{k}: {v:+.1f}" for k, v in y.items()))
        mth = (1 + a.risk * d.r).groupby([d.index.year, d.index.month]).prod() - 1
        print(f"months won {100 * (mth > 0).mean():.0f}% of {len(mth)}, worst month {100 * mth.min():+.1f}%, best "
              f"{100 * mth.max():+.1f}%, step {d.g.iloc[-60:].mean():.2f} lately")
