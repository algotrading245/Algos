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
SWAP_BP = 2.0


def daily(sym):
    d = pd.read_csv(f"marketdata/histdata/{sym}_M1.csv.gz")
    t = pd.to_datetime(d["time"], unit="s")
    d.index = pd.DatetimeIndex(t)
    d = d[np.asarray(t.dt.hour < 16)]
    c = d["close"].groupby(d.index.normalize()).last()
    c = c[c.index.dayofweek < 5]
    return holdout.drop(c)


def run(c, spread_bp, k=1.0, variant=0):
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
        nights = (idx[x] - idx[e]).days
        cost.iloc[e] += k * spread_bp * 1e-4 / 2
        cost.iloc[x] += k * spread_bp * 1e-4 / 2
        # swap spread over the held days in proportion to calendar nights
        for j in range(e + 1, x + 1):
            cost.iloc[j] += k * SWAP_BP * 1e-4 * (idx[j] - idx[j - 1]).days
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
        print(s, c.index[0].date(), c.index[-1].date(), len(c))
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
