"""The sizing model of AurumQuartet: a small linear model that scores each trade of a leg and sizes it up or down.

Method (meta-labelling): the four rules of tools/backtest_quartet.py decide when and which way to trade; the model
only decides how much. For every trade it reads a few numbers known at the entry, all signed by the trade's side:
  dayret  yesterday's daily return                     intra   move from yesterday's close to the entry
  rng     today's high minus low so far                h1      move over the hour before the entry
  mom5    return of the five days before today         volr    log of 20-day over 250-day daily volatility
  mon, fri  day-of-week flags
  dip only:  z (size of the falling M15 bar in standard deviations), tod (time of day)
  bell only: sigk (the move into the bell in average moves)
The first five are divided by the mean absolute daily return of the previous 20 days. A ridge regression of the
trade result (in units of the stop, clipped to +-1) on the standardised features gives a score; the size of the
trade is 1 + tilt x erf(z / sqrt 2), z being the score in standard deviations of the training scores. So the size
runs from 1 - tilt to 1 + tilt and is 1 on average.

Test: each year from --from on is sized by a model fitted on the earlier years only (expanding window). The lines
printed are the plain rule against the sized rule on those years. "overlay" is the extra result from the sizing.
--mql prints the fit on all trades as the arrays of mql5/Experts/_archive/AurumQuartet/AurumQuartet.mq5.

The account lines are built from the single trades and differ a little from tools/backtest_quartet.py, which
drops the first weeks of the gold leg.

Usage: python tools/quartet_model.py [--tilt 0.5] [--from 2014] [--alpha 0.1] [--gold 0.17] [--fx 0.85] [--mql]
"""
import argparse
import warnings
from math import erf, sqrt
import numpy as np
import pandas as pd

import backtest_quartet as q

SIZE = {"dip": 1.55, "bell": 0.027, "tokyo": 0.020, "meridian": 0.010}
FEATS = ["dayret", "intra", "rng", "h1", "mom5", "volr", "mon", "fri"]
EXTRA = {"dip": ["z", "tod"], "bell": ["sigk"], "tokyo": [], "meridian": []}
NF = 10                                                    # columns of the arrays in the EA


def table(T):
    """Day x minute arrays of one instrument and its daily closes and volatilities, weekdays only."""
    days = T["open"].index
    keep = days.dayofweek < 5
    A = {f: T[f].to_numpy(dtype=float)[keep] for f in ("open", "high", "low", "last")}
    A["days"] = days[keep]
    dc = pd.Series(A["last"][:, 1439], index=A["days"]).ffill()
    dr = dc.pct_change()
    A["dc"] = dc.to_numpy()
    A["dv"] = dr.abs().rolling(20, min_periods=10).mean().shift(1).to_numpy()
    A["dv250"] = dr.abs().rolling(250, min_periods=60).mean().shift(1).to_numpy()
    return A


def features(A, day, a, side):
    """Features known at the open of minute 'a' of 'day' for a trade in direction 'side'; None while history is short."""
    pos = A["days"].get_indexer([day])[0]
    if pos < 7:
        return None
    e, dc, dv = A["open"][pos, a], A["dc"], A["dv"][pos]
    if np.isnan(e):
        e = A["last"][pos, a]
    if np.isnan(e) or not dv > 0:
        return None
    hi, lo = np.nanmax(A["high"][pos, :a]), np.nanmin(A["low"][pos, :a])
    p60 = A["last"][pos, a - 61] if a >= 61 else np.nan
    return {"dayret": side * (dc[pos - 1] / dc[pos - 2] - 1) / dv,
            "intra": side * (e / dc[pos - 1] - 1) / dv,
            "rng": (hi - lo) / e / dv,
            "h1": side * (e / p60 - 1) / dv,
            "mom5": side * (dc[pos - 1] / dc[pos - 6] - 1) / (dv * sqrt(5)),
            "volr": np.log(dv / A["dv250"][pos]),
            "mon": float(day.dayofweek == 0), "fri": float(day.dayofweek == 4)}


def datasets(fx=0.85, gold=0.17):
    """One frame per leg: day, result r, multiplier of the result in the account (the dip's leverage) and features."""
    out = {}
    q._gold_mid()
    A = table(q.bb._cache)
    # dip: the trades of backtest_orient.dips and the leverage of backtest_orient.run
    b = q.bo._bars("M15")
    lr = np.log(b.close).diff()
    z = pd.Series((lr / lr.rolling(96).std().shift(1)).to_numpy(), index=b.dt.to_numpy()).shift(1)
    D = q.bo._bars("D1")
    vol = pd.Series((D.close.pct_change().ewm(span=30).std() * np.sqrt(252)).shift(1).to_numpy(), index=D.dt.dt.normalize())
    rows = []
    for when, ret in q.bo.dips(bp=0.0, cost=gold + 0.05).itertuples(index=False):
        when = pd.Timestamp(when)
        day, a = when.normalize(), when.hour * 60 + when.minute
        f = features(A, day, a, 1)
        lev = min(4.0, 0.30 / vol.get(day, np.nan))
        if f is not None and lev > 0:
            rows.append({"day": day, "r": ret, "mult": lev, **f, "z": -z.get(when, np.nan), "tod": (a - 60) / 420.0})
    out["dip"] = pd.DataFrame(rows)
    rows = []
    for day, x in q.bb.trades(cost=gold, spread=0.0).iterrows():
        f = features(A, day, 1380, x.side)
        if f is not None:
            pos = A["days"].get_indexer([day])[0]
            rows.append({"day": day, "r": x.r, "mult": 1.0, **f, "sigk": abs(A["open"][pos, 1380] - A["last"][pos, 1364]) / x.ref})
    out["bell"] = pd.DataFrame(rows)
    del A
    q.bb._cache.clear()
    q.bo._cache.clear()
    for leg, sym in (("tokyo", "USDJPY"), ("meridian", "EURUSD")):
        t = q.bt.trades(got=1, cost=fx) if leg == "tokyo" else q.bm.trades(cost=fx)
        A = table(q.bm._tables(sym))
        rows = []
        for day, x in t.iterrows():
            f = features(A, day, int(x.a), -1)
            if f is not None:
                rows.append({"day": day, "r": x.r, "mult": 1.0, **f})
        out[leg] = pd.DataFrame(rows)
        del A
        q.bm._cache.pop(sym)
    return out


def fit(X, r, alpha):
    """Ridge fit: feature means and deviations, coefficients, intercept, mean and deviation of the fitted scores."""
    mu, sd = np.nanmean(X, 0), np.nanstd(X, 0)
    sd[~(sd > 0)] = 1.0
    A = np.clip(np.nan_to_num((X - mu) / sd), -4, 4)
    y = np.clip(r, -1, 1)
    Ac = A - A.mean(0)
    beta = np.linalg.solve(Ac.T @ Ac + alpha * len(A) * np.eye(A.shape[1]), Ac.T @ (y - y.mean()))
    icpt = y.mean() - A.mean(0) @ beta
    s = icpt + A @ beta
    return mu, sd, beta, icpt, s.mean(), s.std()


def weight(m, X, tilt):
    """Size of each trade in X under the fitted model m."""
    mu, sd, beta, icpt, sm, ss = m
    s = icpt + np.clip(np.nan_to_num((X - mu) / sd), -4, 4) @ beta
    return 1.0 + tilt * np.array([erf(v / sqrt(2)) for v in (s - sm) / ss]) if ss > 0 else np.ones(len(X))


def walk(d, cols, y0, tilt, alpha):
    """Walk-forward sizes: every year from y0 sized by the fit on the earlier years. NaN where there was no model."""
    w = np.full(len(d), np.nan)
    yr = d.day.dt.year.to_numpy()
    X, r = d[cols].to_numpy(float), d.r.to_numpy()
    for year in range(y0, yr.max() + 1):
        tr, te = yr < year, yr == year
        if te.any() and tr.sum() >= 50:
            w[te] = weight(fit(X[tr], r[tr], alpha), X[te], tilt)
    return w


def tstat(x):
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else 0.0


def account(data, W):
    """Daily return of the account from the single trades, each sized by W[leg] (1 where W is missing)."""
    out = {}
    for leg, d in data.items():
        w = np.nan_to_num(W[leg], nan=1.0) if leg in W else 1.0
        out[leg] = (SIZE[leg] * d.r * d.mult * w).groupby(d.day).sum()
    return pd.DataFrame(out).fillna(0.0).sort_index().loc[q.START:]


def line(D, y0, label):
    r = D.sum(axis=1)
    x = r[str(y0):]
    eq = (1 + x).cumprod()
    print(f"{label:12s} from {y0}: return {100 * 252 * x.mean():5.1f}%/yr, vol {100 * x.std() * np.sqrt(252):4.1f}%, "
          f"Sharpe {q.sharpe(x):.2f} (from 2018 {q.sharpe(r['2018':]):.2f}, from 2022 {q.sharpe(r['2022':]):.2f}), "
          f"maxDD {100 * (1 - eq / eq.cummax()).max():4.1f}%  legs from 2018: "
          + "  ".join(f"{k} {q.sharpe(D[k]['2018':]):+.2f}" for k in D))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tilt", type=float, default=0.5, help="how far the size moves from 1, between 0 and 1")
    ap.add_argument("--from", dest="y0", type=int, default=2014, help="first year sized by the model")
    ap.add_argument("--alpha", type=float, default=0.1, help="ridge penalty per trade")
    ap.add_argument("--gold", type=float, default=0.17, help="round-trip cost of gold at the bell, price units per oz")
    ap.add_argument("--fx", type=float, default=0.85, help="round-trip cost of the currency legs, basis points")
    ap.add_argument("--mql", action="store_true", help="print the fit on all trades as arrays for the EA")
    a = ap.parse_args()
    warnings.simplefilter("ignore")
    data = datasets(a.fx, a.gold)
    W = {}
    print(f"walk-forward from {a.y0}, tilt {a.tilt}: results in 1e-4 of the leg's unit (dip: return x leverage, others: stops)")
    for leg, d in data.items():
        W[leg] = walk(d, FEATS + EXTRA[leg], a.y0, a.tilt, a.alpha)
        m = ~np.isnan(W[leg])
        r, w = (d.r * d.mult).to_numpy()[m], W[leg][m]
        lo = w < 1 - a.tilt / 3
        print(f"  {leg:8s} trades {m.sum():4d}  plain mean {1e4 * r.mean():+7.1f}  sized mean {1e4 * (w * r).mean():+7.1f}  "
              f"mean size {w.mean():.3f}  overlay t {tstat((w - 1) * r):+.2f}, with the mean size removed {tstat((w - w.mean()) * r):+.2f}  "
              f"lowest third of sizes: mean {1e4 * r[lo].mean():+7.1f}, the rest {1e4 * r[~lo].mean():+7.1f}")
    P, M = account(data, {}), account(data, W)
    line(P, a.y0, "plain rule")
    line(M, a.y0, "with model")
    o = (M - P).sum(axis=1)[str(a.y0):]
    o = o[o != 0]
    print(f"overlay on the account: {100 * o.sum() / ((o.index[-1] - o.index[0]).days / 365.25):+.1f}%/yr, t {tstat(o):+.2f} over {len(o)} days")
    for k in data:
        line(account(data, {k: W[k]}), a.y0, f"only {k}")
    if a.mql:
        rows = {k: [] for k in ("MU", "SD", "BETA", "ICPT", "MEAN", "DEV")}
        pad = lambda v, fill: list(v) + [fill] * (NF - len(v))
        for leg, d in data.items():
            mu, sd, beta, icpt, sm, ss = fit(d[FEATS + EXTRA[leg]].to_numpy(float), d.r.to_numpy(), a.alpha)
            for k, v in (("MU", pad(mu, 0.0)), ("SD", pad(sd, 1.0)), ("BETA", pad(beta, 0.0))):
                rows[k].append("{" + ",".join(f"{x:.6g}" for x in v) + "}")
            for k, v in (("ICPT", icpt), ("MEAN", sm), ("DEV", ss)):
                rows[k].append(f"{v:.6g}")
        print(f"// fitted by tools/quartet_model.py on {', '.join(f'{len(d)} {k}' for k, d in data.items())} trades")
        for k in ("MU", "SD", "BETA"):
            print(f"const double M_{k}[4][{NF}]={{" + (",\n" + " " * (24 + len(k))).join(rows[k]) + "};")
        for k in ("ICPT", "MEAN", "DEV"):
            print(f"const double M_{k}[4]={{" + ",".join(rows[k]) + "};")
