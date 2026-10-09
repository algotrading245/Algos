"""Backtest of AurumRebound on real XAUUSD.pc M15 bars.

Rule: when an M15 bar that opened between --h0 and --h1 (server hours) closes with a log return below -thr times the
standard deviation of the previous --win M15 returns, buy at the next bar open and close after --hold bars. One
position at a time. Optional protective stop a fixed percentage below entry, checked on bar lows (filled at the stop,
or at the bar open if it gapped). Cost is charged per round trip in price units.

Usage: python tools/backtest_rebound.py [--thr 3] [--hold 4] [--stop 0] [--lev 3] [--cost 0.20] [--grid]
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd


def trades(thr=3.0, hold=4, stop_pct=0.0, cost=0.20, h0=1, h1=8, win=96):
    d = rd.bars("M15").reset_index(drop=True)
    o, lo, c = d.open.to_numpy(), d.low.to_numpy(), d.close.to_numpy()
    lr = pd.Series(np.log(c)).diff()
    z = (lr / lr.rolling(win).std().shift(1)).to_numpy()
    hour = d.dt.dt.hour.to_numpy()
    date = d.dt.dt.date.to_numpy()
    rows, nxt = [], 0
    for i in np.flatnonzero((z <= -thr) & (hour >= h0) & (hour <= h1)):
        if i < nxt or i + 1 + hold >= len(d) or date[i + 1 + hold] != date[i]:
            continue
        ep, xp = o[i + 1], o[i + 1 + hold]
        if stop_pct > 0:
            sl = ep * (1 - stop_pct / 100)
            for k in range(i + 1, i + 1 + hold):
                if lo[k] <= sl:
                    xp = min(sl, o[k])
                    break
        rows.append((d.dt.iloc[i + 1], ep, xp, (xp - ep - cost) / ep))
        nxt = i + 1 + hold
    return pd.DataFrame(rows, columns=["dt", "entry", "exit", "ret"])


def report(t, lev, label=""):
    daily = (t.set_index("dt").ret * lev).resample("D").sum()
    daily = daily[daily.index.dayofweek < 5]
    eq = (1 + t.ret * lev).cumprod()
    years = (t.dt.iloc[-1] - t.dt.iloc[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    h = int(len(t) * 0.6)
    ts = lambda z: z.mean() / z.std() * np.sqrt(len(z))
    print(f"{label}lev {lev:g}x: trades {len(t)} ({len(t) / years:.0f}/yr), win {100 * (t.ret > 0).mean():.0f}%, "
          f"mean {1e4 * t.ret.mean():+.2f} bp (t {ts(t.ret):+.1f}; first 60% {ts(t.ret.iloc[:h]):+.1f}, last 40% {ts(t.ret.iloc[h:]):+.1f}), "
          f"CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):.1f}%, Sharpe {daily.mean() / daily.std() * np.sqrt(252):.2f}, "
          f"maxDD {100 * dd:.1f}%, worst trade {100 * lev * t.ret.min():.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--thr", type=float, default=3.0, help="shock size in standard deviations")
    ap.add_argument("--hold", type=int, default=4, help="hold, M15 bars")
    ap.add_argument("--stop", type=float, default=0.0, help="protective stop, percent below entry (0 = none)")
    ap.add_argument("--lev", type=float, default=3.0, help="position notional as a multiple of equity")
    ap.add_argument("--cost", type=float, default=0.20, help="round-trip cost, price units per oz")
    ap.add_argument("--grid", action="store_true", help="print a threshold x hold x stop grid instead of one run")
    a = ap.parse_args()
    if a.grid:
        for thr in (2.5, 3.0, 3.5, 4.0):
            for hold in (2, 4, 8, 16):
                for stop in (0.0, 0.5, 1.0):
                    report(trades(thr, hold, stop, a.cost), a.lev, f"thr {thr} hold {hold:2d} stop {stop:.1f}% | ")
    else:
        t = trades(a.thr, a.hold, a.stop, a.cost)
        report(t, a.lev)
        print(t.groupby(t.dt.dt.year).ret.agg(["count", "mean", "sum"]).assign(mean=lambda x: 1e4 * x["mean"], sum=lambda x: 100 * a.lev * x["sum"]).round(2)
              .rename(columns={"mean": "mean_bp", "sum": "sum_pct"}).to_string())
