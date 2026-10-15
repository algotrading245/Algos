"""Meta-labelling the noise-area index leg (research/noise_area_index.py): can a model of features known at the
entry decide which trades to take or how big to make them?  Lopez de Prado's meta-labelling: the rule picks the
side, a model only sizes or filters.  The paper (Zarattini, Aziz, Barbon 2025, sections 4.1-4.5) reports that the
leg's profit varies with the VIX, narrow-range days (NR4/NR7), the weekday and recent declines (RSI).

Features at each entry: half-hour slot, distance beyond the band (in average moves), opening gap, yesterday's and
the last 5 days' return (all signed by the trade and scaled by daily volatility), 14/100-day volatility ratio, VIX
and its 5-day change, distance from the session average, yesterday's range against the 4 days before (NR4),
weekday, trade number in the day.  Label: the trade's net return.  Models: LightGBM (depth 2, 150 trees, learning
rate 0.03, at least 50 trades a leaf) and ridge, refitted every year on the earlier years only (walk-forward from
2014).  Uses: skip trades with a negative forecast, or size = 1 + tilt x erf(z) as in tools/quartet_model.py.

    python research/noise_meta.py

Result (0.75 bp; Sharpe over the days with a trade, 2014-2026 walk-forward), nothing kept:
  S&P 500   plain 0.79 (2014-17) / 1.40 (2018+) / 0.68 (2022+); LightGBM skip 1.39 / 0.70 / 0.14, tilt 0.86 / 1.11 /
            0.49; ridge skip 1.06 / 0.91 / 0.36, tilt 0.77 / 1.15 / 0.38.
  Nasdaq    plain 0.36 / 1.41 / 1.36; LightGBM skip 0.78 / 1.16 / 1.10, tilt 0.57 / 1.34 / 1.36; ridge skip
            0.86 / 1.15 / 1.04, tilt 0.58 / 1.33 / 1.20.
  The models help the early walk-forward years and hurt from 2018: what predicted the trades before 2018 turned
  around later.  The plain rule stays.
"""
import sys
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from noise_area_index import SESSIONS
from overnight_intraday_reversal import matrix

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
FEATS = ["slot", "beyond", "gap", "r1", "r5", "volr", "vix", "dvix", "dtwap", "nr4", "dow", "nth"]


def trades(symbol, vm, cost_bp, look=14, target=0.02, cap=4.0):
    zone, OPEN, CLOSE = SESSIONS[symbol]
    checks = list(range(OPEN + 30, CLOSE, 30))
    days, p = matrix(symbol, zone)
    p = pd.DataFrame(p.astype(float)).ffill(axis=1).to_numpy()
    keep = days.dayofweek < 5
    days, p = days[keep], p[keep]
    o, c = p[:, OPEN], p[:, CLOSE]
    ok = ~np.isnan(o) & ~np.isnan(c) & ~np.isnan(p[:, checks]).any(axis=1)
    days, p, o, c = days[ok], p[ok], o[ok], c[ok]
    sess = p[:, OPEN:CLOSE + 1]
    hi, lo = sess.max(axis=1), sess.min(axis=1)
    rng = (hi - lo) / o
    nr4 = pd.Series(rng).rolling(5).apply(lambda w: float(w[-1] < w[:-1].min()), raw=True).shift(1).to_numpy()
    sig = pd.DataFrame(np.abs(sess / o[:, None] - 1)).rolling(look).mean().shift(1).to_numpy()
    twap = np.cumsum(sess, axis=1) / np.arange(1, sess.shape[1] + 1)
    dret = pd.Series(c / np.r_[np.nan, c[:-1]] - 1)
    dvol = dret.rolling(look).std().shift(1).to_numpy()
    dvol100 = dret.rolling(100).std().shift(1).to_numpy()
    r5 = (pd.Series(c) / pd.Series(c).shift(5) - 1).shift(1).to_numpy()
    vix = pd.read_csv(ROOT / "vixidx" / "^VIX.csv", index_col=0, parse_dates=True).close
    v = vix.shift(1).reindex(days).to_numpy()
    dv = (vix - vix.shift(5)).shift(1).reindex(days).to_numpy()
    rows = []
    for i in range(1, len(days)):
        if np.isnan(sig[i, 0]) or not dvol[i] > 0:
            continue
        h, l = max(o[i], c[i - 1]), min(o[i], c[i - 1])
        size = min(cap, target / dvol[i])
        pos, entry, feat, n = 0, 0.0, None, 0
        for m in checks + [CLOSE]:
            j = m - OPEN
            px = p[i, m]
            ub, lb = h * (1 + vm * sig[i, j]), l * (1 - vm * sig[i, j])
            if pos:
                stop = max(ub, twap[i, j]) if pos > 0 else min(lb, twap[i, j])
                if m == CLOSE or (pos > 0 and px < stop) or (pos < 0 and px > stop):
                    rows.append({**feat, "day": days[i], "ret": size * (pos * (px / entry - 1) - cost_bp * 1e-4)})
                    pos = 0
            if m == CLOSE:
                break
            if pos == 0 and (px > ub or px < lb):
                pos, entry, n = (1 if px > ub else -1), px, n + 1
                band = ub if pos > 0 else lb
                feat = {"slot": j // 30, "beyond": abs(px - band) / (o[i] * sig[i, j]),
                        "gap": pos * (o[i] / c[i - 1] - 1) / dvol[i], "r1": pos * dret[i - 1] / dvol[i],
                        "r5": pos * r5[i] / (dvol[i] * sqrt(5)), "volr": dvol[i] / dvol100[i] if dvol100[i] > 0 else 1.0,
                        "vix": v[i], "dvix": dv[i], "dtwap": pos * (px - twap[i, j]) / (o[i] * sig[i, j]),
                        "nr4": nr4[i], "dow": days[i].dayofweek, "nth": n}
    return pd.DataFrame(rows)


def walk(t, kind, y0=2014):
    import lightgbm as lgb
    from sklearn.linear_model import Ridge
    pred = np.full(len(t), np.nan)
    yr = t.day.dt.year.to_numpy()
    X, y = t[FEATS].to_numpy(float), t.ret.to_numpy()
    X = np.nan_to_num(X)
    for year in range(y0, yr.max() + 1):
        tr, te = yr < year, yr == year
        if not te.any():
            continue
        if kind == "lgbm":
            m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.03, max_depth=2, num_leaves=4,
                                  min_child_samples=50, subsample=0.8, subsample_freq=1, verbose=-1, random_state=1)
            m.fit(X[tr], y[tr])
            pred[te] = m.predict(X[te])
        else:
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            m = Ridge(alpha=len(X[tr]) * 0.1).fit((X[tr] - mu) / sd, y[tr])
            pred[te] = m.predict((X[te] - mu) / sd)
    return pred


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    for sym, vm in (("SPXUSD", 1.5), ("NSXUSD", 1.0)):
        t = trades(sym, vm, 0.75)
        print(f"{sym}: {len(t)} trades")
        for kind in ("lgbm", "ridge"):
            pred = walk(t, kind)
            m = ~np.isnan(pred)
            d = t[m].copy()
            d["pred"] = pred[m]
            # z of the forecast against the forecasts of the previous year (known when trading)
            yr = d.day.dt.year
            ref = d.groupby(yr).pred.agg(["mean", "std"]).shift(1).reindex(yr).to_numpy()
            z = (d.pred.to_numpy() - ref[:, 0]) / ref[:, 1]
            d["z"] = np.nan_to_num(z)
            plain = d.groupby("day").ret.sum()
            filt = d[d.pred > 0].groupby("day").ret.sum().reindex(plain.index).fillna(0)
            tilt = (d.ret * (1 + 0.5 * np.array([erf(v / sqrt(2)) for v in d.z]))).groupby(d.day).sum()
            for name, x in (("plain", plain), ("skip if forecast < 0", filt), ("size tilt 0.5", tilt)):
                print(f"  {kind:5s} {name:22s} Sharpe 2014-17 {sharpe(x[:'2017']):+.2f}, 2018+ {sharpe(x['2018':]):+.2f}, "
                      f"2022+ {sharpe(x['2022':]):+.2f}, trades kept {len(d[d.pred > 0]) / len(d):.0%}" if name.startswith("skip") else
                      f"  {kind:5s} {name:22s} Sharpe 2014-17 {sharpe(x[:'2017']):+.2f}, 2018+ {sharpe(x['2018':]):+.2f}, "
                      f"2022+ {sharpe(x['2022':]):+.2f}")
