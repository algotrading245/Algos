"""Day-type (trend vs range) classifier gating breakout, noise (by P(trend)) and grid (by P(range)).

Item ml_day_type_gate_breakout_noise_grid. Deviation: the tester data has no per-market M1 for the leg markets in one file,
so the label uses HYDRA_H1 (hourly last bids, AUDUSD USDCAD XAUUSD AUDCAD, hours 1-22): per symbol and day, trend day if
|last-first| >= 0.6 * (max-min) of the hourly closes. Market label = share of the 4 symbols that were trend days (>=0.5 -> 1).
Features known before the day: prior-day share, prior 5d share, prior-day range / 20d median, Asian (hours 1-7) range / 20d
median of the same day (known by 08:00), overnight gap proxy (hour1 open vs prior close) / ATR, weekday, VIX prior close.
Expanding walk-forward, refit yearly from 2012 (train < Y-01-01 minus 10 days); logistic C=1 and LightGBM depth 3 (5 seeds).
Weight = clip((p-0.4)/0.15,0,1) (single pre-set threshold pair). Controls: random scale with the same mean.

    python research/ml_day_type_gate_breakout_noise_grid.py
"""
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import backtest_hydra as H  # noqa: E402
import book_sim as B  # noqa: E402


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def main():
    warnings.simplefilter("ignore")
    L = B.legs()
    days = L.index
    h = H.hourly()
    h = h[h.index < pd.Timestamp("2025-10-13")]
    d = h.index.normalize()
    g = h.groupby(d)
    first, last, hi, lo = g.first(), g.last(), g.max(), g.min()
    rng = (hi - lo)
    trend = ((last - first).abs() >= 0.6 * rng.replace(0, np.nan)).astype(float).where(rng > 0)
    share = trend.mean(axis=1)
    y_all = (share >= 0.5).astype(int)
    rrel = (rng / first).mean(axis=1)
    asian = h[h.index.hour <= 7]
    ga = asian.groupby(asian.index.normalize())
    arng = ((ga.max() - ga.min()) / ga.first()).mean(axis=1)
    gap = ((first - last.shift(1)).abs() / first).mean(axis=1)
    F = pd.DataFrame(index=share.index)
    F["prev"] = share.shift(1)
    F["prev5"] = share.rolling(5).mean().shift(1)
    F["rr"] = (rrel / rrel.rolling(20).median()).shift(1)
    F["asian"] = arng / arng.rolling(20).median().shift(1)
    F["gap"] = gap / rrel.rolling(20).mean().shift(1)
    F["wd"] = F.index.dayofweek
    vix = pd.to_numeric(pd.read_csv(ROOT / "marketdata" / "fred" / "VIXCLS.csv", index_col=0, parse_dates=True).iloc[:, 0],
                        errors="coerce").dropna()
    F["vix"] = vix.reindex(F.index.union(vix.index)).ffill().shift(1).reindex(F.index)
    F["y"] = y_all
    F = F.dropna()
    F = F[F.index.dayofweek < 5]
    print(len(F), "days", F.index.min().date(), F.index.max().date(), "trend share base", round(F.y.mean(), 3))
    FE = ["prev", "prev5", "rr", "asian", "gap", "wd", "vix"]

    def fit_pred(kind, seed):
        p = pd.Series(np.nan, index=F.index)
        for Y in range(2012, 2026):
            tr = F[F.index < pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=10)]
            te = F[(F.index >= f"{Y}-01-01") & (F.index < f"{Y + 1}-01-01")]
            if len(te) == 0:
                continue
            if kind == "logit":
                m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=500))
            else:
                m = lgb.LGBMClassifier(max_depth=3, n_estimators=100, learning_rate=0.05, subsample=0.8, subsample_freq=1,
                                       colsample_bytree=0.8, random_state=seed, verbose=-1)
            m.fit(tr[FE], tr.y)
            p[te.index] = m.predict_proba(te[FE])[:, 1]
        return p

    def book(Lx):
        b, _ = B.combine(Lx)
        return b

    mo = lambda x: (x["2018":].groupby(x["2018":].index.to_period("M")).sum() < 0).sum()
    pb = book(L)
    print(f"plain book: all {sh(pb):.2f} to2017 {sh(pb[:'2017']):.2f} 2018+ {sh(pb['2018':]):.2f} losing months 2018+ {mo(pb)}")
    w = lambda p: ((p - 0.4) / 0.15).clip(0, 1)
    res = []
    rng_ = np.random.default_rng(0)
    for kind, seed in [("logit", 0)] + [("lgbm", s) for s in range(5)]:
        p = fit_pred(kind, seed)
        V = F.loc[p.dropna().index]
        auc = roc_auc_score(V.y, p[V.index])
        wt = w(p).reindex(days)
        wr = w(1 - p).reindex(days)
        out = {}
        for tag, legs_t, legs_r in [("all3", ["breakout", "noise"], ["grid"]), ("trend2", ["breakout", "noise"], []),
                                     ("grid", [], ["grid"])]:
            Lg = L.copy()
            for lg in legs_t:
                Lg[lg] = L[lg] * wt.fillna(1.0)
            for lg in legs_r:
                Lg[lg] = L[lg] * wr.fillna(1.0)
            b = book(Lg)
            out[tag] = (sh(b["2018":]), sh(b[:"2017"]), mo(b))
        print(f"{kind} s{seed}: AUC {auc:.3f} " + " | ".join(f"{k} 2018+ {v[0]:.2f} to2017 {v[1]:.2f} lose {v[2]}" for k, v in out.items()))
        res.append((auc, out["all3"][0]))
    # random-scale controls with the same mean weight
    p = fit_pred("logit", 0)
    mt, mr = w(p).mean(), w(1 - p).mean()
    for s in range(3):
        r = np.random.default_rng(s)
        Lg = L.copy()
        for lg in ["breakout", "noise"]:
            Lg[lg] = L[lg] * (r.random(len(L)) < mt)
        Lg["grid"] = L["grid"] * (r.random(len(L)) < mr)
        b = book(Lg)
        print(f"random control {s}: 2018+ {sh(b['2018':]):.2f} lose {mo(b)} (mean w {mt:.2f}/{mr:.2f})")
    print("trials: 6 models x 3 arms + 3 controls = 21; best AUC", max(r[0] for r in res))


if __name__ == "__main__":
    main()
