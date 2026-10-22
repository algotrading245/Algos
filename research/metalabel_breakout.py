"""Meta-labeling sizing of the London-breakout leg (queue item ml_metalabel_breakout_size).

Primary model = research/london_breakout.py rules unchanged (both sides, stop at the other side of the range, exit
18:00).  Trades pooled over USDJPY, EURJPY, GBPUSD, XAUUSD, EURUSD at real costs; the sized leg is USDJPY (the leg
in the book).  Meta label = net R > 0.  Features known at entry.  Expanding walk-forward: each test year Y is
predicted by a model fitted on trades up to 10 days before 1 Jan Y; first test year 2012.
Size = 0.5 + 0.5 p (p from the model, never above 1), skip when p < 0.40 (variant B).
Controls: plain leg, plain leg x mean size, random keep at the same skip rate (3 seeds).
Trials counted: 2 models x 2 size rules = 4, plus the random seeds (3).

    python research/metalabel_breakout.py
"""
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

DATA = ROOT / "marketdata" / "histdata"
OUT = ROOT / "marketdata" / "candidates"
MK = {"USDJPY": 1.2, "EURJPY": 1.4, "GBPUSD": 1.0, "XAUUSD": 1.0, "EURUSD": 0.8}
FEATS = ["atr_ratio", "rv_pct", "dist20", "hour", "wd", "hit5", "prev_rng", "mend", "side", "width"]


def trades(s):
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz")
    t = pd.to_datetime(m.time, unit="s")
    m = m[t.dt.dayofweek < 5]
    g = m.assign(time=m.time // 300 * 300).groupby("time").agg(open=("open", "first"), high=("high", "max"),
                                                               low=("low", "min"), close=("close", "last"))
    g["day"] = pd.to_datetime(g.index, unit="s").normalize()
    g["h"] = (g.index % 86400) / 3600
    # daily bars (server day) for past-only context
    dd = g.groupby("day").agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    pc = dd.close.shift(1)
    tr = pd.concat([dd.high - dd.low, (dd.high - pc).abs(), (dd.low - pc).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().shift(1)           # known before the day
    atr100 = tr.rolling(100).mean().shift(1)
    ret = dd.close.pct_change()
    rv20 = ret.rolling(20).std().shift(1)
    rv_pct = rv20.rolling(250, min_periods=60).rank(pct=True)
    mean20 = dd.close.rolling(20).mean().shift(1)
    prev_rng = ((dd.high - dd.low) / atr14).shift(1)
    out, rng_hist = [], []
    for day, d in g.groupby("day"):
        a = d[(d.h >= 1) & (d.h < 9)]
        b = d[(d.h >= 10) & (d.h < 18)]
        if len(a) < 60 or len(b) < 60:
            continue
        hi, lo = a.high.max(), a.low.min()
        w = (hi - lo) / a.close.iloc[-1]
        avg = np.mean(rng_hist[-60:]) if len(rng_hist) >= 30 else np.nan
        rng_hist.append(w)
        if np.isnan(avg) or not 0.25 * avg <= w <= 3 * avg:
            continue
        O, H, L, C = (b[c].to_numpy() for c in ("open", "high", "low", "close"))
        hrs = b.h.to_numpy()
        for want in (1, -1):
            side, e, stop, x, k0 = 0, 0.0, 0.0, None, 0
            for k in range(len(b)):
                if side == 0:
                    if want > 0 and H[k] > hi:
                        side, e = 1, max(hi, O[k])
                    elif want < 0 and L[k] < lo:
                        side, e = -1, min(lo, O[k])
                    else:
                        continue
                    k0 = k
                    stop = lo if side > 0 else hi
                    if side * (C[k] - stop) <= 0:
                        x = stop
                        break
                    continue
                if side * ((L[k] if side > 0 else H[k]) - stop) <= 0:
                    x = stop
                    break
            if side == 0:
                continue
            if x is None:
                x = C[-1]
            R = abs(e - stop)
            try:
                a14, a100 = atr14[day], atr100[day]
                feat = dict(atr_ratio=a14 / a100, rv_pct=rv_pct[day], dist20=side * (e - mean20[day]) / a14,
                            prev_rng=prev_rng[day], width=w / avg)
            except KeyError:
                continue
            out.append(dict(day=day, mk=s, r=side * (x - e) / R, rel=R / e, hour=hrs[k0], wd=day.dayofweek,
                            mend=float((day + pd.offsets.BDay(2)).month != day.month), side=side, **feat))
    T = pd.DataFrame(out)
    T["net"] = T.r - MK[s] * 1e-4 / T.rel
    T["net15"] = T.r - 1.5 * MK[s] * 1e-4 / T.rel
    T["net2"] = T.r - 2.0 * MK[s] * 1e-4 / T.rel
    # prior-5-trade hit rate, only trades from earlier days (exit 18:00 same day)
    T = T.sort_values(["day", "side"]).reset_index(drop=True)
    hit = (T.net > 0).astype(float)
    days = T.day.to_numpy()
    h5 = np.full(len(T), np.nan)
    for i in range(len(T)):
        j = np.searchsorted(days, days[i], side="left")      # trades strictly before this day
        if j >= 5:
            h5[i] = hit.iloc[j - 5:j].mean()
    T["hit5"] = h5
    return T


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def daily(T, col, size=None):
    r = T[col] * (T.rel * 0 + 1) if size is None else T[col] * size
    return pd.Series(r.to_numpy(), index=T.day).groupby(level=0).sum()


if __name__ == "__main__":
    A = pd.concat([trades(s) for s in MK], ignore_index=True)
    A = A.dropna(subset=FEATS).reset_index(drop=True)
    A = A[A.day <= "2025-10-12"]
    A = holdout.drop(A.set_index("day")).reset_index()
    print(len(A), "trades", A.day.min(), A.day.max())
    A.to_pickle(ROOT / "research" / "metalabel_trades.pkl")
    U = A[A.mk == "USDJPY"].copy()
    print("USDJPY plain net Sharpe", round(sh(daily(U, "net")), 2), "to2017", round(sh(daily(U, "net")[:"2017"]), 2),
          "2018+", round(sh(daily(U, "net")["2018":]), 2))
    A["y"] = (A.net > 0).astype(int)
    pcol = {}
    for model in ("logit", "lgbm"):
        p = pd.Series(np.nan, index=A.index)
        for Y in range(2012, 2026):
            tr = A[A.day < pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=10)]
            te = A[(A.day >= f"{Y}-01-01") & (A.day < f"{Y + 1}-01-01") & (A.mk == "USDJPY")]
            if len(te) == 0:
                continue
            if model == "logit":
                m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
            else:
                import lightgbm as lgb
                m = lgb.LGBMClassifier(max_depth=2, n_estimators=100, learning_rate=0.05, verbose=-1, random_state=0)
            m.fit(tr[FEATS], tr.y)
            p[te.index] = m.predict_proba(te[FEATS])[:, 1]
        pcol[model] = p
    U = A[A.mk == "USDJPY"].copy()
    from sklearn.metrics import roc_auc_score
    res = {}
    for model, p in pcol.items():
        U["p"] = p[U.index]
        V = U.dropna(subset=["p"])
        print(f"\n[{model}] OOS trades {len(V)}  AUC {roc_auc_score(V.y, V.p):.3f}  mean p {V.p.mean():.3f} "
              f"base hit {V.y.mean():.3f}")
        for rule in ("A", "B"):
            if rule == "A":
                size = 0.5 + 0.5 * V.p
            else:
                size = pd.Series(np.where(V.p < 0.40, 0.0, 0.5 + 0.5 * V.p), index=V.index)
            res[(model, rule)] = (V, size)
            for col in ("net", "net15", "net2"):
                d = daily(V, col, size)
                base = daily(V, col)
                scaled = daily(V, col, size.mean())
                print(f"  rule {rule} {col}: sized {sh(d):.2f} (to2017 {sh(d[:'2017']):.2f}, 2018+ {sh(d['2018':]):.2f}) "
                      f"| plain {sh(base):.2f} ({sh(base[:'2017']):.2f}/{sh(base['2018':]):.2f}) "
                      f"| plain x mean size {sh(scaled):.2f}  mean size {size.mean():.2f} skip {(size == 0).mean():.0%}")
        # random keep at the same skip rate (3 seeds)
        if True:
            skip = (res[(model, "B")][1] == 0).mean()
            for seed in range(3):
                rng = np.random.default_rng(seed)
                sz = pd.Series(np.where(rng.random(len(V)) < skip, 0.0, res[(model, "B")][1][res[(model, "B")][1] > 0].mean()),
                               index=V.index)
                d = daily(V, "net", sz)
                print(f"  random keep seed {seed}: {sh(d):.2f} ({sh(d[:'2017']):.2f}/{sh(d['2018':]):.2f})")
    # choose model/rule on 2012-2017 OOS only
    best, bs = None, -9
    for k, (V, size) in res.items():
        s = sh(daily(V, "net", size)[:"2017"])
        print("select", k, round(s, 3))
        if s > bs:
            best, bs = k, s
    print("chosen on 2012-17:", best)
    V, size = res[best]
    # candidate series: before 2012 neutral mean size; the book's breakout leg is scaled, so write the ratio series
    # sized/plain as a size multiplier and the daily R of the sized leg with the book's scale
    import book_sim as B
    bl = B.legs()["breakout"]
    plain = daily(U, "net")
    k = (bl.std() / plain.reindex(bl.index).fillna(0).std())
    print("scale to book leg", round(k, 6), "corr plain vs book leg",
          round(plain.reindex(bl.index).fillna(0).corr(bl), 3))
    ms = size.mean()
    for col, name in (("net", "ml_metalabel_breakout_size"), ("net15", "ml_metalabel_breakout_size_stress")):
        d = daily(V, col, size).reindex(plain.index).fillna(0)
        pre = daily(U, col)[:"2011"] * ms
        d = d.copy()
        d[d.index <= "2011-12-31"] = pre.reindex(d[:"2011"].index).fillna(0)
        d = (d * k)
        d.index.name = "day"
        d.name = "r"
        d.to_csv(OUT / f"{name}.csv", header=True)
    print("written")
