"""Meta-label the 5 desk benchmark edges. Kill rule 1: out-of-sample AUC >= 0.55 WITHIN each edge.
Walk-forward yearly from 2012 (train = trades closed before the test year: purge = max holding, 1-bar embargo).
Models: expanding conditional frequency (trend x vol cell), logistic, LightGBM (3 seeds). Trials = 5 edges x 5 models.
"""
import sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
from desk import edges, paths, sandbox
from desk.edges import base
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
import lightgbm as lgb

cfg = paths.config()
NAMES = ["bollinger_reversion", "donchian_trend", "london_breakout", "ma_cross", "rsi2_reversion"]
FEATS = ["r20", "r60", "r120", "vs200", "atrratio", "volrank", "stopatr", "hour", "dow", "hit20"]


def trades_for(name):
    e = edges.get(name)
    rows = []
    for m in e["markets"]:
        spec = cfg["instruments"][m]
        df = base.hist_bars(m, e["tf"], cfg).reset_index(drop=True)
        sigs = edges.run(name, df, None, sandbox.context(e, m, cfg))
        tr = sandbox.simulate(df, sigs, sandbox.costs(df, spec["cost"], spec.get("class")))
        c = df["close"].values.astype(float)
        a = base.atr(df, 14).values
        a100 = pd.Series(a).rolling(100).mean().values
        s200 = pd.Series(c).rolling(200).mean().values
        rel = pd.Series(a / c).rolling(500, min_periods=100).rank(pct=True).values
        t = df["time"].values
        sigmap = {}
        for s in sigs:
            sigmap.setdefault(s["i"], s)
        tt = np.searchsorted(t, [x["t"] for x in tr])
        hist = []
        for x, j in zip(tr, tt):
            i = j - 1
            if i < 130 or not np.isfinite(a[i]) or a[i] <= 0:
                continue
            d = 1 if x["side"] == "buy" else -1
            s = sigmap.get(i)
            stopatr = abs(c[i] - s["stop"]) / a[i] if s else np.nan
            ts = pd.Timestamp(int(t[i]), unit="s")
            prior = [h for h in hist if h[0] < x["t"]][-20:]
            hit = np.mean([h[1] > 0 for h in prior]) if len(prior) >= 5 else 0.5
            rows.append(dict(market=m, t=x["t"], out=x["out"], r=x["r"], side=d,
                             r20=d * (c[i] - c[i - 20]) / a[i], r60=d * (c[i] - c[i - 60]) / a[i],
                             r120=d * (c[i] - c[i - 120]) / a[i],
                             vs200=d * (c[i] - s200[i]) / a[i] if np.isfinite(s200[i]) else 0.0,
                             atrratio=a[i] / a100[i] if np.isfinite(a100[i]) else 1.0,
                             volrank=rel[i] if np.isfinite(rel[i]) else 0.5, stopatr=stopatr,
                             hour=ts.hour, dow=ts.dayofweek, hit20=hit))
            hist.append((x["out"], x["r"]))
            hist.sort()
    return pd.DataFrame(rows).sort_values("t").reset_index(drop=True)


def sharpe(d):
    d = np.asarray(d, float)
    return float(d.mean() / d.std() * np.sqrt(252)) if len(d) > 5 and d.std() > 0 else float("nan")


def daily(df, mask):
    s = df[mask].assign(day=lambda x: pd.to_datetime(x["out"], unit="s").dt.normalize()).groupby("day")["r"].sum()
    return s


res = {}
for name in NAMES:
    df = trades_for(name)
    df["year"] = pd.to_datetime(df["t"], unit="s").dt.year
    df["y"] = (df["r"] > 0).astype(int)
    df["stopatr"] = df["stopatr"].fillna(df["stopatr"].median())
    print(f"\n== {name}: {len(df)} trades, win {df.y.mean():.3f}, avg_r {df.r.mean():.3f}")
    preds = {k: pd.Series(np.nan, index=df.index) for k in ["freq", "logit", "gbm0", "gbm1", "gbm2"]}
    for yr in range(2012, 2026):
        te = df.index[df.year == yr]
        tr = df.index[(df.out < pd.Timestamp(f"{yr}-01-01").timestamp() - 86400)]
        if len(te) == 0 or len(tr) < 100:
            continue
        # conditional frequency: trend sign x vol tercile cell
        def cell(d):
            return (d["r60"] > 0).astype(int) * 3 + np.minimum((d["volrank"] * 3).astype(int), 2)
        ct = cell(df.loc[tr]); g = df.loc[tr].groupby(ct)["y"].agg(["sum", "count"])
        base_p = df.loc[tr, "y"].mean()
        cte = cell(df.loc[te])
        preds["freq"].loc[te] = [(g.loc[k, "sum"] / g.loc[k, "count"]) if k in g.index and g.loc[k, "count"] >= 30 else base_p
                                 for k in cte]
        X = df.loc[tr, FEATS].values; Xt = df.loc[te, FEATS].values
        sc = StandardScaler().fit(X)
        if df.loc[tr, "y"].nunique() > 1:
            lr = LogisticRegression(C=0.1, max_iter=500).fit(sc.transform(X), df.loc[tr, "y"])
            preds["logit"].loc[te] = lr.predict_proba(sc.transform(Xt))[:, 1]
            for sd in range(3):
                m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.03, num_leaves=7, min_child_samples=40,
                                       subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=sd, verbose=-1)
                m.fit(X, df.loc[tr, "y"])
                preds[f"gbm{sd}"].loc[te] = m.predict_proba(Xt)[:, 1]
    ok = preds["freq"].notna()
    print(f"  OOS trades {ok.sum()}, base win {df.y[ok].mean():.3f}, plain avg_r {df.r[ok].mean():.3f}")
    best = 0
    for k, p in preds.items():
        o = p.notna()
        if o.sum() < 100 or df.y[o].nunique() < 2:
            continue
        auc = roc_auc_score(df.y[o], p[o])
        best = max(best, auc)
        # skip lowest 30% by score, compare mean r
        thr = p[o].quantile(0.3)
        keep = o & (p >= thr)
        print(f"  {k}: AUC {auc:.3f}  keep70% avg_r {df.r[keep].mean():.3f} vs plain {df.r[o].mean():.3f}")
    res[name] = best
    if name == "london_breakout":  # kill rules 2 and 4 on the only edge near AUC 0.55 (mean of 3 gbm seeds)
        p = (preds["gbm0"] + preds["gbm1"] + preds["gbm2"]) / 3
        o = p.notna(); keep = o & (p >= p[o].quantile(0.3))
        dates = pd.to_datetime(df["out"], unit="s")
        for lab, m in (("to2017", dates.dt.year <= 2017), ("2018+", dates.dt.year >= 2018)):
            print(f"  {lab}: plain SR {sharpe(daily(df, o & m)):.2f} filtered SR {sharpe(daily(df, keep & m)):.2f}")
        rng = np.random.default_rng(0); srs = []
        for _ in range(100):
            rk = o & (rng.random(len(df)) >= 0.3)
            srs.append(sharpe(daily(df, rk)))
        print(f"  all OOS: plain {sharpe(daily(df, o)):.2f} filtered {sharpe(daily(df, keep)):.2f} random-skip p95 {np.percentile(srs, 95):.2f}")
print("\nbest OOS AUC per edge:", {k: round(v, 3) for k, v in res.items()})
print("edges with AUC>=0.55:", [k for k, v in res.items() if v >= 0.55])
