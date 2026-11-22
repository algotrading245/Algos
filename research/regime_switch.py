"""Regime classifier (ADX, Hurst proxy, realised-vol ratio on XAUUSD D1; rule version and LightGBM version) that
switches each Hydra leg on or off the next day. Walk-forward by year (train = all earlier days, 1-day purge), test
years 2014 on, judged 2018 on, holdout dropped. Compared with all legs always on.

    python research/regime_switch.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

SPLIT = pd.Timestamp("2018-01-01")
FEATS = ["adx", "hurst", "rvr"]


def features():
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / "XAUUSD_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    D = d.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    h, l, c = D.high, D.low, D.close
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, D.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    mdi = 100 * pd.Series(mdm, D.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
    r = np.log(c).diff()
    r5 = np.log(c).diff(5)
    hurst = 0.5 * np.log(r5.rolling(120).var() / (5 * r.rolling(120).var())) / np.log(5) + 0.5
    rvr = r.rolling(5).std() / r.rolling(60).std()
    F = pd.DataFrame({"adx": adx, "hurst": hurst, "rvr": rvr}, index=D.index)
    F.index = F.index.normalize()
    return F.shift(1)       # feature known at the previous close drives the day's switch


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def main():
    legs = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    legs = holdout.drop(legs)
    F = features().reindex(legs.index).ffill()
    legs = legs.drop(columns=["quartet"], errors="ignore")
    ok = F.notna().all(axis=1)
    legs, F = legs[ok], F[ok]
    years = range(2014, legs.index.year.max() + 1)
    rule = pd.DataFrame(1.0, index=legs.index, columns=legs.columns)
    ml = {s: pd.DataFrame(1.0, index=legs.index, columns=legs.columns) for s in (0, 1, 2)}
    trials = 0
    for y in years:
        tr = legs.index < pd.Timestamp(f"{y}-01-01") - pd.Timedelta(days=2)
        te = legs.index.year == y
        for leg in legs.columns:
            for f in FEATS:
                trials += 1
                med = F.loc[tr, f].median()
                hi = F.loc[tr, f] > med
                a, b = legs.loc[tr, leg][hi], legs.loc[tr, leg][~hi]
                t = (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b))
                if abs(t) > 2.0:      # only act on a significant split; the rule votes
                    on = (F.loc[te, f] > med) if t > 0 else (F.loc[te, f] <= med)
                    rule.loc[te, leg] = rule.loc[te, leg] * on.astype(float).values
            for s in (0, 1, 2):
                trials += 1
                X = pd.concat([F, legs[leg].shift(1).rename("lag")], axis=1)
                m = lgb.LGBMClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, subsample=0.8,
                                       subsample_freq=1, colsample_bytree=0.8, random_state=s, verbose=-1)
                yt = (legs[leg][tr] > 0).iloc[1:]
                m.fit(X[tr].iloc[1:], yt)
                p = m.predict_proba(X[te])[:, 1]
                ml[s].loc[te, leg] = (p > yt.mean()).astype(float)   # on when above the training base rate
    start = pd.Timestamp("2014-01-01")
    base = legs[legs.index >= start]
    rows = []
    for name, sw in [("rule", rule)] + [(f"lgbm{s}", ml[s]) for s in ml]:
        g = (legs * sw)[legs.index >= start]
        for lbl, m in (("2014+", slice(None)),):
            pass
        for lbl, sel in (("2014-17", g.index < SPLIT), ("2018+", g.index >= SPLIT)):
            rows.append((name, lbl, sharpe(base[sel].sum(axis=1)), sharpe(g[sel].sum(axis=1)),
                         (sw[legs.index >= start][sel].mean().mean())))
    print("variant   period    Sharpe on   Sharpe switched   share of days on")
    for r in rows:
        print(f"{r[0]:8s} {r[1]:8s} {r[2]:9.2f} {r[3]:15.2f} {r[4]:14.2f}")
    print("per leg 2018+ (always on -> rule -> lgbm mean of seeds)")
    late = legs.index >= SPLIT
    for leg in legs.columns:
        print(f"{leg:8s} {sharpe(legs.loc[late, leg]):5.2f} {sharpe((legs[leg] * rule[leg])[late]):5.2f} "
              f"{np.mean([sharpe((legs[leg] * ml[s][leg])[late]) for s in ml]):5.2f}")
    print("trials", trials)
    sw = (legs * rule).sum(axis=1) - legs.sum(axis=1)
    out = ROOT / "marketdata" / "candidates"
    sw[sw.index >= start].rename("r").rename_axis("day").to_csv(out / "regime_switch.csv")


if __name__ == "__main__":
    main()
