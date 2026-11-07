"""Turn-of-the-month long on S&P 500 / Nasdaq (McConnell & Xu 2008; Quantpedia).
Rule (prespecified, no tuning): buy the close of the last trading day of the month, sell the close of trading day +3
of the next month. Long only. Variant B (secondary, counted as a trial): buy the close of day -2 (so the return of
day -1 is included, the paper's days -1..+3).
Daily close = last M1 bar before 16:00 in the file's clock (histdata, fixed offset). Costs: spread round trip
1.0 bp (S&P) / 0.5 bp (Nasdaq) at 1x, financing 2 bp per night held at 1x (about 7%/yr long CFD); 1.5x = both x1.5.
Holdout dropped through tools/holdout.py.  Outputs marketdata/candidates/totm_us.csv, _stress.csv, _markets.csv.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
import holdout

SPEC = {"SPXUSD": 1.0, "NSXUSD": 0.5}   # spread bp round trip at 1x
SWAP_BP = 2.0


def daily(sym):
    d = pd.read_csv(f"marketdata/histdata/{sym}_M1.csv.gz")
    t = pd.to_datetime(d["time"], unit="s")
    d.index = pd.DatetimeIndex(t)
    d = d[np.asarray(t.dt.hour < 16)]
    c = d["close"].groupby(d.index.normalize()).last()
    c = c[c.index.dayofweek < 5]
    return holdout.drop(c)


def run(c, spread_bp, k=1.0, pre=0):
    """pre=0: enter close of last day of month; pre=1: enter one day earlier."""
    ret = c.pct_change().fillna(0.0)
    idx = c.index
    mon = pd.Series(idx.to_period("M"), index=idx)
    pos = pd.Series(0.0, index=idx)
    entries = []
    months = mon.unique()
    for i in range(len(months) - 1):
        a = np.where(mon.values == months[i])[0]
        b = np.where(mon.values == months[i + 1])[0]
        if len(b) < 4:
            continue
        e = a[-1] - pre            # entry day position (close)
        x = b[2]                   # trading day +3 = third day of new month
        entries.append((e, x))
        pos.iloc[e + 1: x + 1] = 1.0
    r = ret * pos
    cost = pd.Series(0.0, index=idx)
    for e, x in entries:
        cost.iloc[e] += k * spread_bp * 1e-4 / 2
        cost.iloc[x] += k * spread_bp * 1e-4 / 2
        cost.iloc[e + 1: x + 1] += k * SWAP_BP * 1e-4
    return r - cost


def sh(x, lo=None, hi=None):
    if lo:
        x = x[x.index >= lo]
    if hi:
        x = x[x.index < hi]
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


if __name__ == "__main__":
    px = {s: daily(s) for s in SPEC}
    for s, c in px.items():
        print(s, c.index[0].date(), c.index[-1].date(), len(c))
    out = {}
    for pre in (0, 1):
        for s, c in px.items():
            for k in (0.0, 1.0, 1.5, 2.0):
                x = run(c, SPEC[s], k, pre)
                print(f"variant{pre} {s} cost x{k}: Sharpe all {sh(x):.2f}  <=2017 {sh(x, hi='2018-01-01'):.2f}  2018+ {sh(x, lo='2018-01-01'):.2f}  mean/yr {x.mean()*252*100:.2f}%")
            out[(pre, s)] = {k: run(c, SPEC[s], k, pre) for k in (1.0, 1.5)}
    # primary: variant 0, equal-weight both indices
    for tag, k in (("", 1.0), ("_stress", 1.5)):
        df = pd.concat([out[(0, s)][k] for s in SPEC], axis=1).dropna()
        r = df.mean(axis=1)
        pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(f"marketdata/candidates/totm_us{tag}.csv", index=False)
    m = pd.concat({s: out[(0, s)][1.0] for s in SPEC}, axis=1).dropna()
    r = m.mean(axis=1)
    print("combined 1x: all %.2f  <=2017 %.2f  2018+ %.2f" % (sh(r), sh(r, hi="2018-01-01"), sh(r, lo="2018-01-01")))
    m.insert(0, "day", m.index.strftime("%Y-%m-%d"))
    m.to_csv("marketdata/candidates/totm_us_markets.csv", index=False)
