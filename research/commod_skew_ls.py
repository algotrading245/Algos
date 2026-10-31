"""Fernandez-Perez, Frijns, Fuertes, Miffre 2018 (J Banking & Finance 86): long the most negatively skewed commodities,
short the most positively skewed, monthly.  R=12 months of daily returns, H=1 month, top/bottom 3 of 15 (FTMO set).

    python research/commod_skew_ls.py

Costs: spread per unit of turnover (FTMO spread when exported, else 6 bp one-way) and FTMO swap per calendar day held
(points * point / price, from docs/ftmo_specs.json).  Output: marketdata/candidates/commod_skew_ls(.csv|_stress.csv).
Roll days zeroed (|daily return| > 12%) and CL 2020-04-20/21 dropped before skew.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout

MK = {"CC": "COCOA.c", "KC": "COFFEE.c", "ZC": "CORN.c", "CT": "COTTON.c", "ZS": "SOYBEAN.c", "SB": "SUGAR.c",
      "ZW": "WHEAT.c", "CL": "USOIL.cash", "BZ": "UKOIL.cash", "NG": "NATGAS.cash", "HG": "XCUUSD",
      "GC": "XAUUSD", "SI": "XAGUSD", "PL": "XPTUSD", "PA": "XPDUSD"}
SPLIT = "2018-01-01"
SPEC = json.load(open(ROOT / "docs" / "ftmo_specs.json"))["symbols"]


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


def load():
    P = pd.DataFrame({k: pd.read_csv(ROOT / "marketdata" / "commod" / f"{k}.csv", index_col=0, parse_dates=True).close
                      for k in MK}).sort_index()
    return P


def run(P, n=3, lb=252, fix=True, cost_mult=1.0, swap=True):
    R = P.pct_change(fill_method=None)
    R = R.where(R.abs() <= 0.12, 0.0) if fix else R.clip(-0.5, 0.5)
    if fix:
        R.loc["2020-04-20":"2020-04-21", "CL"] = np.nan
    ends = R.groupby([R.index.year, R.index.month]).tail(1).index
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    cur = pd.Series(0.0, index=R.columns)
    for i, d in enumerate(R.index):
        if d in ends:
            w = R.loc[:d].tail(lb)
            sk = w.skew()[w.count() >= int(lb * 0.8)].dropna()
            cur = pd.Series(0.0, index=R.columns)
            if len(sk) >= 2 * n + 2:
                o = sk.sort_values()
                cur[o.index[:n]] = 1.0 / n
                cur[o.index[-n:]] = -1.0 / n
        W.iloc[i] = cur.values
    W = W.shift(1).fillna(0.0)  # position held the day after the month-end signal
    # spread cost per unit turnover
    sp = {}
    for k, s in MK.items():
        v = SPEC.get(s, {})
        px = P[k].median()
        bps = v.get("spread", 0) * v.get("point", 0) / px if v.get("spread", 0) else 6e-4
        sp[k] = max(bps, 2e-4) / 2 if v.get("spread", 0) else 6e-4
    sp = pd.Series(sp)
    cost = (W.diff().abs().fillna(0) * sp).sum(axis=1) * cost_mult
    sw = pd.Series(0.0, index=R.index)
    if swap:
        days = pd.Series(R.index.to_series().diff().dt.days.fillna(1).values, index=R.index)
        for k, s in MK.items():
            v = SPEC[s]
            last = P[k].dropna().iloc[-1]  # swap is quoted at today's price: fixed percent rate over history
            f = v["swap_long"] * v["point"] / last
            g = v["swap_short"] * v["point"] / last
            # swap points sign: negative = pays; per calendar day, on position size
            sw += (W[k].clip(lower=0) * f + (-W[k]).clip(lower=0) * g) * days
        sw = sw * cost_mult if False else sw
    gross = (W * R.fillna(0)).sum(axis=1)
    r = gross - cost + sw
    return r[W.abs().sum(axis=1).cumsum() > 0], gross


if __name__ == "__main__":
    P = load()
    out = {}
    for nm, kw in {"main": {}, "no_fix": dict(fix=False), "n2": dict(n=2), "n4": dict(n=4), "lb126": dict(lb=126),
                   "noswap": dict(swap=False)}.items():
        r, g = run(P, **kw)
        r = holdout.drop(r) if hasattr(holdout, "drop") else r
        out[nm] = r
        print(f"{nm:8s} Sharpe {sharpe(r):+.2f} to2017 {sharpe(r[:SPLIT]):+.2f} 2018+ {sharpe(r[SPLIT:]):+.2f} "
              f"ann {r.mean()*252:+.3%} vol {r.std()*np.sqrt(252):.3%}")
    r, _ = run(P)
    s, _ = run(P, cost_mult=1.5)
    r2, _ = run(P, cost_mult=2.0)
    r, s, r2 = [holdout.drop(x) for x in (r, s, r2)]
    print("1.5x", round(sharpe(s), 2), "2x", round(sharpe(r2), 2))
    d = ROOT / "marketdata" / "candidates"
    r.rename("r").rename_axis("day").to_csv(d / "commod_skew_ls.csv")
    s.rename("r").rename_axis("day").to_csv(d / "commod_skew_ls_stress.csv")
