"""Volatility forecast for sizing: HAR-RV vs GARCH(1,1) vs LightGBM vs EWMA/naive on XAUUSD daily realised vol.

Realised vol = sqrt(sum of squared 5-min log returns) per day (from M1, holdout dropped). Forecast of day t+1 RV from
data to t (past only). Walk-forward: refit each January on all data before it (expanding), first test year 2010+train.
Sizing: w_t = clip(TARGET / forecast_t, 0, CAP) applied to a long gold position (r_{t+1}); baseline = fixed size 1
(buy and hold, ann. vol-matched in the report). Costs: 1 bp round trip on |dw|, 0.5 bp swap on |w| per day, x1.0/1.5/2.0.
Trials: 4 forecasters x 1 sizing rule (+ 3 LightGBM seeds) = counted as 8 extra trials.
Judged: forecast QLIKE/MSE on 2018 on; resized Sharpe vs fixed, both halves. Stream written for tools/gates.py:
candidate volforecast_sizing = best forecaster chosen by TRAIN half (to 2017) QLIKE only.
    python research/volforecast_sizing.py
"""
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST = 1.0e-4
SWAP = 0.5e-4
CAP = 3.0
SPLIT = pd.Timestamp("2018-01-01")


def daily():
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / "XAUUSD_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    m5 = d.close.resample("5min").last().dropna()
    lr = np.log(m5).diff().dropna()
    # drop rollover hour 23-01 jumps? keep: day = calendar day of data clock, exclude weekend thin days
    rv = np.sqrt((lr ** 2).groupby(lr.index.normalize()).sum())
    cl = d.close.resample("1D").last().dropna()
    ret = np.log(cl).diff()
    df = pd.DataFrame({"rv": rv, "ret": ret}).dropna()
    df = df[df.index.dayofweek < 5]
    return df[df.rv > 0]


def feats(df):
    rv = df.rv
    f = pd.DataFrame(index=df.index)
    f["d"] = rv
    f["w"] = rv.rolling(5).mean()
    f["m"] = rv.rolling(22).mean()
    f["absret"] = df.ret.abs()
    f["neg"] = (df.ret < 0).astype(float) * df.ret.abs()
    return f


def har_fit(f, y, idx):
    X = np.c_[np.ones(len(idx)), f.loc[idx, ["d", "w", "m"]].values]
    b = np.linalg.lstsq(X, y.loc[idx].values, rcond=None)[0]
    return lambda ix: np.c_[np.ones(len(ix)), f.loc[ix, ["d", "w", "m"]].values] @ b


def garch_filter(r, p):
    w, a, b = p
    s2 = np.empty(len(r) + 1)
    s2[0] = np.var(r)
    for i in range(len(r)):
        s2[i + 1] = w + a * r[i] ** 2 + b * s2[i]
    return np.sqrt(s2[1:])


def garch_mle(r):
    from scipy.optimize import minimize

    def nll(p):
        w, a, b = p
        if w <= 0 or a < 0 or b < 0 or a + b >= 0.9999:
            return 1e12
        s = garch_filter(r, p)
        s2 = np.r_[np.var(r), s[:-1] ** 2]
        return 0.5 * np.sum(np.log(s2) + r ** 2 / s2)
    v = np.var(r)
    best = minimize(nll, [v * 0.05, 0.05, 0.9], method="Nelder-Mead", options={"maxiter": 600, "xatol": 1e-5, "fatol": 1e-6})
    return best.x


def lgb_fit(f, y, idx, seed):
    import lightgbm as lgb
    cols = list(f.columns)
    m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.03, num_leaves=8, min_child_samples=50,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=seed, verbose=-1)
    m.fit(f.loc[idx, cols], np.log(y.loc[idx]))
    return lambda ix: np.exp(m.predict(f.loc[ix, cols]))


def main():
    df = daily()
    f = feats(df).dropna()
    df = df.loc[f.index]
    y = df.rv.shift(-1)                  # target: next day's RV, known only after t+1
    nxt = df.ret.shift(-1)
    ok = y.notna()
    years = sorted(set(df.index.year))
    first = years[0] + 5
    names = ["naive", "ewma", "har", "garch", "lgbm"]
    pred = {n: pd.Series(np.nan, index=df.index) for n in names}
    for yr in years:
        if yr < first:
            continue
        te = df.index[(df.index.year == yr) & ok.values]
        # purge: train rows whose target (t+1) lies before test start -> drop last 1 day
        tr = df.index[(df.index < pd.Timestamp(f"{yr}-01-01")) & ok.values][:-1]
        if len(te) == 0:
            continue
        pred["naive"].loc[te] = f.loc[te, "d"].values
        pred["ewma"].loc[te] = df.rv.ewm(halflife=5).mean().loc[te].values
        pred["har"].loc[te] = har_fit(f, y, tr)(te)
        r_all = (df.ret.loc[:te[-1]] * 100).fillna(0.0)
        params = garch_mle((df.ret.loc[:tr[-1]] * 100).fillna(0.0).values)
        sig = garch_filter(r_all.values, params)          # sig[i] = sigma forecast for day i+1 given r up to i
        s = pd.Series(sig, index=r_all.index) / 100
        ratio = (df.rv.shift(-1).loc[tr] / s.loc[tr]).median()   # scale close-close sigma to RV units, train only
        pred["garch"].loc[te] = (s.loc[te] * ratio).values
        pred["lgbm"].loc[te] = np.mean([lgb_fit(f, y, tr, s)(te) for s in (1, 2, 3)], axis=0)
    P = pd.DataFrame(pred).dropna()
    P = P.loc[P.index.intersection(y.dropna().index)]
    yy = y.loc[P.index]
    pre = P.index < SPLIT

    def qlike(p, a):
        return float(np.mean(np.log(p ** 2) + a ** 2 / p ** 2))

    print("forecast loss (QLIKE lower=better, MSE x1e6)")
    for n in names:
        print(f"{n:6s} QLIKE pre {qlike(P[n][pre], yy[pre]):.4f} post {qlike(P[n][~pre], yy[~pre]):.4f}"
              f"  MSE pre {np.mean((P[n][pre]-yy[pre])**2)*1e6:.2f} post {np.mean((P[n][~pre]-yy[~pre])**2)*1e6:.2f}")

    # sizing
    ann = lambda x: float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0
    R = nxt.loc[P.index]
    fixed_sd = R[pre].std()
    TARGET = fixed_sd                     # match train-half daily vol of the fixed position
    streams = {}
    for k in (1.0, 1.5, 2.0):
        fixed = R - SWAP * k
        fixed.iloc[0] -= COST * k / 2
        streams[("fixed", k)] = fixed
        for n in names:
            w = (TARGET / P[n]).clip(0, CAP)
            dw = w.diff().abs().fillna(w.abs())
            streams[(n, k)] = w * R - dw * COST * k / 2 - w * SWAP * k
    print("\nSharpe (net) pre / post / both, by cost multiple; ann. vol post")
    for n in ["fixed"] + names:
        for k in (1.0, 1.5, 2.0):
            s = streams[(n, k)]
            print(f"{n:6s} x{k}: {ann(s[pre]):5.2f} {ann(s[~pre]):5.2f} {ann(s):5.2f}  vol post {s[~pre].std()*np.sqrt(252):.3f}"
                  f" maxDD {float((s.cumsum()-s.cumsum().cummax()).min()):.3f}")
    # choose by train-half QLIKE only
    best = min(names, key=lambda n: qlike(P[n][pre], yy[pre]))
    print("\nbest forecaster by train QLIKE:", best)
    out = ROOT / "marketdata" / "candidates"
    for k, suf in ((1.0, ""), (1.5, "_stress")):
        # candidate = resized stream minus the fixed stream? Gate the resized strategy itself.
        s = streams[(best, k)]
        pd.DataFrame({"day": s.index.strftime("%Y-%m-%d"), "r": s.values}).to_csv(out / f"volforecast_sizing{suf}.csv", index=False)
    # value of sizing: resized minus fixed (same vol) Sharpe difference
    print("written volforecast_sizing(.csv/_stress.csv); trials: 5 forecasters (lgbm 3 seeds) ~ 8")


if __name__ == "__main__":
    main()
