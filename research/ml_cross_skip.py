"""Overlap-aware skip filter for the cross leg (queue item ml_cross_skip_fix_overlap).

Primary = cross leg (month-end fix on yen crosses, tools/backtest_hydra.fix with FIXCROSS) unchanged. Event = a month-end
day with a cross trade. Label = day pnl at 1x cost > 0. L2 logistic (C=1, standardised), expanding walk-forward, test
year Y fitted on events before 1 Jan Y minus 10 days, first test year 2012. Skip when P < 0.40 (fixed). Features known
at entry: S&P month-to-date move (abs and sign, which is also the side fix takes), S&P prior-day return, VIX level
(previous close), S&P 20d vol rank, mean pnl of the last 5 fix trades and last 5 cross trades (earlier months only),
fix traded today (always 1 on a cross day, kept out as constant). One config = one trial, plus 3 random-keep controls.

    python research/ml_cross_skip.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import backtest_hydra as H  # noqa: E402
import book_sim as B  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
FE = ["mtd", "mtd_sign", "spx1", "vix", "rvrank", "fix5", "cross5"]
ID = "ml_cross_skip_fix_overlap"


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def main():
    cr = {cx: H.fix(0.005, cost=2.0 * cx, pairs=H.FIXCROSS, name="HYDRA_FIXX", after=False) for cx in (1.0, 1.5)}
    fx = H.fix(0.005, cost=1.2)
    cr = {k: holdout.drop(v) for k, v in cr.items()}
    fx = holdout.drop(fx)
    spx = H.stocks()
    vix = pd.to_numeric(pd.read_csv(ROOT / "marketdata" / "fred" / "VIXCLS.csv", index_col=0, parse_dates=True).iloc[:, 0],
                        errors="coerce").dropna()
    days = cr[1.0].index
    al = days.union(spx.index).union(vix.index)
    ret = spx.pct_change()
    F = pd.DataFrame(index=days)
    F["spx1"] = ret.reindex(al).ffill().shift(1).reindex(days)
    F["vix"] = vix.reindex(al).ffill().shift(1).reindex(days)
    rv = ret.rolling(20).std()
    rr = rv.rolling(250, min_periods=120).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    F["rvrank"] = rr.reindex(al).ffill().shift(1).reindex(days)
    mclose = spx.groupby(spx.index.to_period("M")).last()
    mtd = []
    for d in days:
        p = d.to_period("M")
        before = spx[:d - pd.Timedelta(days=1)]
        mtd.append(before.iloc[-1] / mclose[p - 1] - 1 if p - 1 in mclose.index and len(before) else np.nan)
    F["mtd"] = np.abs(mtd)
    F["mtd_sign"] = np.sign(mtd)
    ev = cr[1.0][cr[1.0] != 0].index
    e = F.loc[ev].copy()
    e["pnl"] = cr[1.0].loc[ev]
    e["pnl15"] = cr[1.5].loc[ev]
    e["fixpnl"] = fx.reindex(ev).fillna(0.0)
    e["fix5"] = e.fixpnl.shift(1).rolling(5, min_periods=2).mean()
    e["cross5"] = e.pnl.shift(1).rolling(5, min_periods=2).mean()
    e = e.dropna()
    e["y"] = (e.pnl > 0).astype(int)
    print("events", len(e), "from", e.index[0].date(), "base rate", round(e.y.mean(), 3))
    P = pd.Series(np.nan, index=e.index)
    for Y in range(2012, 2026):
        tr = e[e.index < pd.Timestamp(Y, 1, 1) - pd.Timedelta(days=10)]
        te = e[(e.index.year == Y)]
        if len(te) == 0 or tr.y.nunique() < 2 or len(tr) < 30:
            continue
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=500))
        m.fit(tr[FE], tr.y)
        P.loc[te.index] = m.predict_proba(te[FE])[:, 1]
    t = e[P.notna()]
    p = P.dropna()
    print("AUC", round(roc_auc_score(t.y, p), 3), "n", len(t), "skip share", round((p < 0.40).mean(), 3))

    def filt(s15=False):
        out = {}
        for cx in (1.0, 1.5):
            s = cr[cx].copy()
            s.loc[p.index[p < 0.40]] = 0.0
            out[cx] = s
        return out
    f = filt()
    rng = np.random.default_rng(0)
    ctrl = []
    for _ in range(3):
        s = cr[1.0].copy()
        k = rng.choice(p.index, int((p < 0.40).sum()), replace=False)
        s.loc[k] = 0.0
        ctrl.append(sh(s[s.index >= "2012-01-01"]))
    for nm, s in (("plain", cr[1.0]), ("filtered", f[1.0])):
        s = s[s.index >= "2012-01-01"]
        print(nm, "Sharpe 2012+", round(sh(s), 2), " <2018", round(sh(s[s.index < "2018-01-01"]), 2),
              " 2018+", round(sh(s[s.index >= "2018-01-01"]), 2), "total", round(s.sum(), 4))
    print("random-keep controls", [round(c, 2) for c in ctrl])
    # book: swap cross for the filtered one
    for nm, s in (("plain", None), ("filtered", f[1.0])):
        L = B.legs(extra=None if s is None else {"cross": s})
        w = B.weights(L)
        bk = (L * w).sum(axis=1)
        print("book", nm, "2018+", round(sh(bk[bk.index >= "2018-01-01"]), 3), "all", round(sh(bk), 3))
    f[1.0].rename("r").rename_axis("day").to_csv(OUT / f"{ID}.csv")
    f[1.5].rename("r").rename_axis("day").to_csv(OUT / f"{ID}_stress.csv")


if __name__ == "__main__":
    main()
