"""Caporale & Plastun (2019) FX price overreaction fade (queue id paper_caporale_plastun_overreaction_fx).

Rule (fixed, no sweep): day R = close(22:59 bar)/open(01:00 bar) - 1 on the server clock (rollover 23:00-01:00 left out).
Overreaction when R beyond mean20 +/- 2*sd20 of the previous 20 days' R (past only).  Next weekday: enter at the 01:00 bar
open opposite to the overreaction, exit at the 08:00 bar open.  Costs: round trip in bp of price (EURUSD 0.8, USDJPY 1.2,
AUDUSD 1.0, EURJPY 1.4, USDCAD 1.2), stress 1.5x, 2x.  Equal-weight mean of the pairs' daily returns (a day with no trade = 0).
Halves: to 2017 / 2018 on; holdout dropped via tools/holdout.py.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

PAIRS = {"EURUSD": 0.8, "USDJPY": 1.2, "AUDUSD": 1.0, "EURJPY": 1.4, "USDCAD": 1.2}
N, K = 20, 2.0


def pair_trades(name):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{name}_M1.csv.gz")
    d = d.drop_duplicates("time").sort_values("time")
    d["dt"] = pd.to_datetime(d.time, unit="s")
    d = d[d.dt < holdout.START]
    d["day"] = d.dt.dt.normalize()
    d["mod"] = d.dt.dt.hour * 60 + d.dt.dt.minute
    d = d[d.dt.dt.dayofweek < 5]
    o1 = d[d["mod"] == 60].groupby("day").open.first()
    c22 = d[d["mod"] == 22 * 60 + 59].groupby("day").close.last()
    o8 = d[d["mod"] == 8 * 60].groupby("day").open.first()
    df = pd.DataFrame({"o1": o1, "c22": c22, "o8": o8}).dropna(subset=["o1", "c22"])
    df["R"] = df.c22 / df.o1 - 1
    m = df.R.rolling(N).mean().shift(1)
    s = df.R.rolling(N).std().shift(1)
    sig = pd.Series(0, index=df.index)
    sig[df.R > m + K * s] = -1   # fade positive overreaction
    sig[df.R < m - K * s] = 1
    # trade on next available day in df (consecutive trading day)
    sig_next = sig.shift(1)
    gap = (df.index.to_series().diff().dt.days <= 4)
    sig_next = sig_next.where(gap, 0).fillna(0)
    gross = sig_next * (df.o8 / df.o1 - 1)
    gross = gross.where(sig_next != 0).dropna()
    return gross, sig_next


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


def main():
    cols, cols1, cols2, mk = {}, {}, {}, {}
    for p, c in PAIRS.items():
        g, sn = pair_trades(p)
        n = len(g)
        print(f"{p}: trades {n}; gross mean bp {g.mean()*1e4:.2f}, win {np.mean(g>0):.2f}; "
              f"pos-fade n={int((sn==-1).sum())} neg-fade n={int((sn==1).sum())}")
        for lab, mult, store in (("1x", 1.0, cols), ("1.5x", 1.5, cols1), ("2x", 2.0, cols2)):
            net = g - c * 1e-4 * mult
            store[p] = net
        h1 = g[g.index < "2018-01-01"]
        h2 = g[g.index >= "2018-01-01"]
        print(f"   gross bp/trade to2017 {h1.mean()*1e4:.2f} (n {len(h1)}) ; 2018on {h2.mean()*1e4:.2f} (n {len(h2)}); "
              f"net1x {((h1-c*1e-4).mean())*1e4:.2f} / {((h2-c*1e-4).mean())*1e4:.2f}")
    idx = pd.bdate_range("2009-01-01", holdout.START - pd.Timedelta(days=1))

    def daily(store):
        return pd.DataFrame({p: s.reindex(idx).fillna(0) for p, s in store.items()})
    d1, d15, d2 = daily(cols), daily(cols1), daily(cols2)
    for lab, d in (("1x", d1), ("1.5x", d15), ("2x", d2)):
        r = d.mean(axis=1)
        a, b = r[r.index < "2018-01-01"], r[r.index >= "2018-01-01"]
        print(f"book {lab}: Sharpe to2017 {sharpe(a):.2f}, 2018on {sharpe(b):.2f}, all {sharpe(r):.2f}, ann ret bp {r.mean()*252*1e4:.1f}")
    print("per-pair net 1x Sharpe halves:")
    mkt = {}
    for p in PAIRS:
        a, b = d1[p][d1.index < "2018-01-01"], d1[p][d1.index >= "2018-01-01"]
        print(f"  {p}: {sharpe(a):.2f} / {sharpe(b):.2f}  all {sharpe(d1[p]):.2f}")
    cand = ROOT / "marketdata" / "candidates"
    out = lambda d: pd.DataFrame({"day": d.index.strftime("%Y-%m-%d"), "r": d.mean(axis=1).values})
    out(d1).to_csv(cand / "overreaction_fx.csv", index=False)
    out(d15).to_csv(cand / "overreaction_fx_stress.csv", index=False)
    mk = d1.copy()
    mk.insert(0, "day", mk.index.strftime("%Y-%m-%d"))
    mk.to_csv(cand / "overreaction_fx_markets.csv", index=False)


main()
