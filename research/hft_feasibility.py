"""Can seconds-long trades beat the retail cost on XAUUSD.pc? Scan on the real tick days in marketdata/ticks.

Signal: the mid price moved at least k over the last w seconds. "follow" trades with the move, "fade" against it.
The order reaches the broker --latency ms after the signal tick and is filled at the quote then in force (buy at ask,
sell at bid); the close is sent hold seconds later and takes the same delay. Cost is the real quoted spread plus
COMMISSION per round trip. One position at a time per rule. Rules are ranked on the first days and the best ones are
then shown on the last --test days, which the ranking never saw.

The broker publishes a quote about every 100 ms. A delay shorter than that fills the order at the very quote that
gave the signal, which a real market order is not promised: read the low-latency rows as an upper bound.

Usage: python research/hft_feasibility.py [--latency 5 50 100 210] [--test 5]
"""
import argparse
import itertools

import numpy as np

import realdata as rd

COMMISSION = 0.06           # price units per round trip (6 USC per lot)
WINDOWS = (0.1, 0.2, 1.0, 5.0, 30.0)
MOVES = (0.10, 0.20, 0.50, 1.00, 1.50)
HOLDS = (0.5, 1.0, 5.0, 30.0, 120.0)


def day_trades(t, bid, ask, w, k, hold, lat):
    """Non-overlapping trades of one day: (signed mid move, follow net, fade net) per trade."""
    mid = (bid + ask) / 2
    back = np.searchsorted(t, t - int(w * 1000), side="right") - 1
    move = np.where(back >= 0, mid - mid[np.maximum(back, 0)], 0.0)
    cand = np.flatnonzero(np.abs(move) >= k)
    cand = cand[t[cand] + int(hold * 1000) + 2 * lat <= t[-1]]
    rows, free = [], -1
    p = 0
    ct = t[cand]
    while p < len(cand):
        i = cand[p]
        e = np.searchsorted(t, t[i] + lat, side="right") - 1
        x = np.searchsorted(t, t[i] + lat + int(hold * 1000) + lat, side="right") - 1
        s = 1.0 if move[i] > 0 else -1.0
        long_net = bid[x] - ask[e] - COMMISSION
        short_net = bid[e] - ask[x] - COMMISSION
        rows.append((s * (mid[x] - mid[e]), long_net if s > 0 else short_net, short_net if s > 0 else long_net))
        free = t[x]
        p = int(np.searchsorted(ct, free, side="right"))
    return np.array(rows).reshape(-1, 3)


def stats(a):
    n = len(a)
    if n < 2:
        return n, 0.0, 0.0
    return n, a.mean(), a.mean() / (a.std(ddof=1) / np.sqrt(n) + 1e-12)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--latency", type=int, nargs="+", default=[5, 50, 100, 210], help="one-way order delay, ms")
    ap.add_argument("--test", type=int, default=5, help="last days held out of the ranking")
    a = ap.parse_args()
    days = [rd.ticks(p) for p in rd.tick_days()]
    sp = np.concatenate([d[2] - d[1] for d in days])
    print(f"{len(days)} tick days, {len(sp)} ticks, spread median {np.median(sp):.2f}, "
          f"cost per round trip about {np.median(sp) + COMMISSION:.2f}")
    for lat in a.latency:
        res = []
        for w, k, hold in itertools.product(WINDOWS, MOVES, HOLDS):
            per = [day_trades(*d, w, k, hold, lat) for d in days]
            tr, te = np.concatenate(per[:-a.test]), np.concatenate(per[-a.test:])
            for name, col in (("follow", 1), ("fade", 2)):
                sign = 1 if col == 1 else -1
                res.append((name, w, k, hold, stats(tr[:, col]), stats(te[:, col]), sign * tr[:, 0].mean() if len(tr) else 0))
        res = [r for r in res if r[4][0] >= 100]
        res.sort(key=lambda r: -r[4][1])
        print(f"\nlatency {lat} ms: {len(res)} rules with 100+ trades; "
              f"{sum(r[4][1] > 0 for r in res)} positive after cost on the first {len(days) - a.test} days, "
              f"{sum(r[5][1] > 0 for r in res)} on the last {a.test}")
        print("best by mean net on the first days (price units per trade; t = t-statistic):")
        for name, w, k, hold, (n1, m1, t1), (n2, m2, t2), gross in res[:8]:
            print(f"  {name:6s} move>={k:.2f} in {w:4.1f}s, hold {hold:5.1f}s | first: n {n1:6d} net {m1:+.3f} t {t1:+5.1f} "
                  f"gross {gross:+.3f} | last: n {n2:5d} net {m2:+.3f} t {t2:+5.1f}")
        g = max(res, key=lambda r: r[6])
        print(f"  largest gross edge before any cost: {g[0]} move>={g[2]:.2f} in {g[1]}s, hold {g[3]}s: {g[6]:+.3f}")
