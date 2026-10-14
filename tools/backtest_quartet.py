"""Backtest of AurumQuartet: four unrelated session patterns on one account.

Legs (each is the rule of its own backtest, at that backtest's default settings):
  dip       buy gold after a sharp 15-minute fall in the Asian session      tools/backtest_orient.py
  bell      fade of gold's last 15 minutes into the New York close          tools/backtest_bell.py
  tokyo     short USD/JPY after the Tokyo 9:55 fixing on settlement days    tools/backtest_tokyo.py
  meridian  short EUR/USD through the European midday                       tools/backtest_meridian.py
  session   long gold through the whole Asian session; off by default: at real cost its Sharpe is 0.3 to 0.4
            since 2018, and it adds drawdown without adding to the Sharpe of the other four
Size: --dip and --session multiply a volatility target of 30% (leverage of a unit = size x min(4, 30% / gold's
volatility)); --bell, --tokyo and --meridian are the fraction of the balance lost at each leg's stop. The legs
trade at different hours, so the day's result is the sum. The defaults are each leg scaled to 8% annual
volatility on the years to 2017 only.
Prices: gold is the mid of the bid and ask bars built from histdata.com ticks (tools/build_tick_bars.py) and
pays --gold per oz a round trip at the bell and 0.05 more in the Asian session, where the spread is wider. The
currency pairs are bid bars and pay --fx basis points (quoted spread plus commission; the commission is an
assumption).

Usage: python tools/backtest_quartet.py [--dip 1.55] [--session 0] [--bell 0.027] [--tokyo 0.020]
                                        [--meridian 0.010] [--gold 0.17] [--fx 0.85] [--grid]
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

import backtest_bell as bb
import backtest_meridian as bm
import backtest_orient as bo
import backtest_tokyo as bt

START = "2009-09-01"
CUT = pd.Timestamp("2018-01-01")
LEGS = ("dip", "bell", "tokyo", "meridian", "session")
BA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata" / "XAUUSD_BA_M1.npz"
_cache = {}


def _gold_mid():
    """Hands the two gold backtests mid prices from the tick-built bid and ask bars instead of bid bars."""
    if bb._cache:
        return
    z = np.load(BA)
    ok = z["n"] >= 1
    m = pd.DataFrame({"time": z["time"][ok], **{f: (z["b" + f[0]][ok] + z["a" + f[0]][ok]) / 2
                                                for f in ("open", "high", "low", "close")}})
    m["dt"] = pd.to_datetime(m.time, unit="s")
    m = m[m.dt.dt.dayofweek < 5]
    for tf, s in (("M5", 300), ("M15", 900), ("D1", 86400)):
        g = m.assign(time=m.time // s * s).groupby("time").agg(open=("open", "first"), high=("high", "max"),
                                                              low=("low", "min"), close=("close", "last")).reset_index()
        g["dt"] = pd.to_datetime(g.time, unit="s")
        bo._cache[tf] = g
    day, mod = m.dt.dt.normalize(), m.dt.dt.hour * 60 + m.dt.dt.minute
    for f in ("open", "high", "low", "close"):
        bb._cache[f] = m.pivot_table(index=day, columns=mod, values=f, aggfunc="first").reindex(columns=range(1440))
    bb._cache["last"] = bb._cache["close"].ffill(axis=1)


def legs(fx=0.85, gold=0.17):
    """Daily result of each leg at unit size: the gold units at a 30% target, the others per unit of risk at the stop."""
    if (fx, gold) not in _cache:
        _gold_mid()
        d = {"dip": bo.run(bp=0.0, cost=gold + 0.05, use_base=False)[0].ret,
             "bell": bb.trades(cost=gold, spread=0.0).r, "tokyo": bt.trades(got=1, cost=fx).r,
             "meridian": bm.trades(cost=fx).r, "session": bo.run(bp=0.0, cost=gold + 0.05, use_dip=False)[0].ret}
        _cache[(fx, gold)] = pd.DataFrame(d).fillna(0.0).sort_index().loc[START:]
    return _cache[(fx, gold)]


def run(size, fx=0.85, gold=0.17):
    """Daily return of the account for the sizes in 'size' (leg name -> multiplier)."""
    D = legs(fx, gold)
    return sum(size.get(k, 0.0) * D[k] for k in LEGS)


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def report(r, label=""):
    eq = (1 + r).cumprod()
    years = (r.index[-1] - r.index[0]).days / 365.25
    h = r.index < CUT
    y = (1 + r).groupby(r.index.year).prod() - 1
    m = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    print(f"{label}CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):5.1f}%, Sharpe {sharpe(r):.2f} (to 2017 {sharpe(r[h]):.2f}, "
          f"from 2018 {sharpe(r[~h]):.2f}, from 2022 {sharpe(r[r.index >= pd.Timestamp('2022-01-01')]):.2f}), "
          f"vol {100 * r.std() * np.sqrt(252):4.1f}%, maxDD {100 * (1 - eq / eq.cummax()).max():4.1f}%, "
          f"worst day {100 * r.min():+.1f}%, worst year {100 * y.min():+.1f}%, years won {(y > 0).sum()}/{len(y)}, "
          f"months won {100 * (m > 0).mean():.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dip", type=float, default=1.55, help="multiplier on the gold dip unit's 30%% volatility target")
    ap.add_argument("--session", type=float, default=0.0, help="the same for the Asian session unit, 0 = off")
    ap.add_argument("--bell", type=float, default=0.027, help="closing bell leg: fraction of the balance lost at the stop")
    ap.add_argument("--tokyo", type=float, default=0.020, help="Tokyo fixing leg: fraction of the balance lost at the stop")
    ap.add_argument("--meridian", type=float, default=0.010, help="midday leg: fraction of the balance lost at the stop")
    ap.add_argument("--gold", type=float, default=0.17, help="round-trip cost of gold at the bell, price units per oz")
    ap.add_argument("--fx", type=float, default=0.85, help="round-trip cost of the currency legs, basis points")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    size = {k: getattr(a, k) for k in LEGS}
    D = legs(a.fx, a.gold)
    if a.grid:
        for k in LEGS:
            report(run({k: size[k] or 0.55}, a.fx, a.gold), f"{k:8s} alone       | ")
        for k in LEGS[:4]:
            report(run({**size, k: 0.0}, a.fx, a.gold), f"without {k:8s}     | ")
        report(run({**size, "session": 0.55}, a.fx, a.gold), "with session 0.55    | ")
        for g, f in ((0.17, 0.5), (0.17, 1.2), (0.22, 0.85), (0.22, 1.2), (0.30, 1.6), (0.40, 2.0)):
            report(run(size, f, g), f"cost gold {g:.2f} fx {f:.2f} | ")
        for s in (0.25, 0.5, 0.75, 1.25):
            report(run({k: s * v for k, v in size.items()}, a.fx, a.gold), f"all sizes x {s:4.2f}     | ")
        # sizes set from the first half only: each leg scaled to the volatility it had up to 2017
        vol = D[D.index < CUT].std() * np.sqrt(252)
        early = {k: 0.08 / vol[k] for k in LEGS[:4]}
        print("sizes from the years to 2017:", "  ".join(f"{k} {v:.4f}" for k, v in early.items()))
        report(run(early, a.fx, a.gold)[D.index >= CUT], "those sizes, 2018 on | ")
    else:
        r = run(size, a.fx, a.gold)
        report(r)
        y = (1 + r).groupby(r.index.year).prod() - 1
        print("by year (%):", "  ".join(f"{k}: {100 * v:+.0f}" for k, v in y.items()))
        print("legs (annual volatility %, Sharpe to 2017 | from 2018, share of the days traded, worst day):")
        for k in LEGS:
            x = D[k]
            print(f"  {k:8s} {100 * size[k] * x.std() * np.sqrt(252):4.1f}  {sharpe(x[x.index < CUT]):+.2f} | "
                  f"{sharpe(x[x.index >= CUT]):+.2f}  {100 * (x != 0).mean():3.0f}%  {100 * size[k] * x.min():+.1f}%")
        print("result of each leg by year (% of the balance):")
        for k in LEGS[:4]:
            print(f"  {k:8s}", "  ".join(f"{yy % 100:02d}: {100 * v:+.0f}"
                                         for yy, v in (size[k] * D[k]).groupby(D.index.year).sum().items()))
        c = D[list(LEGS[:4])].corr()
        print("largest correlation between two of the four legs:", f"{c.where(~np.eye(4, dtype=bool)).abs().max().max():.2f}")
