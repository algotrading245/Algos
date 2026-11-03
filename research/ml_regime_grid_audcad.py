"""ml_regime_grid_audcad: L2 logistic regression on trend-state features decides whether a new AUDCAD grid cycle may open.
Label: the cycle (unfiltered grid) lost money. Features (daily closes, previous day): ADX(14) proxy, 20d vol rank vs 250d,
distance from 60d mean in 60d sd, 20d return, last cycle depth. Yearly expanding walk-forward from 2012 (cycles that ENDED
before the test year). Skip when P(loss) > 0.5 (one threshold, no sweep). Random-keep control at the same skip rate.
    python research/ml_regime_grid_audcad.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))
import backtest_hydra as B  # noqa: E402
from grid_crosses import hourly  # noqa: E402

CAND = ROOT / "marketdata" / "candidates"
MA, STEP, LEV, COST = 5, 1.0, 4, 1.8


def daily_close(p):
    d = p[p.index.hour == 22]
    d.index = d.index.normalize()
    return d


def features(p):
    c = daily_close(p)
    lc = np.log(c)
    ret = lc.diff()
    up = (c.diff().clip(lower=0)).ewm(alpha=1 / 14).mean()
    dn = (-c.diff().clip(upper=0)).ewm(alpha=1 / 14).mean()
    # directional-movement proxy on closes only (no high/low): |up-dn|/(up+dn)
    adx = ((up - dn).abs() / (up + dn)).ewm(alpha=1 / 14).mean()
    vol20 = ret.rolling(20).std()
    volrank = vol20.rolling(250).rank(pct=True)
    sd60 = ret.rolling(60).std() * np.sqrt(60)
    dist = (lc - lc.rolling(60).mean()) / sd60
    r20 = lc - lc.shift(20)
    f = pd.DataFrame({"adx": adx, "volrank": volrank, "dist": dist.abs(), "r20": r20.abs() / (sd60 * np.sqrt(20 / 60))})
    return f.shift(1)  # known before the day


def grid_cycles(p, ma, step, levels, cost, skipday=None):
    """Same loop as B.grid; returns daily pnl series (per unit risk), cycle list (start_i, end_i, pnl, depth)."""
    mult = 1.0
    wt = np.concatenate([[0.0], np.cumsum(mult ** np.arange(levels))])
    risk = sum(mult ** (k - 1) * (levels + 1 - k) for k in range(1, levels + 1))
    lp = np.log(p.to_numpy())
    avg = pd.Series(lp).rolling(ma * 22).mean().to_numpy()
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40).std() * np.sqrt(22)).shift(1).to_numpy()
    days = p.index.normalize()
    out = np.zeros(len(lp))
    q, dead, unit = 0, False, 1.0
    cyc, cur_start, cur_pnl, cur_depth = [], None, 0.0, 0
    for i in range(len(lp)):
        if q:
            out[i] = np.sign(q) * wt[abs(q)] * r[i] / unit
            cur_pnl += out[i]
        if np.isnan(avg[i]) or np.isnan(dv[i]) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (step * dv[i])
        az, side = abs(z), (1 if z > 0 else -1)
        if dead:
            dead = az >= 0.5
            continue
        if q == 0:
            unit = step * dv[i]
        if az >= levels + 1:
            new, dead = 0, True
        else:
            cur = abs(q) if q * side < 0 else 0
            new = -side * max(min(int(az), levels), min(cur, int(np.ceil(az))))
        if q == 0 and new != 0 and skipday is not None and days[i] in skipday:
            new = 0
        if new != q:
            c = abs(np.sign(new) * wt[abs(new)] - np.sign(q) * wt[abs(q)]) * cost * 1e-4 / 2 / unit
            out[i] -= c
            cur_pnl -= c
            if q == 0:
                cur_start, cur_pnl, cur_depth = i, -c, 0
            cur_depth = max(cur_depth, abs(new))
            if new == 0 and cur_start is not None:
                cyc.append((cur_start, i, cur_pnl, cur_depth))
                cur_start = None
            q = new
    return pd.Series(out, index=p.index).groupby(days).sum() / risk, cyc, days


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    p = hourly("AUDCAD")
    F = features(p).dropna()
    base1, cyc, days = grid_cycles(p, MA, STEP, LEV, COST)
    cdf = pd.DataFrame(cyc, columns=["s", "e", "pnl", "depth"])
    cdf["sday"] = days[cdf.s.to_numpy()]
    cdf["eday"] = days[cdf.e.to_numpy()]
    cdf["loss"] = (cdf.pnl < 0).astype(int)
    cdf["lastdepth"] = cdf.depth.shift(1)
    cdf = cdf.join(F, on="sday").dropna()
    cols = ["adx", "volrank", "dist", "r20", "lastdepth"]
    print(f"cycles {len(cdf)} from {cdf.sday.min().date()}; loss share {cdf.loss.mean():.2f}")
    # daily feature table incl. lastdepth (carried forward as of that day)
    ld = cdf.set_index("eday").depth.groupby(level=0).last()
    Fd = F.copy()
    Fd["lastdepth"] = ld.reindex(Fd.index.union(ld.index)).ffill().reindex(Fd.index).shift(1).fillna(1).to_numpy()
    skip, oof_y, oof_p = set(), [], []
    for y in range(2013, 2026):
        tr = cdf[cdf.eday < pd.Timestamp(f"{y}-01-01")]
        te = cdf[(cdf.sday >= f"{y}-01-01") & (cdf.sday < f"{y+1}-01-01")]
        if len(tr) < 30 or tr.loss.nunique() < 2:
            continue
        sc = StandardScaler().fit(tr[cols])
        m = LogisticRegression(C=1.0, max_iter=500).fit(sc.transform(tr[cols]), tr.loss)
        if len(te) and te.loss.nunique() > 0:
            oof_y += list(te.loss)
            oof_p += list(m.predict_proba(sc.transform(te[cols]))[:, 1])
        dy = Fd[(Fd.index >= f"{y}-01-01") & (Fd.index < f"{y+1}-01-01")]
        pr = m.predict_proba(sc.transform(dy[cols]))[:, 1]
        skip |= set(dy.index[pr > 0.5])
    auc = roc_auc_score(oof_y, oof_p)
    print(f"out-of-fold AUC {auc:.3f} on {len(oof_y)} cycles; skip days {len(skip)}")
    base = {c: 0.035 * grid_cycles(p, MA, STEP, LEV, COST * c)[0] for c in (1, 1.5, 2)}
    filt = {c: 0.035 * grid_cycles(p, MA, STEP, LEV, COST * c, skip)[0] for c in (1, 1.5, 2)}
    # share of starts skipped
    _, cyc_f, _ = grid_cycles(p, MA, STEP, LEV, COST, skip)
    print(f"cycles unfiltered {len(cyc)} filtered {len(cyc_f)}")
    b, g = base[1], filt[1]
    print(f"base   halves {sh(b[:'2017']):.2f}/{sh(b['2018':]):.2f}")
    print(f"filter halves {sh(g[:'2017']):.2f}/{sh(g['2018':]):.2f}  1.5x {sh(filt[1.5]['2018':]):.2f} 2x {sh(filt[2]['2018':]):.2f}")
    # random-keep control at same skip rate on the test years
    rate = len(skip) / len(Fd[Fd.index >= "2013-01-01"])
    rs = []
    alld = Fd[Fd.index >= "2013-01-01"].index
    for seed in range(5):
        rng = np.random.default_rng(seed)
        sk = set(alld[rng.random(len(alld)) < rate])
        rs.append(sh((0.035 * grid_cycles(p, MA, STEP, LEV, COST, sk)[0])['2018':]))
    print(f"skip day rate {rate:.2f}; random-skip control 2018+ Sharpe {np.round(rs,2)} mean {np.mean(rs):.2f}")
    hy = g[g.index.dayofweek < 5]
    hy.rename("r").rename_axis("day").to_csv(CAND / "ml_regime_grid_audcad.csv")
    filt[1.5][filt[1.5].index.dayofweek < 5].rename("r").rename_axis("day").to_csv(CAND / "ml_regime_grid_audcad_stress.csv")
