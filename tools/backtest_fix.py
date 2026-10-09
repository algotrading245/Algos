"""Backtest of AurumFix on real XAUUSD.pc M5 bars.

Rule: every weekday sell at --entry London time and buy back at --exit London time (defaults 10:20 and 10:35, around
the 10:30 LBMA morning auction). The server clock follows US daylight saving (GMT+2 / GMT+3) and London follows UK
daylight saving, so the server time of the trade is London + 2 h, or + 3 h in the weeks when only the US is on summer
time. Optional protective stop a fixed percentage above entry, checked on M5 highs (filled at the stop, or at the bar
open if it gapped). Cost is charged per round trip in price units.

Usage: python tools/backtest_fix.py [--entry 10:20] [--exit 10:35] [--stop 0.3] [--lev 3] [--cost 0.20] [--grid]
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd


def _nth_sunday(year, month, n):
    """Day of month of the n-th Sunday (n = -1 for the last one)."""
    days = pd.date_range(f"{year}-{month:02d}-01", periods=31)
    sundays = [x.day for x in days if x.month == month and x.dayofweek == 6]
    return sundays[n - 1] if n > 0 else sundays[-1]


def london_shift(day):
    """Hours to add to London time to get server time on this date."""
    y = day.year
    us = pd.Timestamp(y, 3, _nth_sunday(y, 3, 2)) <= day < pd.Timestamp(y, 11, _nth_sunday(y, 11, 1))
    uk = pd.Timestamp(y, 3, _nth_sunday(y, 3, -1)) <= day < pd.Timestamp(y, 10, _nth_sunday(y, 10, -1))
    return (3 if us else 2) - (1 if uk else 0)


def trades(entry="10:20", exit_="10:35", stop_pct=0.3, cost=0.20, dst=True):
    d = rd.bars("M5").reset_index(drop=True)
    d["date"] = d.dt.dt.normalize()
    e, x = pd.Timedelta(entry + ":00"), pd.Timedelta(exit_ + ":00")
    rows = []
    for day, g in d.groupby("date"):
        sh = pd.Timedelta(hours=london_shift(day) if dst else 2)
        g = g.set_index("dt")
        t0, t1 = day + e + sh, day + x + sh
        if t0 not in g.index or t1 not in g.index:
            continue
        ep, xp = g.open[t0], g.open[t1]
        if stop_pct > 0:
            sl = ep * (1 + stop_pct / 100)
            w = g.loc[t0:t1 - pd.Timedelta(minutes=5)]
            hit = w[w.high >= sl]
            if len(hit):
                xp = max(sl, hit.open.iloc[0])
        rows.append((t0, ep, xp, (ep - xp - cost) / ep))
    return pd.DataFrame(rows, columns=["dt", "entry", "exit", "ret"])


def report(t, lev, label=""):
    eq = (1 + t.ret * lev).cumprod()
    years = (t.dt.iloc[-1] - t.dt.iloc[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    h = int(len(t) * 0.6)
    ts = lambda z: z.mean() / z.std() * np.sqrt(len(z))
    print(f"{label}lev {lev:g}x: trades {len(t)} ({len(t) / years:.0f}/yr), win {100 * (t.ret > 0).mean():.0f}%, "
          f"mean {1e4 * t.ret.mean():+.2f} bp (t {ts(t.ret):+.1f}; first 60% {ts(t.ret.iloc[:h]):+.1f}, last 40% {ts(t.ret.iloc[h:]):+.1f}), "
          f"CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):.1f}%, Sharpe {t.ret.mean() / t.ret.std() * np.sqrt(252):.2f}, "
          f"maxDD {100 * dd:.1f}%, worst trade {100 * lev * t.ret.min():.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="10:20", help="entry, London time HH:MM (multiple of 5 minutes)")
    ap.add_argument("--exit", default="10:35", help="exit, London time HH:MM (multiple of 5 minutes)")
    ap.add_argument("--stop", type=float, default=0.3, help="protective stop, percent above entry (0 = none)")
    ap.add_argument("--lev", type=float, default=3.0, help="position notional as a multiple of equity")
    ap.add_argument("--cost", type=float, default=0.20, help="round-trip cost, price units per oz")
    ap.add_argument("--grid", action="store_true", help="print an entry x exit x stop grid instead of one run")
    a = ap.parse_args()
    if a.grid:
        for en in ("10:10", "10:15", "10:20", "10:25"):
            for ex in ("10:30", "10:35", "10:40", "10:45"):
                for stop in (0.0, 0.15, 0.3):
                    report(trades(en, ex, stop, a.cost), a.lev, f"{en}-{ex} stop {stop:.2f}% | ")
        report(trades("10:20", "10:35", 0.3, a.cost, dst=False), a.lev, "10:20-10:35 stop 0.30%, fixed server +2 h | ")
        for c in (0.30, 0.50, 1.00):
            report(trades("10:20", "10:35", 0.3, c), a.lev, f"10:20-10:35 stop 0.30%, cost {c:.2f} | ")
    else:
        t = trades(a.entry, a.exit, a.stop, a.cost)
        report(t, a.lev)
        m = t.groupby([t.dt.dt.year, t.dt.dt.month]).ret.agg(["count", "mean", "sum"])
        print(m.assign(mean=1e4 * m["mean"], sum=100 * a.lev * m["sum"]).round(2).rename(columns={"mean": "mean_bp", "sum": "sum_pct"}).to_string())
