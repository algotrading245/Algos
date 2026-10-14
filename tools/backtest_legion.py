"""Backtest of the AurumLegion EA: the bots that are on by default (grid, day windows, hold) on one account, and
with --scan the scalp bot on eight symbols, which decides whether it may be on.

Grid and hold are the AurumHydra ones (backtest_hydra.py). A day window is "symbol, clock (S server, L London,
T Tokyo), start, end, side (B/S), days (A every weekday, G dates divisible by five or the Friday before one),
loss at the stop in % of the balance"; the stop is --day-stop average moves of that window (60 days) from the entry.
Scalp: an M5 close --k standard deviations (20 closes) from their average is faded between server hours 9 and 20,
closed at the first close back across the average, after 12 bars, or at a stop 2 standard deviations away.
Minute bid bars from histdata.com; costs are assumed round trips in basis points, not the broker's.

  python tools/backtest_legion.py           the default bots, their combination and the size table
  python tools/backtest_legion.py --scan    the scalp bot, symbol by symbol
"""
import argparse
import numpy as np
import pandas as pd
import backtest_hydra as bh

COST = {"XAUUSD": 0.8, "EURUSD": 0.85, "USDJPY": 0.85, "GBPUSD": 1.1, "AUDUSD": 1.1, "USDCAD": 1.2, "USDCHF": 1.2, "XAGUSD": 5.0}
ZONE = {"S": None, "L": "Europe/London", "T": "Asia/Tokyo"}
WINDOWS = "USDJPY,T,955,1125,S,G,2.0;EURUSD,L,1130,1300,S,A,1.0"


def minute(sym):
    """Minute bid bars of one symbol as arrays: time (server, seconds), open, high, low, close."""
    m = pd.read_csv(bh.DATA / f"{sym}_M1.csv.gz", dtype={"time": np.int64, "open": np.float32, "high": np.float32,
                                                        "low": np.float32, "close": np.float32}).sort_values("time")
    return tuple(m[c].to_numpy() for c in ("time", "open", "high", "low", "close"))


def server(days, minutes, clock):
    """Server time (New York + 7 hours), in seconds, of `minutes` after midnight on `clock` for each day."""
    at = days + pd.Timedelta(minutes=minutes)
    if ZONE[clock]:
        at = at.tz_localize(ZONE[clock]).tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return ((at - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()


def window(bars, clock, start, end, side, gotobi, risk, stop=3.0, cost=0.85, days_avg=60):
    """Daily results of one timed window, as fractions of the balance."""
    t, o, h, l, c = bars
    days = pd.bdate_range("2009-06-01", pd.Timestamp(t[-1], unit="s").normalize())
    a = server(days, start // 100 * 60 + start % 100, clock)
    b = server(days, end // 100 * 60 + end % 100, clock)
    i0, i1 = np.searchsorted(t, a), np.searchsorted(t, b) - 1
    ok = (i0 < len(t)) & (i1 > i0)
    ok[ok] &= (t[i0[ok]] - a[ok] <= 300) & (b[ok] - t[i1[ok]] <= 600)
    move = np.full(len(days), np.nan)
    move[ok] = np.log(c[i1[ok]].astype(np.float64) / o[i0[ok]])
    avg = pd.Series(np.abs(move)).rolling(days_avg, min_periods=days_avg // 2).mean().shift(1).to_numpy()
    dom, fri = days.day.to_numpy(), days.dayofweek.to_numpy() == 4
    trade = ok & ~np.isnan(avg)
    if gotobi:
        trade &= (dom % 5 == 0) | (fri & (((dom + 1) % 5 == 0) | ((dom + 2) % 5 == 0)))
    out = np.zeros(len(days))
    for k in np.flatnonzero(trade):
        dist = stop * avg[k]
        worst = (h[i0[k]:i1[k] + 1].max() if side < 0 else l[i0[k]:i1[k] + 1].min()) / o[i0[k]]
        r = -dist if -side * np.log(worst) >= dist else side * move[k]
        out[k] = risk * (r - cost * 1e-4) / dist
    return pd.Series(out, index=days)


def scalp(bars, k=2.5, n=20, stop=2.0, hold=12, cost=0.85, h0=9, h1=20):
    """Results of the scalp trades of one symbol in units of the loss at the stop, indexed by entry time."""
    t, o, h, l, c = bars
    g = pd.DataFrame({"h": h, "l": l, "c": c}).groupby(t // 300).agg({"h": "max", "l": "min", "c": "last"})
    T = g.index.to_numpy() * 300
    H, L, C = (g[x].to_numpy().astype(np.float64) for x in ("h", "l", "c"))
    ma = pd.Series(C).rolling(n).mean().to_numpy()
    sd = pd.Series(C).rolling(n).std().to_numpy()
    whole = np.r_[np.zeros(n, bool), T[n:] - T[:-n] == 300 * n]                   # no hole inside the band
    hour, dow = (T % 86400) // 3600, (T // 86400 + 3) % 7
    hit = whole & (sd > 0) & (np.abs(C - ma) >= k * sd) & (hour >= h0) & (hour <= h1) & (dow < 5)
    res, when, free = [], [], 0
    for i in np.flatnonzero(hit):
        if i < free or i + hold >= len(C) or T[i + hold] - T[i] != 300 * hold:
            continue
        side, dist = (-1 if C[i] > ma[i] else 1), stop * sd[i]
        r, j = None, i
        for j in range(i + 1, i + hold + 1):
            if side * ((L[j] if side > 0 else H[j]) - C[i]) <= -dist:
                r = -dist
                break
            if (C[j] - ma[j]) * side >= 0:
                break
        r = side * (C[j] - C[i]) if r is None else r
        res.append((r - cost * 1e-4 * C[i]) / dist)
        when.append(T[i])
        free = j + 1
    return pd.Series(res, index=pd.to_datetime(np.array(when, dtype=np.int64), unit="s"), dtype=float)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", default=WINDOWS, help="day windows, as in the EA but without the broker's suffix")
    ap.add_argument("--day-stop", type=float, default=3.0, help="stop of a day window, average moves of the window")
    ap.add_argument("--grid-risk", type=float, default=0.035, help="fraction of the balance the grid loses at its stop-out")
    ap.add_argument("--grid-cost", type=float, default=1.8, help="round-trip cost of AUDCAD, basis points")
    ap.add_argument("--hold-vol", type=float, default=0.107, help="volatility target of the gold hold")
    ap.add_argument("--swap", type=float, default=0.04, help="yearly holding charge on long gold, fraction of the notional")
    ap.add_argument("--scan", action="store_true", help="the scalp bot on eight symbols")
    a = ap.parse_args()
    if a.scan:
        print("Scalp bot, result per trade in losses-at-the-stop (t) trades: 2009-2017 | 2018-2026, net of the assumed cost")
        for sym in COST:
            bars = minute(sym)
            for k in (2.0, 2.5, 3.0):
                x = scalp(bars, k=k, cost=COST[sym])
                cell = lambda v: f"{v.mean():+.3f} ({v.mean() / v.std() * np.sqrt(len(v)):+5.1f}) {len(v):6d}" if len(v) > 30 else "-"
                print(f"  {sym} k {k:.1f}: {cell(x[:bh.SPLIT])} | {cell(x[bh.SPLIT:])}", flush=True)
            del bars
    else:
        H = bh.hourly()
        parts = {"grid": a.grid_risk * bh.grid(H.AUDCAD, cost=a.grid_cost), "hold": bh.hold(H.XAUUSD, a.hold_vol, a.swap)}
        for row in a.windows.split(";"):
            sym, clock, s, e, side, days, risk = (f.strip() for f in row.split(","))
            parts[f"day {sym}"] = window(minute(sym), clock, int(s), int(e), 1 if side == "B" else -1, days == "G",
                                         float(risk) / 100, a.day_stop, COST.get(sym, 2.0))
        F = pd.DataFrame(parts).loc["2010-06-01":].fillna(0.0)
        print("Correlation of daily results:\n" + F.corr().round(2).to_string())
        for name in F:
            bh.report(F[name], name)
        bh.report(F.sum(axis=1), "all")
        print("Resampled 2018-2026 results of all (blocks of 5 days), every size multiplied:")
        bh.ruin(F.sum(axis=1)[bh.SPLIT:].to_numpy())
