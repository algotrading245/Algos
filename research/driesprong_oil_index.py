"""Driesprong-Jacobsen-Maat 2008: hold the index next month only after a negative WTI month. No fitting.
Signal at month end from CL (roll days zeroed), long-only index CFD, swap per calendar night, spread per switch.
Run: python research/driesprong_oil_index.py"""
import sys, gzip
sys.path.insert(0, "tools")
import numpy as np, pandas as pd
import holdout

SWAP_BP = 2.5      # per calendar night held (long index swap, idea text)
SPREAD_BP = 1.0    # per side (US500 ~0.5pt on ~4000-7000, GER40 ~1pt, JP225 ~8pt on 30000+): ~1bp each

def load_cl(sym="CL"):
    d = pd.read_csv(f"marketdata/commod/{sym}.csv", parse_dates=["date"]).set_index("date")["close"]
    r = d.pct_change()
    r[r.abs() > 0.10] = 0.0          # roll / negative price days
    return holdout.drop(r.dropna())

def oil_signal(r):
    m = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    return m  # month return; used for NEXT month

def load_idx(name):
    if name == "US500":
        d = pd.read_csv("marketdata/histdata/SPX_D1.csv", parse_dates=["date"]).set_index("date")["close"]
    else:
        f = {"GER40": "GRXEUR", "JP225": "JPXJPY"}[name]
        m = pd.read_csv(f"marketdata/histdata/{f}_M1.csv.gz")
        m.columns = [c.strip() for c in m.columns]
        t = pd.to_datetime(m["time"], unit="s")
        m = m.set_index(t)["close"]
        # server-clock free: daily close at 21:00 UTC-ish, use last bar of each UTC date
        d = m.groupby(m.index.normalize()).last()
        d.index.name = "date"
    d = d[d.index.dayofweek < 5]
    return holdout.drop(d)

def run(name, sig, cost_mult=1.0, always=False, osign=-1):
    p = load_idx(name)
    r = p.pct_change().dropna()
    r = r[(r.abs() < 0.15)]
    per = r.index.to_period("M")
    prev = pd.PeriodIndex(per).asi8  # placeholder
    pos = pd.Series([(1.0 if always else float(osign * sig.get(pp - 1, np.nan) > 0)) for pp in per], index=r.index)
    pos = pos.fillna(0.0)
    gap = pd.Series(r.index, index=r.index).diff().dt.days.fillna(1).clip(1, 4)
    held_prev = pos.shift(1).fillna(0)
    swap = held_prev * gap * SWAP_BP * 1e-4 * cost_mult
    sw = (pos.diff().abs().fillna(0)) * SPREAD_BP * 1e-4 * cost_mult
    out = pos.shift(1).fillna(0) * r - swap - sw   # position decided at prior close (signal known at month end)
    return out

def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0

if __name__ == "__main__":
    cl = load_cl()
    sig = oil_signal(cl)
    print("oil months", len(sig), "neg share", (sig < 0).mean().round(3), "from", sig.index[0])
    mk = {}
    for n in ["US500", "GER40", "JP225"]:
        idx = load_idx(n)
        print(n, idx.index[0].date(), idx.index[-1].date(), len(idx))
        for cm in [1, 1.5, 2]:
            s = run(n, sig, cm)
            a, b = s[s.index < "2018-01-01"], s[s.index >= "2018-01-01"]
            print(f" {n} x{cm}: Sharpe all {sharpe(s):.2f} h1 {sharpe(a):.2f} h2 {sharpe(b):.2f} ann {s.mean()*252:.3f}")
        bh = run(n, sig, 1.0, always=True)
        print(f" {n} always-long Sharpe {sharpe(bh):.2f}  | rule in-market share {(run(n,sig,0)!=0).mean():.2f}")
        mk[n] = run(n, sig, 1.0)
    # sensitivity: Brent signal
    sb = oil_signal(load_cl("BZ"))
    for n in ["US500", "GER40", "JP225"]:
        s = run(n, sb)
        print(" Brent signal", n, f"{sharpe(s):.2f}")
    # equal-weight basket, restricted to common days
    M = pd.DataFrame(mk).dropna(how="all").fillna(0)
    book = M.mean(axis=1)
    book = book[book.index >= "2010-01-01"]
    S = pd.DataFrame({k: run(k, sig, 1.5) for k in mk}).fillna(0).mean(axis=1)
    S = S[S.index >= "2010-01-01"]
    a = book[book.index < "2018-01-01"]; b = book[book.index >= "2018-01-01"]
    print("BASKET Sharpe", round(sharpe(book), 2), "h1", round(sharpe(a), 2), "h2", round(sharpe(b), 2),
          "stress", round(sharpe(S), 2))
    # always-long basket benchmark
    BH = pd.DataFrame({k: run(k, sig, 1.0, always=True) for k in mk}).fillna(0).mean(axis=1)
    print("always-long basket Sharpe", round(sharpe(BH[BH.index >= "2010-01-01"]), 2))
    if "--write" in sys.argv:
        book.rename("r").rename_axis("day").to_csv("marketdata/candidates/driesprong_oil_index.csv")
        S.rename("r").rename_axis("day").to_csv("marketdata/candidates/driesprong_oil_index_stress.csv")
        M.loc[M.index >= "2010-01-01"].rename_axis("day").to_csv("marketdata/candidates/driesprong_oil_index_markets.csv")
        print("written")
