"""Meta-label skip filter on the quartet leg (queue item ml_metalabel_quartet_skip).

Primary = the four quartet sub-legs and their ridge sizing (tools/quartet_model.py, tilt 0.5, from 2014) unchanged.
Secondary = lightgbm (max_depth 3, 100 trees, lr 0.05, fixed) on each trade: P(r*mult > 0). Skip if P < 0.45 (fixed).
Features: the model's own FEATS (+ per-leg extras), GVZ level (previous close), mean of the previous 5 trades' result
of the same sub-leg. Walk-forward: refit each year Y on trades before Y (train needs >=150), test 2014+; the label of a
trade is known at its day, so a 5-day purge is applied (train days < Y-01-01 minus 5 days). Seeds 0,1,2.
Trials: 1 config x 3 seeds, plus 3 random-keep controls.

    python research/ml_metalabel_quartet_skip.py
"""
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import quartet_model as qm  # noqa: E402
import book_sim as B  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "ml_metalabel_quartet_skip"
THR = 0.45


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def main():
    warnings.simplefilter("ignore")
    data = qm.datasets()
    data = {k: d[d.day < holdout.START].reset_index(drop=True) for k, d in data.items()}
    gvz = pd.to_numeric(pd.read_csv(ROOT / "marketdata" / "fred" / "GVZCLS.csv", index_col=0, parse_dates=True).iloc[:, 0],
                        errors="coerce").dropna()
    W = {leg: qm.walk(d, qm.FEATS + qm.EXTRA[leg], 2014, 0.5, 0.1) for leg, d in data.items()}
    base = qm.account(data, W)
    # skip masks per seed
    masks = {s: {} for s in (0, 1, 2)}
    aucs = []
    for leg, d in data.items():
        d = d.copy()
        d["gvz"] = gvz.reindex(gvz.index.union(d.day)).ffill().shift(1).reindex(d.day).to_numpy()
        pnl = d.r * d.mult
        d["prev5"] = pnl.shift(1).rolling(5, min_periods=2).mean()
        cols = qm.FEATS + qm.EXTRA[leg] + ["gvz", "prev5"]
        y = (pnl > 0).astype(int).to_numpy()
        X = d[cols].to_numpy(float)
        yr = d.day.dt.year.to_numpy()
        for s in masks:
            P = np.full(len(d), np.nan)
            for Y in range(2014, yr.max() + 1):
                tr = (d.day < pd.Timestamp(Y, 1, 1) - pd.Timedelta(days=5)).to_numpy()
                te = yr == Y
                if te.any() and tr.sum() >= 150 and len(set(y[tr])) == 2:
                    m = lgb.LGBMClassifier(max_depth=3, n_estimators=100, learning_rate=0.05, subsample=0.8,
                                           subsample_freq=1, colsample_bytree=0.8, random_state=s, verbose=-1)
                    m.fit(X[tr], y[tr])
                    P[te] = m.predict_proba(X[te])[:, 1]
            ok = ~np.isnan(P)
            if s == 0:
                a = roc_auc_score(y[ok], P[ok])
                aucs.append((leg, int(ok.sum()), round(a, 3), round(float((P[ok] < THR).mean()), 3)))
            masks[s][leg] = np.where(ok & (P < THR), 0.0, 1.0)
    print("per leg (n, AUC seed0, skip share):", aucs)
    print("plain quartet   2014+ %.2f  <2018 %.2f  2018+ %.2f" % (
        sh(base["2014":].sum(axis=1)), sh(base["2014":"2017"].sum(axis=1)), sh(base["2018":].sum(axis=1))))
    res = {}
    for s in masks:
        Wf = {leg: np.nan_to_num(W[leg], nan=1.0) * masks[s][leg] for leg in data}
        f = qm.account(data, Wf).sum(axis=1)
        res[s] = f
        print("seed", s, "filtered 2014+ %.2f  <2018 %.2f  2018+ %.2f" % (
            sh(f["2014":]), sh(f["2014":"2017"]), sh(f["2018":])))
    rng = np.random.default_rng(0)
    for _ in range(3):
        Wr = {leg: np.nan_to_num(W[leg], nan=1.0) * (rng.random(len(data[leg])) > (1 - masks[0][leg]).mean()) for leg in data}
        r = qm.account(data, Wr).sum(axis=1)
        print("random-keep control 2018+ %.2f" % sh(r["2018":]))
    plain = base.sum(axis=1)
    # book: swap quartet for filtered (seed 0 and worst seed)
    L0 = B.legs()
    w0 = B.weights(L0)
    b0 = (L0 * w0).sum(axis=1)
    print("book plain 2018+ %.3f" % sh(b0["2018":]))
    for s in masks:
        L = B.legs(extra={"quartet": res[s]})
        w = B.weights(L)
        b = (L * w).sum(axis=1)
        print("book seed", s, "2018+ %.3f" % sh(b["2018":]))
    # write the candidate: seed with the lowest 2018+ book-independent Sharpe (worst)
    worst = min(res, key=lambda s: sh(res[s]["2018":]))
    cx = {}
    for cx_name, cost_mult in (("", 1.0), ("_stress", 1.5)):
        data_c = qm.datasets(0.85 * cost_mult, 0.17 * cost_mult)
        data_c = {k: d[d.day < holdout.START].reset_index(drop=True) for k, d in data_c.items()}
        Wc = {leg: qm.walk(d, qm.FEATS + qm.EXTRA[leg], 2014, 0.5, 0.1) for leg, d in data_c.items()}
        Wf = {leg: np.nan_to_num(Wc[leg], nan=1.0) * masks[worst][leg] for leg in data_c}
        cx[cost_mult] = qm.account(data_c, Wf).sum(axis=1)
        cx[cost_mult].rename("r").rename_axis("day").to_csv(OUT / f"{ID}{cex(cost_mult)}.csv")
    print("worst seed", worst, "written; 1.5x 2018+ %.2f" % sh(cx[1.5]["2018":]))


def cex(c):
    return "" if c == 1.0 else "_stress"


if __name__ == "__main__":
    main()
