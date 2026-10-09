"""Seconds-to-minutes scalping from ticks: 1-second grid, order-flow style features (tick imbalance, quote
intensity, spread, short returns), LightGBM, train on the first days and test on the last ones. Trades are filled
at the real ask/bid one second after the signal and closed at the real bid/ask H seconds later."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
sys.path.insert(0, str(Path(__file__).resolve().parent))
import realdata as rd

def day_frame(path):
    t, b, a = rd.ticks(path)
    sec = t // 1000
    mid = (a + b) / 2
    dm = np.diff(mid, prepend=mid[0])
    g = pd.DataFrame({"sec": sec, "bid": b, "ask": a, "up": (dm > 0).astype(np.int32), "dn": (dm < 0).astype(np.int32), "n": 1})
    s = g.groupby("sec").agg(bid=("bid", "last"), ask=("ask", "last"), up=("up", "sum"), dn=("dn", "sum"), n=("n", "sum"))
    full = pd.RangeIndex(s.index[0], s.index[-1] + 1)
    s = s.reindex(full)
    s[["bid", "ask"]] = s[["bid", "ask"]].ffill()
    s[["up", "dn", "n"]] = s[["up", "dn", "n"]].fillna(0)
    s["stale"] = s.n.eq(0).astype(int).rolling(30).sum()          # seconds without quotes in the last 30
    mid = (s.bid + s.ask) / 2
    f = pd.DataFrame(index=s.index)
    d1 = mid.diff()
    vol = d1.rolling(900).std() + 1e-6
    for k in (1, 3, 10, 30, 60, 300, 900):
        f[f"r{k}"] = (mid - mid.shift(k)) / (vol * np.sqrt(k))
    for k in (3, 10, 30, 120):
        u, dn = s.up.rolling(k).sum(), s.dn.rolling(k).sum()
        f[f"imb{k}"] = (u - dn) / (u + dn + 1)
        f[f"int{k}"] = s.n.rolling(k).sum() / (s.n.rolling(900).sum() * k / 900 + 1)
    f["spr"] = s.ask - s.bid
    f["sprr"] = f.spr / f.spr.rolling(900).median()
    f["volr"] = d1.rolling(30).std() / vol
    f["vol"] = vol
    for k in (60, 300, 900):
        hi, lo = mid.rolling(k).max(), mid.rolling(k).min()
        f[f"pos{k}"] = (mid - lo) / (hi - lo + 1e-6)
    f["tod"] = (s.index % 86400) / 3600
    out = {"f": f, "bid": s.bid.to_numpy(), "ask": s.ask.to_numpy(), "mid": mid.to_numpy(), "stale": s.stale.to_numpy()}
    return out

days = [day_frame(p) for p in rd.tick_days()]
print("days", len(days), "rows", sum(len(x["f"]) for x in days), flush=True)
ntr = int(len(days) * 0.6)

def build(dd, H, step):
    Xs, ys, meta = [], [], []
    for k, x in enumerate(dd):
        n = len(x["f"])
        i = np.arange(900, n - H - 2, step)
        i = i[x["stale"][i] < 20]
        Xs.append(x["f"].iloc[i])
        ys.append((x["mid"][i + 1 + H] - x["mid"][i + 1]) / x["f"].vol.to_numpy()[i])
        lg = x["bid"][i + 1 + H] - x["ask"][i + 1]            # long: buy at ask, sell at bid
        sh = x["bid"][i + 1] - x["ask"][i + 1 + H]            # short: sell at bid, buy at ask
        meta.append(pd.DataFrame({"day": k, "i": i, "lg": lg, "sh": sh}))
    return pd.concat(Xs), np.concatenate(ys), pd.concat(meta, ignore_index=True)

for H in (5, 15, 60, 300, 900):
    step = max(1, H // 5)
    Xtr, ytr, _ = build(days[:ntr], H, step)
    Xte, yte, mt = build(days[ntr:], H, step)
    ok = np.isfinite(ytr) & Xtr.notna().all(axis=1).to_numpy()
    Xtr, ytr = Xtr[ok], ytr[ok]
    cut = int(len(Xtr) * 0.8)
    m = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=500, subsample=0.5,
                          subsample_freq=1, colsample_bytree=0.7, reg_lambda=5, verbose=-1)
    m.fit(Xtr.iloc[:cut], ytr[:cut], eval_set=[(Xtr.iloc[cut:], ytr[cut:])], callbacks=[lgb.early_stopping(40, verbose=False)])
    pv = m.predict(Xtr.iloc[cut:])
    p = m.predict(Xte)
    okt = np.isfinite(yte) & np.isfinite(p)
    ic = np.corrcoef(p[okt], yte[okt])[0, 1]
    icv = np.corrcoef(pv, ytr[cut:])[0, 1]
    imp = pd.Series(m.booster_.feature_importance("gain"), index=Xtr.columns).sort_values(ascending=False)
    print(f"\nH={H}s trees {m.best_iteration_} IC val {icv:+.4f} test {ic:+.4f} top {list(imp.index[:5])}", flush=True)
    for q in (0.9, 0.99, 0.999):
        thr = np.quantile(np.abs(pv), q)
        res = []
        for dy, g in mt.groupby("day"):
            pp = p[g.index.to_numpy()]
            nxt = -1
            for j, (i, lg, sh) in enumerate(zip(g.i.to_numpy(), g.lg.to_numpy(), g.sh.to_numpy())):
                if i < nxt or not abs(pp[j]) >= thr: continue
                res.append((dy, lg if pp[j] > 0 else sh, (lg - sh) / 2 if pp[j] > 0 else (sh - lg) / 2))
                nxt = i + H
        if len(res) < 5:
            print(f"  q={q}: n={len(res)}"); continue
        r = pd.DataFrame(res, columns=["day", "net", "gross"])
        print(f"  q={q}: n={len(r):5d} net {r.net.mean():+.4f} t {r.net.mean() / r.net.std() * np.sqrt(len(r)):+.1f} | gross(mid) {r.gross.mean():+.4f} | per day net {r.groupby('day').net.sum().round(1).tolist()}", flush=True)
