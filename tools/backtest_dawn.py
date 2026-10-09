"""Backtest of AurumDawn on real XAUUSD.pc M15 bars.

Rule: buy at the first price of the trading day (01:00 server time), close after a fixed hold. Optional protective
stop a fixed percentage below entry, checked on bar lows (filled at the stop, or at the bar open if it gapped).
Lot size keeps the position notional at a fixed multiple of equity. Cost is charged per round trip in price units.

Usage: python tools/backtest_dawn.py [--hold 120] [--stop 0] [--lev 3] [--cost 0.25]
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd


def trades(hold_min=120, stop_pct=0.0, cost=0.25, entry="01:00", skip_days=()):
    d = rd.bars("M15").reset_index(drop=True)
    d["date"] = d.dt.dt.date
    rows = []
    nb = hold_min // 15
    for date, g in d.groupby("date", sort=True):
        g = g[g.dt.dt.strftime("%H:%M") >= entry].reset_index(drop=True)
        if not len(g) or g.dt.iloc[0].strftime("%H:%M") != entry or len(g) <= nb or g.dt.iloc[0].weekday() in skip_days:
            continue
        if (g.dt.iloc[nb] - g.dt.iloc[0]).total_seconds() != hold_min * 60:      # gap inside the hold
            continue
        ep = g.open.iloc[0]
        xp = g.open.iloc[nb]
        if stop_pct > 0:
            sl = ep * (1 - stop_pct / 100)
            for k in range(nb):
                if g.low.iloc[k] <= sl:
                    xp = min(sl, g.open.iloc[k])
                    break
        rows.append((g.dt.iloc[0], ep, xp, (xp - ep - cost) / ep))
    return pd.DataFrame(rows, columns=["dt", "entry", "exit", "ret"])


def report(t, lev, label=""):
    r = t.ret * lev
    eq = (1 + r).cumprod()
    years = (t.dt.iloc[-1] - t.dt.iloc[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    h = int(len(t) * 0.6)
    sh = lambda z: z.mean() / z.std() * np.sqrt(252)
    print(f"{label}lev {lev:g}x: trades {len(t)}, win {100 * (r > 0).mean():.0f}%, mean {1e4 * t.ret.mean():+.2f} bp "
          f"(t {t.ret.mean() / t.ret.std() * np.sqrt(len(t)):+.1f}), CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):.1f}%, "
          f"Sharpe {sh(r):.2f} (first 60% {sh(r.iloc[:h]):.2f}, last 40% {sh(r.iloc[h:]):.2f}), maxDD {100 * dd:.1f}%, "
          f"worst day {100 * r.min():.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=120)
    ap.add_argument("--stop", type=float, default=0.0, help="protective stop, percent below entry (0 = none)")
    ap.add_argument("--lev", type=float, default=3.0, help="position notional as a multiple of equity")
    ap.add_argument("--cost", type=float, default=0.25, help="round-trip cost, price units per oz")
    ap.add_argument("--grid", action="store_true", help="print a hold x stop x cost grid instead of one run")
    a = ap.parse_args()
    if a.grid:
        for hold in (60, 120, 180, 240, 360):
            for stop in (0.0, 0.5, 1.0):
                for cost in (0.25, 0.50):
                    report(trades(hold, stop, cost), a.lev, f"hold {hold:3d}m stop {stop:.1f}% cost {cost:.2f} | ")
    else:
        t = trades(a.hold, a.stop, a.cost)
        report(t, a.lev)
        print(t.groupby(t.dt.dt.year).ret.agg(["count", "mean", "sum"]).assign(mean=lambda x: 1e4 * x["mean"], sum=lambda x: 100 * a.lev * x["sum"]).round(2)
              .rename(columns={"mean": "mean_bp", "sum": "sum_pct"}).to_string())
