"""Backtest of AurumSnap: the two-minute fade of gold's last five minutes into the New York 16:00 close.

Rule (server time, 23:00 = 16:00 New York all year):
  At the bell the move of the last --look minutes is measured. When it is at least --k times the average size of
  the same move over the previous --days trading days, a position is opened against it: sell after a rise, buy
  after a fall. It is closed --hold seconds later, or earlier at a stop --stop times that average away from the
  entry. One trade a day at most.
Size: --risk of the balance is lost when the stop is hit. Cost is --cost price units per round trip.

Two sources:
  default   1-minute bid bars 2009-2026 (tools/backtest_bell.py with the hold rounded to whole minutes).
  --ticks   a directory of tick files written by tools/download_histdata_ticks.py. Entry --delay seconds after the
            bell and exit to the second, on mid prices (the feed's own spread at the bell is several times the
            broker's, so the cost is charged through --cost instead). The average move still comes from the bars.

Usage: python tools/backtest_snap.py [--look 5] [--hold 120] [--k 1.5] [--stop 3] [--cost 0.17] [--grid]
       python tools/backtest_snap.py --ticks <dir> [--delay 1] [--grid]
"""
import argparse
import glob
import numpy as np
import pandas as pd

import backtest_bell as bb

BELL = 1380


def tick_trades(folder, look=5, hold=120, k=1.5, stop=3.0, days=60, cost=0.17, delay=1.0):
    """One row per trade from tick mids: side, average move, net result per oz and in units of the stop distance."""
    T = bb._tables()
    move = (T["open"][BELL] - T["last"][BELL - look - 1]).dropna()
    ref = move.abs().rolling(days, min_periods=days // 2).mean().shift(1)
    t0, rows = BELL * 60, []
    for f in sorted(glob.glob(folder + "/*.pkl")):
        df = pd.read_pickle(f).dropna()
        for d, g in df.groupby(df.srv.dt.normalize()):
            r = ref.get(d, np.nan)
            if d.dayofweek > 4 or np.isnan(r) or r <= 0:
                continue
            t = (g.srv - d).dt.total_seconds().to_numpy()
            m = ((g.bid + g.ask) / 2).to_numpy()
            if len(t) < 300 or t[0] > t0 - look * 60 - 30 or t[-1] < t0 + delay + hold + 30:
                continue
            at = lambda s: max(np.searchsorted(t, s, side="right") - 1, 0)
            sig = m[at(t0)] - m[at(t0 - look * 60)]
            if sig == 0 or abs(sig) < k * r:
                continue
            s, i, j = -np.sign(sig), at(t0 + delay), at(t0 + delay + hold)
            res = s * (m[j] - m[i])
            if stop > 0 and j > i and (s * (m[i + 1:j + 1] - m[i])).min() <= -stop * r:
                res = -stop * r
            rows.append((d, s, r, res - cost))
    w = pd.DataFrame(rows, columns=["day", "side", "ref", "net"]).set_index("day").sort_index()
    w["r"] = w.net / ((stop if stop > 0 else 3.0) * w.ref)
    return w


def tick_report(t, risk=0.01, label=""):
    if len(t) < 10:
        print(f"{label}{len(t)} trades")
        return
    ret = risk * t.r
    eq = (1 + ret).cumprod()
    years = (t.index[-1] - t.index[0]).days / 365.25
    ts = lambda z: z.mean() / (z.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else 0.0
    h = t.index < t.index[0] + (t.index[-1] - t.index[0]) / 2
    pf = t.net[t.net > 0].sum() / max(-t.net[t.net < 0].sum(), 1e-9)
    print(f"{label}{len(t):4d} trades ({len(t) / years:3.0f}/yr), win {100 * (t.net > 0).mean():2.0f}%, net/oz {t.net.mean():+.2f}, "
          f"PF {pf:.2f}, t {ts(t.net):+.1f} (first half {ts(t.net[h]):+.1f}, second {ts(t.net[~h]):+.1f}), "
          f"CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):4.1f}%, maxDD {100 * (1 - eq / eq.cummax()).max():4.1f}%, worst {100 * ret.min():+.1f}%")


def by_year(t, risk):
    y = t.groupby(t.index.year).agg(n=("net", "size"), net=("net", "mean"), r=("r", lambda z: 100 * ((1 + risk * z).prod() - 1)))
    print("by year (trades, net/oz, %):", "  ".join(f"{k}: {int(v.n)} {v.net:+.2f} {v.r:+.1f}" for k, v in y.iterrows()))
    print(f"long {int((t.side > 0).sum())} trades net/oz {t.net[t.side > 0].mean():+.2f}, "
          f"short {int((t.side < 0).sum())} trades net/oz {t.net[t.side < 0].mean():+.2f}, "
          f"average move {t.ref.iloc[-60:].mean():.2f} lately")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--look", type=int, default=5, help="the move is measured over this many minutes")
    ap.add_argument("--hold", type=int, default=120, help="holding time, seconds (whole minutes without --ticks)")
    ap.add_argument("--k", type=float, default=1.5, help="trade when the move is at least k times its average size")
    ap.add_argument("--stop", type=float, default=3.0, help="stop distance in average moves, 0 = none")
    ap.add_argument("--days", type=int, default=60, help="days in the average")
    ap.add_argument("--risk", type=float, default=0.01, help="fraction of the balance lost at the stop")
    ap.add_argument("--cost", type=float, default=0.17, help="round-trip cost, price units per oz")
    ap.add_argument("--ticks", help="directory of tick files; without it the 1-minute bars are used")
    ap.add_argument("--delay", type=float, default=1.0, help="with --ticks: seconds between the bell and the entry")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    kw = dict(look=a.look, hold=a.hold, k=a.k, stop=a.stop, days=a.days, cost=a.cost)
    if a.ticks:
        run = lambda **o: tick_trades(a.ticks, **{**kw, "delay": a.delay, **o})
        rep = tick_report
        grid = (("cost", (0.0, 0.17, 0.25, 0.35), ".2f"), ("delay", (0.0, 0.3, 1.0, 2.0, 5.0, 15.0), ".1f"),
                ("hold", (15, 30, 60, 120, 180, 300, 600), "d"), ("k", (1.0, 1.5, 2.0, 3.0), ".1f"), ("look", (5, 10, 15), "d"),
                ("stop", (0.0, 2.0, 3.0, 5.0), ".1f"))
    else:
        run = lambda **o: bb.trades(**{**kw, **o, "hold": max(1, round({**kw, **o}["hold"] / 60))})
        rep = bb.report
        grid = (("cost", (0.0, 0.17, 0.25, 0.35), ".2f"), ("hold", (60, 120, 180, 300, 600), "d"),
                ("k", (1.0, 1.5, 2.0, 3.0), ".1f"), ("look", (5, 10, 15), "d"), ("stop", (0.0, 2.0, 3.0, 5.0), ".1f"),
                ("days", (20, 60, 120), "d"))
    if a.grid:
        for name, vals, fmt in grid:
            for v in vals:
                rep(run(**{name: v}), a.risk, f"{name} {format(v, fmt):>5s} | ")
    else:
        t = run()
        rep(t, a.risk)
        by_year(t, a.risk)
