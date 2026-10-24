"""The book: every leg we trade, combined at equal risk, with the risk layer on top, and what it means for the owner
(owner-approved portfolio rule, 2026-10-22).  tools/gates.py judges a new leg by what it does to this book.

    python tools/book_sim.py                 # headline numbers, writes docs/book.json for the dashboard
    python tools/book_sim.py --without grid  # the same without a leg (comma list)

The book's legs are the Hydra legs (marketdata/hydra_legs_daily.csv.gz) plus every leg in docs/candidates.json past
the gates and not rejected (status tester, demo, live or ea) whose daily series we have.  Nothing on or after the
owner's holdout (tools/holdout.py) is used.

Weights: equal risk, walk-forward.  On the first trading day of each month every leg gets 1 / (its volatility over the
252 trading days before that day), legs with under 126 days of history get none, no leg gets more than CAP of the
gross weight, and the weights sum to 1.  A leg in SCALE gets that share of an equal risk
(cross: half, as it repeats fix).  Nothing is fitted to returns, so the book's Sharpe is out of sample.

Risk layer (the same rules go into the EAs as inputs):
  vol target   size = VOL_TARGET / the book's volatility over the last 63 days, at most LEVER_MAX times the size its
               whole past volatility would give
  drawdown     half size while the book is DD_HALF below its peak, a quarter beyond DD_QUARTER
  day guard    the prop path's own 3% day stop (tools/prop_firms.py)

Headline numbers (all on the risk-managed book):
  profitable months   share of calendar months with a gain, all and from 2018
  prop pass           FTMO 2-Step 10/5 with AurumFunded's sizing (tools/prop_firms.py): share of start days that
                      reach a first payout within 12 months, failures, median months
  payout              expected payout a month once funded, $100k account, 80% split
Each is shown for the backtest and for a 70% edge (the mean cut by 30%, our allowance for decay live).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from holdout import START as HOLDOUT_START  # noqa: E402

HYDRA = ROOT / "marketdata" / "hydra_legs_daily.csv.gz"
CACHED = ROOT / "marketdata" / "candidate_legs_daily.csv.gz"
CANDIDATES = ROOT / "marketdata" / "candidates"
LEDGER = ROOT / "docs" / "candidates.json"
OUT = ROOT / "docs" / "book.json"

LOOKBACK, MIN_HISTORY, CAP = 252, 126, 0.25
VOL_TARGET, VOL_LOOKBACK, LEVER_MAX = 0.20, 63, 2.0
DD_HALF, DD_QUARTER = 0.10, 0.20
IN_BOOK = ("tester", "demo", "live", "ea")
SPLIT = "2018-01-01"
# A leg that repeats another gets a share of a leg's risk (owner 2026-10-24, steer.md): fix and cross correlate 0.61
# and held 26% of the risk as two legs. Halving cross beat one shared budget in every period (2018+ 3.15 vs 3.05,
# to 2017 2.40 vs 2.18; none 3.01).
SCALE = {"cross": 0.5}
ACCOUNT, SPLIT_SHARE = 100_000, 0.80


def sharpe(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def clip(x):
    """Weekdays before the owner's holdout only."""
    return x[(x.index.dayofweek < 5) & (x.index < HOLDOUT_START)]


def series(cid):
    """(returns, returns at 1.5x cost or None) for a candidate id, or (None, None)."""
    f = CANDIDATES / f"{cid}.csv"
    if f.exists():
        r = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        fs = CANDIDATES / f"{cid}_stress.csv"
        stress = pd.read_csv(fs, index_col=0, parse_dates=True).iloc[:, 0] if fs.exists() else None
        return r, stress
    if CACHED.exists():
        c = pd.read_csv(CACHED, index_col=0, parse_dates=True)
        if cid in c:
            return c[cid], None
    return None, None


def legs(without=(), extra=None):
    """Every leg in the book as columns, less `without`, plus `extra` ({name: daily series}); NaN before a leg starts."""
    out = clip(pd.read_csv(HYDRA, index_col=0, parse_dates=True))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"candidates": []}
    for c in ledger["candidates"]:
        if c.get("status") in IN_BOOK and c["id"] not in out:
            r, _ = series(c["id"])
            if r is not None:
                out = out.join(clip(r).rename(c["id"]), how="outer")
    out = out.drop(columns=[k for k in without if k in out])
    for k, r in (extra or {}).items():
        out = out.drop(columns=[k], errors="ignore").join(clip(r).rename(k), how="outer")
    for k in out:  # a leg starts on its first day in its own file; zero after that is a day with no trade
        first = out[k].first_valid_index()
        out.loc[out.index >= first, k] = out.loc[out.index >= first, k].fillna(0.0)
    return out.sort_index()


def weights(L):
    """Walk-forward equal-risk weights, one row a day (constant within a month)."""
    vol = L.rolling(LOOKBACK, min_periods=MIN_HISTORY).std().shift(1)
    month_start = L.index.to_series().groupby(L.index.to_period("M")).transform("first")
    rows = {}
    for day in month_start.unique():
        v = vol.loc[day]
        inv = (1 / v[v > 0]).dropna()
        if inv.empty:
            continue
        for k, f in SCALE.items():
            if k in inv.index:
                inv[k] *= f
        w = inv / inv.sum()
        for _ in range(20):  # cap, then share what was cut among the legs under the cap
            over = w > CAP
            if not over.any():
                break
            spare = (w[over] - CAP).sum()
            w[over] = CAP
            w[~over] += spare * w[~over] / w[~over].sum()
        rows[day] = w
    W = pd.DataFrame(rows).T.reindex(columns=L.columns).fillna(0.0)
    return W.reindex(month_start.values).set_axis(L.index)


def combine(L):
    """The book's daily return (equal-risk weights; scale is arbitrary until the risk layer sets it)."""
    W = weights(L)
    live = W.sum(axis=1) > 0
    return (W * L.fillna(0.0)).sum(axis=1)[live], W


def risk_layer(b):
    """Vol target, then size cuts in a drawdown; uses only days before each day."""
    vol = b.rolling(VOL_LOOKBACK, min_periods=20).std().shift(1) * np.sqrt(252)
    base = VOL_TARGET / (b.expanding(min_periods=LOOKBACK).std().shift(1) * np.sqrt(252))
    size = np.minimum(VOL_TARGET / vol, LEVER_MAX * base).fillna(0.0)
    out = np.zeros(len(b))
    eq, peak = 1.0, 1.0
    for i, (r, s) in enumerate(zip(b.to_numpy(), size.to_numpy())):
        dd = 1 - eq / peak
        s *= 0.25 if dd > DD_QUARTER else (0.5 if dd > DD_HALF else 1.0)
        out[i] = r * s
        eq *= 1 + out[i]
        peak = max(peak, eq)
    return pd.Series(out, index=b.index)[size > 0]


def months(x):
    m = (1 + x).groupby(x.index.to_period("M")).prod() - 1
    return m


def prop(x):
    """FTMO 2-Step with AurumFunded's sizing on daily fraction returns x."""
    import prop_firms as P
    targets, mindays, gaps, wait = P.FIRMS["FTMO 2-Step 10/5"]
    a = (x * 100).to_numpy()
    res = [P.path(a, s, targets, mindays, gaps, wait) for s in range(0, len(a) - 760, 3)]
    t = np.array([d for d, _ in res if d is not None])
    n = len(res)
    return {"pass_12m": float(np.sum(t <= 252) / n) if n else 0.0,
            "failed": float(sum(f for _, f in res) / n) if n else 0.0,
            "median_months": round(float(np.median(t) / 21), 1) if len(t) else None}


def headline(x):
    import prop_firms as P
    m = months(x)
    funded_month = float(m.mean()) * P.SIZE
    return {"sharpe": round(sharpe(x), 2), "sharpe_2018": round(sharpe(x[x.index >= SPLIT]), 2),
            "profitable_months": round(float((m > 0).mean()), 3),
            "profitable_months_2018": round(float((m[m.index >= pd.Period(SPLIT, "M")] > 0).mean()), 3),
            "worst_month": round(float(m.min()), 4), "mean_month": round(float(m.mean()), 4),
            "prop": prop(x),
            "payout_month_usd": round(max(0.0, funded_month) * ACCOUNT * SPLIT_SHARE)}


def run(without=()):
    L = legs(without)
    b, W = combine(L)
    x = risk_layer(b)
    cut = x - x.mean() * 0.3
    last = W.iloc[-1]
    return {"when": datetime.now().isoformat(timespec="seconds"), "ends": str(x.index[-1].date()),
            "legs": {k: {"weight": round(float(last[k]), 3), "sharpe": round(sharpe(L[k]), 2)} for k in L},
            "book_raw_sharpe": round(sharpe(b), 2),
            "backtest": headline(x), "edge_70": headline(cut),
            "rule": f"equal risk, {LOOKBACK}-day vol, monthly, cap {CAP:.0%}; vol target {VOL_TARGET:.0%}, "
                    f"half size past {DD_HALF:.0%} drawdown, quarter past {DD_QUARTER:.0%}"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--without", default="")
    a = ap.parse_args()
    res = run([k for k in a.without.split(",") if k])
    for k, v in res["legs"].items():
        print(f"  {k:24s} weight {v['weight']:5.1%}  Sharpe {v['sharpe']:5.2f}")
    print(f"book Sharpe before the risk layer {res['book_raw_sharpe']}; {res['rule']}")
    for case in ("backtest", "edge_70"):
        h = res[case]
        p = h["prop"]
        print(f"{case:9s} Sharpe {h['sharpe']} (2018+ {h['sharpe_2018']}); profitable months {h['profitable_months']:.0%}"
              f" (2018+ {h['profitable_months_2018']:.0%}); worst month {h['worst_month']:.1%}; FTMO payout within 12m "
              f"{p['pass_12m']:.0%}, failed {p['failed']:.1%}, median {p['median_months']} months; "
              f"payout ~${h['payout_month_usd']:,}/month funded")
    if not a.without:
        OUT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
