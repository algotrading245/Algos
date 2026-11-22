"""Meta-label filter on the after, morning and fall legs (queue item ml_metalabel_after_morning_fall).

Primary = the three legs of tools/backtest_hydra.py unchanged. Event = (leg, day) with a trade. Label = the leg's
day pnl at 1x costs > 0. One pooled logistic regression (L2, C=1, standardised features) with leg dummies, expanding
walk-forward: test year Y fitted on events before 1 Jan Y minus 10 days, first test year 2012. Skip when P < 0.40
(fixed, no tuning). Features known before the event: S&P prior-day return, S&P 5d return, VIX level and its 5d change
(VIXCLS, the previous close), S&P 20d realised-vol rank over 250 days, day of week, days since the last FOMC date.
(The overnight gap in the traded market is replaced by the S&P prior-day return: no gap series is shared by the
three legs.) One config, one trial (plus 3 random-keep controls).

    python research/metalabel_afmofa.py
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
FE = ["spx1", "spx5", "vix", "dvix5", "rvrank", "wd", "dsf", "is_fall", "is_morning"]


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def main():
    legs = {}
    for cx in (1.0, 1.5):
        legs[cx] = {
            "fall": H.fall(cost=1.2 * cx), "morning": H.morning(costx=cx), "after": H.after(costx=cx)}
    spx = H.stocks()
    vix = pd.read_csv(ROOT / "marketdata" / "fred" / "VIXCLS.csv", index_col=0, parse_dates=True).iloc[:, 0]
    vix = pd.to_numeric(vix, errors="coerce").dropna()
    fomc = pd.to_datetime(pd.read_csv(ROOT / "marketdata" / "fomc" / "fomc_dates.csv").date)
    days = legs[1.0]["fall"].index
    al = days.union(spx.index).union(vix.index)
    ret = spx.pct_change()
    F = pd.DataFrame(index=days)
    F["spx1"] = ret.reindex(al).ffill().shift(1).reindex(days)
    F["spx5"] = (spx / spx.shift(5) - 1).reindex(al).ffill().shift(1).reindex(days)
    F["vix"] = vix.reindex(al).ffill().shift(1).reindex(days)
    F["dvix5"] = (vix / vix.shift(5) - 1).reindex(al).ffill().shift(1).reindex(days)
    rv = ret.rolling(20).std()
    rr = rv.rolling(250, min_periods=120).apply(lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    F["rvrank"] = rr.reindex(al).ffill().shift(1).reindex(days)
    F["wd"] = days.dayofweek
    fo = fomc[fomc < days[-1]].sort_values().to_numpy()
    idx = np.searchsorted(fo, days.to_numpy(), side="right") - 1
    F["dsf"] = np.where(idx >= 0, (days.to_numpy() - fo[np.maximum(idx, 0)]).astype("timedelta64[D]").astype(float), np.nan)
    rows = []
    for name, s in legs[1.0].items():
        s15 = legs[1.5][name]
        ev = s[s != 0].index
        e = F.loc[ev].copy()
        e["leg"] = name
        e["pnl"] = s.loc[ev]
        e["pnl15"] = s15.loc[ev]
        e["is_fall"] = float(name == "fall")
        e["is_morning"] = float(name == "morning")
        rows.append(e)
    E = pd.concat(rows).reset_index().rename(columns={"index": "day"})
    E = E[E.day <= "2025-10-12"]
    E = holdout.drop(E.set_index("day")).reset_index()
    E = E.dropna(subset=FE).reset_index(drop=True)
    E["y"] = (E.pnl > 0).astype(int)
    print(len(E), "events", E.groupby("leg").size().to_dict(), E.day.min().date(), E.day.max().date())
    p = pd.Series(np.nan, index=E.index)
    for Y in range(2012, 2026):
        tr = E[E.day < pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=10)]
        te = E[(E.day >= f"{Y}-01-01") & (E.day < f"{Y + 1}-01-01")]
        if len(te) == 0 or len(tr) < 40 or tr.y.nunique() < 2:
            continue
        m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=500))
        m.fit(tr[FE], tr.y)
        p[te.index] = m.predict_proba(te[FE])[:, 1]
    E["p"] = p
    V = E.dropna(subset=["p"])
    print(f"OOS events {len(V)} AUC {roc_auc_score(V.y, V.p):.3f} base hit {V.y.mean():.3f} mean p {V.p.mean():.3f}")
    for lg, g in V.groupby("leg"):
        print("  ", lg, len(g), "AUC", round(roc_auc_score(g.y, g.p), 3) if g.y.nunique() > 1 else None)
    keep = (V.p >= 0.40).astype(float)
    print("skip rate", round(1 - keep.mean(), 3))
    E["keep"] = 1.0
    E.loc[V.index, "keep"] = keep
    # daily book-scaled series: filtered minus plain, applied on top of the book legs
    book = B.legs()
    res = {}
    for cx, col in ((1.0, "pnl"), (1.5, "pnl15")):
        tot = pd.Series(0.0, index=days)
        plain = pd.Series(0.0, index=days)
        for name in ("fall", "morning", "after"):
            raw = legs[1.0][name]
            bl = book[name].reindex(days).fillna(0.0)
            k = bl.std() / raw.std()
            d = E[E.leg == name].set_index("day")
            filt = (d[col] * d.keep).groupby(level=0).sum().reindex(days).fillna(0.0)
            pl = legs[cx][name]
            # cost-stressed plain also differs from the 1x book leg: shift by (pl - raw) * k
            tot += (bl + (pl - raw) * k) * 0 + filt * k
            plain += bl + (pl - raw) * k
        res[cx] = (tot, plain)
    for cx in (1.0, 1.5):
        t, pl = res[cx]
        t = t[t.index.dayofweek < 5]
        pl = pl[pl.index.dayofweek < 5]
        print(f"cost {cx}x: filtered {sh(t):.2f} (to2017 {sh(t[:'2017']):.2f}, 2018+ {sh(t['2018':]):.2f}) | plain "
              f"{sh(pl):.2f} ({sh(pl[:'2017']):.2f}/{sh(pl['2018':]):.2f})")
    for seed in range(3):
        rng = np.random.default_rng(seed)
        kk = pd.Series(np.where(rng.random(len(E)) < (1 - keep.mean()) * (E.keep == 1).mean() * 0 + (E.keep == 0).mean(), 0.0, 1.0), index=E.index)
        t = 0
        for name in ("fall", "morning", "after"):
            raw = legs[1.0][name]
            k = book_k = B.legs()[name].reindex(days).fillna(0.0).std() / raw.std()
            d = E[E.leg == name].set_index("day")
            kn = kk[E.leg == name].to_numpy()
            t = t + (d.pnl * kn).groupby(level=0).sum().reindex(days).fillna(0.0) * k
        t = t[t.index.dayofweek < 5]
        print(f"  random keep seed {seed}: {sh(t):.2f} ({sh(t[:'2017']):.2f}/{sh(t['2018':]):.2f})")
    # losing months from 2018
    t, pl = res[1.0]
    for nm, x in (("filtered", t), ("plain", pl)):
        mo = x["2018":].groupby(x["2018":].index.to_period("M")).sum()
        print(nm, "losing months from 2018:", int((mo < 0).sum()), "of", len(mo), "sum of losses", round(mo[mo < 0].sum(), 4))
    t1, _ = res[1.0]
    t15, _ = res[1.5]
    for x, nm in ((t1, "ml_metalabel_after_morning_fall"), (t15, "ml_metalabel_after_morning_fall_stress")):
        x = x[x.index.dayofweek < 5].copy()
        x.index.name = "day"
        x.name = "r"
        x.to_csv(OUT / f"{nm}.csv", header=True)
    print("written")


if __name__ == "__main__":
    main()
