"""Backtest of AurumBell: fade gold's last move into the New York 16:00 close.

Rule (server time, 23:00 = 16:00 New York all year):
  At the open of the 1-minute bar at --at (default 23:00) the move over the last --look minutes is measured. When it
  is at least --k times the average size of the same move over the previous --days trading days, a position is
  opened against it: sell after a rise, buy after a fall. It is closed --hold minutes later, or earlier at a stop
  --stop times that average away from the entry. One trade a day at most, never held overnight.
Size: --risk of the balance is lost when the stop is hit. Cost is --cost price units per round trip. Bars are bid
prices: the stop of a short is checked against the bar high plus --spread.

Usage: python tools/backtest_bell.py [--look 15] [--hold 10] [--k 1.5] [--stop 3] [--risk 0.01] [--cost 0.17] [--grid]
"""
import argparse
import sys
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
        _cache["last"] = _cache["close"].ffill(axis=1)
    return _cache


def trades(at=1380, look=15, hold=10, k=1.5, stop=3.0, days=60, cost=0.17, spread=0.11, delay=0):
    """One row per trade: side, average move, net result per oz and in units of the stop distance."""
    T = _tables()
    entry = T["open"][at + delay]
    sig = (T["open"][at] - T["last"][at - look - 1]).where(entry.notna()).dropna()
    ref = sig.abs().rolling(days, min_periods=days // 2).mean().shift(1)
    rows = []
    for d in sig.index[(sig.abs() >= k * ref) & (sig.abs() > 0)]:
        s, r, e = -np.sign(sig[d]), ref[d], entry[d]
        x = np.nan
        for t in range(at + delay, at + hold):
            hi, lo = T["high"].at[d, t], T["low"].at[d, t]
            if np.isnan(hi):
                continue
            if stop > 0 and (lo <= e - stop * r if s > 0 else hi + spread >= e + stop * r):
                x = e - s * stop * r
                break
        if np.isnan(x):
            x = T["last"].at[d, at + hold - 1]
        rows.append((d, s, r, s * (x - e) - cost))
    t = pd.DataFrame(rows, columns=["day", "side", "ref", "net"]).set_index("day")
    t["r"] = t.net / (stop * t.ref) if stop > 0 else t.net / (3 * t.ref)
    return t


def report(t, risk=0.01, label=""):
    if len(t) < 10:
        print(f"{label}{len(t)} trades")
        return
    ret = risk * t.r
    eq = (1 + ret).cumprod()
    years = (t.index[-1] - t.index[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    ts = lambda z: z.mean() / (z.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else 0.0
    h = t.index < pd.Timestamp("2018-01-01")
    pf = t.net[t.net > 0].sum() / max(-t.net[t.net < 0].sum(), 1e-9)
    print(f"{label}{len(t):4d} trades ({len(t) / years:3.0f}/yr), win {100 * (t.net > 0).mean():2.0f}%, net/oz {t.net.mean():+.2f}, "
          f"PF {pf:.2f}, t {ts(t.net):+.1f} (to 2017 {ts(t.net[h]):+.1f}, from 2018 {ts(t.net[~h]):+.1f}), "
          f"CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):4.1f}%, maxDD {100 * dd:4.1f}%, worst {100 * ret.min():+.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", type=int, default=1380, help="decision time, minutes after midnight server time")
    ap.add_argument("--look", type=int, default=15, help="the move is measured over this many minutes")
    ap.add_argument("--hold", type=int, default=10, help="holding time, minutes")
    ap.add_argument("--k", type=float, default=1.5, help="trade when the move is at least k times its average size")
    ap.add_argument("--stop", type=float, default=3.0, help="stop distance in average moves, 0 = none")
    ap.add_argument("--days", type=int, default=60, help="days in the average")
    ap.add_argument("--risk", type=float, default=0.01, help="fraction of the balance lost at the stop")
    ap.add_argument("--cost", type=float, default=0.17, help="round-trip cost, price units per oz")
    ap.add_argument("--delay", type=int, default=0, help="enter this many minutes late")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(at=a.at, look=a.look, hold=a.hold, k=a.k, stop=a.stop, days=a.days, cost=a.cost, delay=a.delay)
    if a.grid:
        var = lambda name, vals, fmt: [report(trades(**{**kw, name: v}), a.risk, f"{name} {format(v, fmt):>5s} | ") for v in vals]
        var("cost", (0.0, 0.17, 0.25, 0.35, 0.50), ".2f")
        var("look", (5, 10, 15, 20, 30, 60), "d")
        var("hold", (2, 5, 10, 15, 20, 30, 58), "d")
        var("k", (0.0, 0.5, 1.0, 1.5, 2.0, 3.0), ".1f")
        var("stop", (0.0, 1.0, 2.0, 3.0, 5.0), ".1f")
        var("days", (20, 60, 120), "d")
        var("delay", (0, 1, 2), "d")
        print("the same rule at other times of the day:")
        var("at", (600, 900, 1020, 1140, 1260, 1320, 1350, 1365, 1380, 1395), "d")
    else:
        t = trades(**kw)
        report(t, a.risk)
        y = t.groupby(t.index.year).agg(n=("net", "size"), net=("net", "mean"), r=("r", lambda z: 100 * ((1 + a.risk * z).prod() - 1)))
        print("by year (trades, net/oz, %):", "  ".join(f"{k}: {int(v.n)} {v.net:+.2f} {v.r:+.1f}" for k, v in y.iterrows()))
        print(f"long {int((t.side > 0).sum())} trades net/oz {t.net[t.side > 0].mean():+.2f}, "
              f"short {int((t.side < 0).sum())} trades net/oz {t.net[t.side < 0].mean():+.2f}, "
              f"average move {t.ref.iloc[-60:].mean():.2f} lately")
