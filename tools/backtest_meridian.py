"""Backtest of AurumMeridian: sell EUR/USD through the European midday, close before New York starts.

Rule (London time, so the window moves by an hour on the server clock in the weeks when only the US has changed
its clocks):
  At --start (default 11:30 London = 13:30 server) the pair is sold, at --end (13:00 London = 15:00 server) it is
  bought back, or earlier at a stop --stop times the average size of the same window's move over the previous
  --days trading days. One trade a day on the weekdays in --weekdays, never held past the window.
  --side 1 buys instead (the dollar pairs quoted the other way round, USDCHF).
Size: --risk of the balance is lost when the stop is hit. Cost is --cost basis points of the price per round trip
(quoted spread about 0.25 plus commission about 0.6, the commission is an assumption). Bars are bid prices from
marketdata/histdata/<symbol>_M1.csv.gz: the stop of a short is checked against the bar high plus --spread.

Usage: python tools/backtest_meridian.py [--symbol EURUSD] [--start 690] [--end 780] [--stop 3] [--cost 0.85] [--grid]
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
_cache = {}


def _sunday(year, month, n):
    """The n-th Sunday of the month, n = -1 for the last one."""
    d = pd.Timestamp(year, month, 1) if n > 0 else pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    step = (6 - d.dayofweek) % 7 if n > 0 else -((d.dayofweek + 1) % 7)
    return d + pd.Timedelta(days=step + 7 * (n - 1 if n > 0 else 0))


def london_shift(day):
    """Minutes the server clock is ahead of London time, minus 120: 60 while only the US is on summer time."""
    us = _sunday(day.year, 3, 2) <= day < _sunday(day.year, 11, 1)
    uk = _sunday(day.year, 3, -1) <= day < _sunday(day.year, 10, -1)
    return 60 * (int(us) - int(uk))


def _tables(symbol):
    """Open, high, low, close of every 1-minute bar, one row per day and one column per minute of the day."""
    if symbol not in _cache:
        m = pd.read_csv(DATA / f"{symbol}_M1.csv.gz", usecols=["time", "open", "high", "low", "close"])
        t = pd.to_datetime(m.time, unit="s")
        day, mod = t.dt.normalize(), t.dt.hour * 60 + t.dt.minute
        T = {f: m.pivot_table(index=day, columns=mod, values=f, aggfunc="first").reindex(columns=range(1440))
             for f in ("open", "high", "low", "close")}
        T["last"] = T["close"].ffill(axis=1)
        T["shift"] = pd.Series([london_shift(d) for d in T["open"].index], index=T["open"].index)
        _cache[symbol] = T
    return _cache[symbol]


def trades(symbol="EURUSD", start=690, end=780, stop=3.0, days=60, cost=0.85, spread=0.25, side=-1,
           weekdays=(0, 1, 2, 3, 4), anchor="london"):
    """One row per trade: average move, net result in basis points and in units of the stop distance."""
    T = _tables(symbol)
    rows = []
    for d, sh in T["shift"].items():
        a = start + 120 + (sh if anchor == "london" else 0)
        b = a + end - start
        e = T["open"].at[d, a]
        if np.isnan(e) or np.isnan(T["last"].at[d, b - 1]):
            continue
        rows.append((d, a, b, e, 1e4 * (T["last"].at[d, b - 1] / e - 1)))
    w = pd.DataFrame(rows, columns=["day", "a", "b", "entry", "move"]).set_index("day")
    w["ref"] = w.move.abs().rolling(days, min_periods=days // 2).mean().shift(1)
    w = w[w.ref.notna() & np.isin(w.index.dayofweek, weekdays)]
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


def report(t, risk=0.01, label=""):
    ret = risk * t.r
    eq = (1 + ret).cumprod()
    years = (t.index[-1] - t.index[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    ts = lambda z: z.mean() / (z.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else 0.0
    h = t.index < pd.Timestamp("2018-01-01")
    yr = t.net.groupby(t.index.year).sum()
    print(f"{label}{len(t):4d} trades, win {100 * (t.net > 0).mean():2.0f}%, net {t.net.mean():+.2f} bp, "
          f"Sharpe {ret.mean() / ret.std() * np.sqrt(len(t) / years):4.2f}, t {ts(t.net):+.1f} (to 2017 {ts(t.net[h]):+.1f}, "
          f"from 2018 {ts(t.net[~h]):+.1f}), years won {(yr > 0).sum()}/{len(yr)}, CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):4.1f}%, "
          f"maxDD {100 * dd:4.1f}%, worst {100 * ret.min():+.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--start", type=int, default=690, help="entry, minutes after midnight London time")
    ap.add_argument("--end", type=int, default=780, help="exit, minutes after midnight London time")
    ap.add_argument("--stop", type=float, default=3.0, help="stop distance in average window moves, 0 = none")
    ap.add_argument("--days", type=int, default=60, help="days in the average")
    ap.add_argument("--risk", type=float, default=0.01, help="fraction of the balance lost at the stop")
    ap.add_argument("--cost", type=float, default=0.85, help="round-trip cost, basis points of the price")
    ap.add_argument("--side", type=int, default=-1, choices=(-1, 1), help="-1 sell, 1 buy")
    ap.add_argument("--weekdays", type=int, nargs="+", default=[0, 1, 2, 3, 4], help="0 = Monday ... 4 = Friday")
    ap.add_argument("--anchor", default="london", choices=("london", "server"), help="clock the window follows")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(symbol=a.symbol, start=a.start, end=a.end, stop=a.stop, days=a.days, cost=a.cost, side=a.side,
              weekdays=tuple(a.weekdays), anchor=a.anchor)
    if a.grid:
        var = lambda name, vals, fmt: [report(trades(**{**kw, name: v}), a.risk, f"{name} {format(v, fmt):>6s} | ") for v in vals]
        var("cost", (0.0, 0.5, 0.85, 1.2, 1.6), ".2f")
        var("stop", (0.0, 1.0, 2.0, 3.0, 5.0), ".1f")
        var("days", (20, 60, 120), "d")
        var("anchor", ("london", "server"), "s")
        for wd in ((0,), (1,), (2,), (3,), (4,), (1, 2, 3, 4), (2, 3, 4)):
            report(trades(**{**kw, "weekdays": wd}), a.risk, f"weekdays {''.join(map(str, wd)):>5s} | ")
        print("other windows (London time):")
        for s, e in ((630, 780), (660, 780), (690, 780), (720, 780), (750, 780), (690, 750), (690, 775), (690, 785), (690, 810),
                     (700, 790), (600, 690), (780, 870)):
            report(trades(**{**kw, "start": s, "end": e}), a.risk, f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d} | ")
    else:
        t = trades(**kw)
        report(t, a.risk)
        y = t.groupby(t.index.year).agg(n=("net", "size"), net=("net", "mean"), r=("r", lambda z: 100 * ((1 + a.risk * z).prod() - 1)))
        print("by year (trades, net bp, %):", "  ".join(f"{k}: {int(v.n)} {v.net:+.2f} {v.r:+.1f}" for k, v in y.iterrows()))
        mth = (1 + a.risk * t.r).groupby([t.index.year, t.index.month]).prod() - 1
        print(f"months won {100 * (mth > 0).mean():.0f}% of {len(mth)}, worst month {100 * mth.min():+.1f}%, "
              f"average move {t.ref.iloc[-60:].mean():.1f} bp lately")
