"""Graziani (2024) time-series reversal: long the index for the next month if the return from the 4th-Friday close to
the month's last close was negative. Primary: hold to next month-end close. Variant B (pre-registered, counted as a
trial): exit at first close on/after day 14 of next month.
Daily close = last M1 bar before 16:00 file clock. Costs: spread round trip 1.0 bp (S&P) / 0.5 bp (Nasdaq) at 1x,
swap 2 bp per CALENDAR night held (conservative, weekends count) at 1x; 1.5x/2x scale both. Holdout dropped.
Outputs marketdata/candidates/graziani_rev.csv, _stress.csv, _markets.csv.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
import holdout

SPEC = {"SPXUSD": 1.0, "NSXUSD": 0.5}
# Swap per night from docs/ftmo_specs.json: |swap_long| * point / last price (US500 -160.52, US100 -730.72 points of
# 0.01), at the last price before the holdout, as research/volmanaged_mm_ftmo.py does. Replaces the flat 2 bp.
import json
_SP = json.load(open("docs/ftmo_specs.json"))["symbols"]
_MAP = {"SPXUSD": "US500.cash", "NSXUSD": "US100.cash"}
SWAP_BP_SYM = {}


def daily(sym):
    d = pd.read_csv(f"marketdata/histdata/{sym}_M1.csv.gz")
    t = pd.to_datetime(d["time"], unit="s")
    d.index = pd.DatetimeIndex(t)
    d = d[np.asarray(t.dt.hour < 16)]
    c = d["close"].groupby(d.index.normalize()).last()
    c = c[c.index.dayofweek < 5]
    return holdout.drop(c)


def run(c, spread_bp, k=1.0, variant=0, swap_bp=None):
    idx = c.index
    ret = c.pct_change().fillna(0.0)
    per = idx.to_period("M")
    months = per.unique()
    pos = pd.Series(0.0, index=idx)
    cost = pd.Series(0.0, index=idx)
    n = 0
    for i in range(len(months) - 1):
        a = np.where(per == months[i])[0]
        b = np.where(per == months[i + 1])[0]
        if len(a) < 15 or len(b) < 15:
            continue
        days = idx[a]
        fr = [j for j, dt in zip(a, days) if dt.dayofweek == 4]
        if len(fr) < 4:
            continue
        f4 = fr[3]
        rw4 = c.iloc[a[-1]] / c.iloc[f4] - 1
        if not rw4 < 0:
            continue
        e = a[-1]
        if variant == 0:
            x = b[-1]
        else:
            cand = [j for j in b if idx[j].day >= 14]
            x = cand[0]
        pos.iloc[e + 1: x + 1] = 1.0
        cost.iloc[e] += k * spread_bp * 1e-4 / 2
        cost.iloc[x] += k * spread_bp * 1e-4 / 2
        # FTMO swap (docs/ftmo_specs.json, fixed bp of notional per night, triple on the rollover3days weekday =
        # Friday): charged at each close held overnight, e .. x-1, booked on that day.
        for j in range(e, x):
            cost.iloc[j] += k * swap_bp * 1e-4 * (3.0 if idx[j].dayofweek == 4 else 1.0)
        n += 1
    return ret * pos - cost, n


def sh(x, lo=None, hi=None):
    if lo:
        x = x[x.index >= lo]
    if hi:
        x = x[x.index < hi]
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


if __name__ == "__main__":
    px = {s: daily(s) for s in SPEC}
    out = {}
    for s, c in px.items():
        sp = _SP[_MAP[s]]
        SWAP_BP_SYM[s] = abs(sp["swap_long"]) * sp["point"] / c.iloc[-1] * 1e4
        print(s, c.index[0].date(), c.index[-1].date(), len(c), "swap bp/night %.2f" % SWAP_BP_SYM[s])
    _run = run
    run = lambda c, sb, k=1.0, variant=0, s=None: _run(c, sb, k, variant, SWAP_BP_SYM["SPXUSD" if sb == 1.0 else "NSXUSD"])
    for v in (0, 1):
        for s, c in px.items():
            for k in (0.0, 1.0, 1.5, 2.0):
                x, n = run(c, SPEC[s], k, v)
                print(f"var{v} {s} x{k}: n={n} Sharpe all {sh(x):.2f} <=2017 {sh(x, hi='2018-01-01'):.2f} 2018+ {sh(x, lo='2018-01-01'):.2f} mean/yr {x.mean()*252*100:.2f}%")
            out[(v, s)] = {k: run(c, SPEC[s], k, v)[0] for k in (1.0, 1.5)}
    for s, c in px.items():
        bh = c.pct_change().dropna()
        print("buy&hold", s, "all %.2f <=2017 %.2f 2018+ %.2f" % (sh(bh), sh(bh, hi="2018-01-01"), sh(bh, lo="2018-01-01")))
    for tag, k in (("", 1.0), ("_stress", 1.5)):
        df = pd.concat([out[(0, s)][k] for s in SPEC], axis=1).dropna()
        r = df.mean(axis=1)
        pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(f"marketdata/candidates/graziani_rev{tag}.csv", index=False)
    m = pd.concat({s: out[(0, s)][1.0] for s in SPEC}, axis=1).dropna()
    r = m.mean(axis=1)
    print("combined 1x: all %.2f <=2017 %.2f 2018+ %.2f" % (sh(r), sh(r, hi="2018-01-01"), sh(r, lo="2018-01-01")))
    m.insert(0, "day", m.index.strftime("%Y-%m-%d"))
    m.to_csv("marketdata/candidates/graziani_rev_markets.csv", index=False)
