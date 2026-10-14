"""Backtest of AurumTokyo: sell USD/JPY at the Tokyo 9:55 fixing, buy it back --hold minutes later.

Rule (Tokyo time; Japan keeps one clock all year, so the fixing is at 02:55 server time while the US is on winter
time and at 03:55 while it is on summer time):
  --delay minutes after 9:55 the pair is sold, --hold minutes after 9:55 it is bought back, or earlier at a stop
  --stop times the average size of the same window's move over the previous --days trading days. One trade a day
  on the weekdays in --weekdays. --gotobi 1 trades only the settlement days (dates divisible by five, or the
  Friday before when that date is on a weekend), --gotobi -1 only the other days.
  --pre M buys M minutes before the fixing and sells at the fixing instead (the run-up, the other half of the
  pattern).
Size: --risk of the balance is lost when the stop is hit. Cost is --cost basis points of the price per round trip
(quoted spread about 0.27 plus commission about 0.6, the commission is an assumption). Bars are bid prices from
marketdata/histdata/USDJPY_M1.csv.gz: the stop of a short is checked against the bar high plus --spread.

Usage: python tools/backtest_tokyo.py [--hold 90] [--delay 0] [--stop 3] [--cost 0.85] [--gotobi 1] [--grid]
"""
import argparse
import numpy as np
import pandas as pd
from backtest_meridian import _tables, _sunday, report


def fix_minute(day):
    """Server minute of the day of 9:55 Tokyo time."""
    return 175 + 60 * int(_sunday(day.year, 3, 2) <= day < _sunday(day.year, 11, 1))


def gotobi(day):
    """True on a settlement day: date divisible by five, or the Friday before one that falls on a weekend."""
    return day.day % 5 == 0 or (day.dayofweek == 4 and ((day.day + 1) % 5 == 0 or (day.day + 2) % 5 == 0))


def trades(symbol="USDJPY", hold=90, delay=0, stop=3.0, days=60, cost=0.85, spread=0.27, pre=0, got=0,
           weekdays=(0, 1, 2, 3, 4)):
    """One row per trade: average move, net result in basis points and in units of the stop distance."""
    T = _tables(symbol)
    side = 1 if pre > 0 else -1
    rows = []
    for d in T["open"].index:
        f = fix_minute(d)
        a, b = (f - pre, f) if pre > 0 else (f + delay, f + hold)
        e = T["open"].at[d, a]
        if np.isnan(e) or np.isnan(T["last"].at[d, b - 1]) or T["open"].loc[d, a:b - 1].isna().mean() > 0.5:
            continue
        rows.append((d, a, b, e, 1e4 * (T["last"].at[d, b - 1] / e - 1), gotobi(d)))
    w = pd.DataFrame(rows, columns=["day", "a", "b", "entry", "move", "gotobi"]).set_index("day")
    w["ref"] = w.move.abs().rolling(days, min_periods=days // 2).mean().shift(1)
    w = w[w.ref.notna() & np.isin(w.index.dayofweek, weekdays) & ((got == 0) | (w.gotobi == (got > 0)))]
    out = []
    for d, x in w.iterrows():
        res = side * x.move
        if stop > 0:
            a, b = int(x.a), int(x.b)
            hi, lo = T["high"].loc[d, a:b - 1].to_numpy(), T["low"].loc[d, a:b - 1].to_numpy()
            adv = 1e4 * (np.nanmax(hi) / x.entry - 1) + spread if side < 0 else -1e4 * (np.nanmin(lo) / x.entry - 1)
            if adv >= stop * x.ref:
                res = -stop * x.ref
        out.append(res - cost)
    w["net"] = out
    w["r"] = w.net / ((stop if stop > 0 else 3.0) * w.ref)
    return w


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="USDJPY")
    ap.add_argument("--hold", type=int, default=90, help="exit, minutes after 9:55 Tokyo time")
    ap.add_argument("--delay", type=int, default=0, help="entry, minutes after 9:55 Tokyo time")
    ap.add_argument("--pre", type=int, default=0, help="buy this many minutes before the fixing and sell at it instead")
    ap.add_argument("--stop", type=float, default=3.0, help="stop distance in average window moves, 0 = none")
    ap.add_argument("--days", type=int, default=60, help="days in the average")
    ap.add_argument("--risk", type=float, default=0.01, help="fraction of the balance lost at the stop")
    ap.add_argument("--cost", type=float, default=0.85, help="round-trip cost, basis points of the price")
    ap.add_argument("--gotobi", type=int, default=1, choices=(-1, 0, 1), help="1 settlement days only, -1 the others, 0 all")
    ap.add_argument("--weekdays", type=int, nargs="+", default=[0, 1, 2, 3, 4], help="0 = Monday ... 4 = Friday")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(symbol=a.symbol, hold=a.hold, delay=a.delay, pre=a.pre, stop=a.stop, days=a.days, cost=a.cost,
              got=a.gotobi, weekdays=tuple(a.weekdays))
    if a.grid:
        var = lambda name, vals, fmt: [report(trades(**{**kw, name: v}), a.risk, f"{name} {format(v, fmt):>6s} | ") for v in vals]
        var("cost", (0.0, 0.5, 0.85, 1.2, 1.6), ".2f")
        var("hold", (15, 30, 60, 90, 120, 180, 240), "d")
        var("delay", (0, 1, 2, 5, 10), "d")
        var("stop", (0.0, 1.0, 2.0, 3.0, 5.0), ".1f")
        var("days", (20, 60, 120), "d")
        var("got", (-1, 0, 1), "d")
        for wd in ((0,), (1,), (2,), (3,), (4,), (0, 3, 4), (3, 4)):
            report(trades(**{**kw, "weekdays": wd}), a.risk, f"weekdays {''.join(map(str, wd)):>5s} | ")
        print("the run-up, bought before the fixing and sold at it:")
        for p in (15, 30, 60):
            report(trades(**{**kw, "pre": p}), a.risk, f"pre {p:6d} | ")
    else:
        t = trades(**kw)
        report(t, a.risk)
        y = t.groupby(t.index.year).agg(n=("net", "size"), net=("net", "mean"), r=("r", lambda z: 100 * ((1 + a.risk * z).prod() - 1)))
        print("by year (trades, net bp, %):", "  ".join(f"{k}: {int(v.n)} {v.net:+.2f} {v.r:+.1f}" for k, v in y.iterrows()))
        mth = (1 + a.risk * t.r).groupby([t.index.year, t.index.month]).prod() - 1
        print(f"months won {100 * (mth > 0).mean():.0f}% of {len(mth)}, worst month {100 * mth.min():+.1f}%, "
              f"average move {t.ref.iloc[-60:].mean():.1f} bp lately")
