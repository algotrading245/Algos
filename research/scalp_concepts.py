"""Three classic fast-scalping concepts on the synthetic gold path (15 s steps).

Shows what each earns per trade before and after the 0.10 spread when price has no
structure. Run on real ticks (marketdata/) to find out whether any concept has an edge.
"""
import sys
import numpy as np
sys.path.insert(0, "tools")
import backtest_sim as b

def trades(bid, ask, entries, side, tp, sl, max_hold):
    """Enter at ask (buy) / bid (sell) at each entry step; exit on TP, SL or time."""
    out = []
    last_exit = -1
    for i, sd in zip(entries, side):
        if i <= last_exit or i + max_hold >= len(bid):
            continue
        px = ask[i] if sd > 0 else bid[i]
        path = (bid[i + 1:i + 1 + max_hold] - px) if sd > 0 else (px - ask[i + 1:i + 1 + max_hold])
        hit = np.flatnonzero((path >= tp) | (path <= -sl))
        k = hit[0] if len(hit) else max_hold - 1
        out.append((path[k], path[k] + (ask[i] - bid[i])))   # (net, before spread)
        last_exit = i + 1 + k
    return np.array(out)

def report(name, r, minutes):
    net, gross = r[:, 0].mean(), r[:, 1].mean()
    print(f"{name:34s} {len(r):7d} trades  gross {gross:+.3f}  net {net:+.3f} per oz "
          f"({100*np.mean(r[:,0]>0):.0f}% wins, hold <= {minutes} min)")

for seed in range(3):
    bid, ask, day, sec = b.make_market(1, seed)
    mid = (bid + ask) / 2
    print(f"--- synthetic year, seed {seed}")
    # A: momentum burst - 1-minute move > 2 sigma, follow it.
    r1 = mid[4:] - mid[:-4]
    sd1 = np.std(r1)
    idx = np.flatnonzero(np.abs(r1) > 2 * sd1) + 4
    report("A momentum burst (follow 1m >2sd)", trades(bid, ask, idx, np.sign(r1[idx - 4]), 1.0, 1.0, 20), 5)
    # B: fade the same burst (mean reversion).
    report("B fade burst (revert 1m >2sd)", trades(bid, ask, idx, -np.sign(r1[idx - 4]), 1.0, 1.0, 20), 5)
    # C: London opening-range breakout: 08:00-09:00 range, trade the break until 12:00.
    steps_day = b.BARS_PER_DAY * b.STEPS_PER_BAR
    ent, sd_ = [], []
    for d0 in range(0, len(bid) - steps_day, steps_day):
        o = d0 + (8 - 1) * 240
        hi, lo = mid[o:o + 240].max(), mid[o:o + 240].min()
        w = mid[o + 240:o + 240 * 4]
        up, dn = np.flatnonzero(w > hi), np.flatnonzero(w < lo)
        if len(up) or len(dn):
            first_up = up[0] if len(up) else 10**9
            first_dn = dn[0] if len(dn) else 10**9
            ent.append(o + 240 + min(first_up, first_dn)); sd_.append(1 if first_up < first_dn else -1)
    report("C London range breakout", trades(bid, ask, np.array(ent), np.array(sd_), 6.0, 4.0, 240 * 3), 180)
