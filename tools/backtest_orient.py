"""Backtest of AurumOrient: long gold through the Asian session, with an extra unit after a sharp dip.

Rule (server time, the day reopens at 01:00):
  base  buy at the open of the M5 bar at --entry (default 01:05, after the reopening spread has narrowed) and close
        at the open of the bar at --exit (default 09:00). Every trading day, never held overnight, so no swap.
  dip   when an M15 bar that opened between --d0 and --d1 closes with a log return below -thr times the standard
        deviation of the previous --win M15 returns, buy one more unit at the next bar open and close it after
        --hold bars (or at the day's last bar). One dip position at a time.
Size: each unit is leverage = min(--cap, --target / vol), vol = exponentially weighted (span --span) standard
deviation of daily returns up to yesterday, annualised. Cost is --bp basis points per round trip, and never less than
--cost price units.

Usage: python tools/backtest_orient.py [--entry 105] [--exit 900] [--thr 3] [--hold 16] [--target 0.30] [--cap 4]
                                       [--bp 1.0] [--cost 0.0] [--grid]
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd

_cache = {}


def _bars(tf):
    if tf not in _cache:
        _cache[tf] = rd.bars(tf).reset_index(drop=True)
    return _cache[tf]


def base(entry=105, exit=900, bp=1.0, cost=0.0):
    """Daily return of the session position, net of cost, per unit of leverage."""
    d = _bars("M5")
    hm = d.dt.dt.hour * 100 + d.dt.dt.minute
    p = d[hm.isin([entry, exit])].pivot_table(index=d.dt.dt.normalize(), columns=hm, values="open", aggfunc="first").dropna()
    return (p[exit] - p[entry] - np.maximum(cost, bp * 1e-4 * p[entry])) / p[entry]


def dips(thr=3.0, hold=16, d0=115, d1=745, win=96, bp=1.0, cost=0.0):
    """One row per dip trade: entry time and net return per unit of leverage."""
    d = _bars("M15")
    o, c = d.open.to_numpy(), d.close.to_numpy()
    lr = pd.Series(np.log(c)).diff()
    z = (lr / lr.rolling(win).std().shift(1)).to_numpy()
    hm = (d.dt.dt.hour * 100 + d.dt.dt.minute).to_numpy()
    day = d.dt.dt.normalize().to_numpy()
    rows, nxt = [], 0
    for i in np.flatnonzero((z <= -thr) & (hm >= d0) & (hm <= d1)):
        if i < nxt or i + 1 >= len(d) or day[i + 1] != day[i]:
            continue
        e = i + 1
        x = e + hold
        last = e + np.searchsorted(day[e:], day[e], side="right") - 1       # last bar of the entry day
        xp = o[x] if x <= last else c[last]
        rows.append((d.dt[e], (xp - o[e] - max(cost, bp * 1e-4 * o[e])) / o[e]))
        nxt = min(x, last + 1)
    return pd.DataFrame(rows, columns=["dt", "ret"])


def run(entry=105, exit=900, thr=3.0, hold=16, d0=115, d1=745, target=0.30, cap=4.0, span=30, bp=1.0, cost=0.0,
        use_base=True, use_dip=True):
    b = base(entry, exit, bp, cost)
    t = dips(thr, hold, d0, d1, bp=bp, cost=cost)
    dip = t.groupby(t.dt.dt.normalize()).ret.sum().reindex(b.index).fillna(0.0)
    D = _bars("D1")
    vol = (D.close.pct_change().ewm(span=span).std() * np.sqrt(252)).shift(1)
    vol.index = D.dt.dt.normalize()
    lev = (target / vol.reindex(b.index)).clip(upper=cap)
    out = pd.DataFrame({"lev": lev, "base": b * use_base, "dip": dip * use_dip}).dropna().iloc[2 * span:]
    out["ret"] = out.lev * (out.base + out.dip)
    return out, len(t)


def report(t, label=""):
    eq = (1 + t.ret).cumprod()
    years = (t.index[-1] - t.index[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    k = int(len(t) * 0.6)
    sh = lambda z: z.mean() / z.std() * np.sqrt(252)
    era = pd.cut(t.index.year, [2008, 2013, 2018, 2022, 2030])
    eras = " ".join(f"{sh(g):+.2f}" for _, g in t.ret.groupby(era, observed=True))
    print(f"{label}CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):5.1f}%, Sharpe {sh(t.ret):.2f} (first 60% {sh(t.ret.iloc[:k]):.2f}, "
          f"last 40% {sh(t.ret.iloc[k:]):.2f}; by era {eras}), maxDD {100 * dd:4.1f}%, worst day {100 * t.ret.min():+.1f}%, "
          f"mean leverage {t.lev.mean():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", type=int, default=105, help="session entry, HHMM server time")
    ap.add_argument("--exit", type=int, default=900, help="session exit, HHMM server time")
    ap.add_argument("--thr", type=float, default=3.0, help="dip threshold in standard deviations")
    ap.add_argument("--hold", type=int, default=16, help="dip holding time, M15 bars")
    ap.add_argument("--target", type=float, default=0.30, help="annual volatility of gold that one unit is scaled to")
    ap.add_argument("--cap", type=float, default=4.0, help="maximum leverage per unit")
    ap.add_argument("--bp", type=float, default=1.0, help="round-trip cost, basis points of price")
    ap.add_argument("--cost", type=float, default=0.0, help="minimum round-trip cost, price units per oz")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(target=a.target, cap=a.cap)
    if a.grid:
        for bp in (0.0, 0.6, 1.0, 1.5, 2.0):
            report(run(bp=bp, **kw)[0], f"cost {bp:.1f} bp                  | ")
        report(run(bp=0.0, cost=0.25, **kw)[0], "cost fixed 0.25              | ")
        report(run(bp=a.bp, use_dip=False, **kw)[0], "session only                 | ")
        report(run(bp=a.bp, use_base=False, **kw)[0], "dip only                     | ")
        for entry in (100, 110, 115, 130, 200):
            report(run(entry=entry, bp=a.bp, **kw)[0], f"entry {entry:04d}                   | ")
        for exit in (700, 800, 1000, 1100, 1200):
            report(run(exit=exit, bp=a.bp, **kw)[0], f"exit {exit:04d}                    | ")
        for thr in (2.0, 2.5, 3.5):
            report(run(thr=thr, bp=a.bp, **kw)[0], f"dip threshold {thr:.1f}            | ")
        for hold in (8, 12, 24):
            report(run(hold=hold, bp=a.bp, **kw)[0], f"dip hold {hold:2d} bars             | ")
        report(run(d1=345, bp=a.bp, **kw)[0], "dip window to 03:45          | ")
        report(run(bp=a.bp, target=a.target / 2, cap=a.cap / 2)[0], "half size                    | ")
    else:
        t, n = run(a.entry, a.exit, a.thr, a.hold, target=a.target, cap=a.cap, bp=a.bp, cost=a.cost)
        report(t)
        print(f"dip trades {n}, session days {len(t)}")
        y = t.ret.groupby(t.index.year).apply(lambda z: 100 * ((1 + z).prod() - 1))
        print("by year (%):", " ".join(f"{k}:{v:+.1f}" for k, v in y.items()))
