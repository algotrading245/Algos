"""HRP (Lopez de Prado 2016) vs the book's equal-risk weights. Past-only: trailing 260 days, rebalance every 22 days.
Same cap, SCALE and risk layer as tools/book_sim.py. Run: python research/ml_hrp_leg_weights.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import book_sim as B
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform

WIN, REB = 260, 22


def ivp(cov):
    w = 1 / np.diag(cov)
    return w / w.sum()


def cvar(cov, idx):
    c = cov[np.ix_(idx, idx)]
    w = ivp(c)
    return float(w @ c @ w)


def hrp(ret):
    cov = ret.cov().to_numpy()
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sd, sd)
    d = np.sqrt((1 - corr) / 2)
    np.fill_diagonal(d, 0)
    order = list(leaves_list(linkage(squareform(d, checks=False), "single")))
    w = pd.Series(1.0, index=order)
    items = [order]
    while items:
        items = [i[j:k] for i in items for j, k in ((0, len(i) // 2), (len(i) // 2, len(i))) if len(i) > 1]
        for s in range(0, len(items), 2):
            a, b = items[s], items[s + 1]
            va, vb = cvar(cov, a), cvar(cov, b)
            al = 1 - va / (va + vb)
            w[a] *= al
            w[b] *= 1 - al
    out = pd.Series(w.sort_index().to_numpy(), index=ret.columns)
    return out / out.sum()


def cap(w):
    for _ in range(20):
        over = w > B.CAP
        if not over.any():
            break
        sp = (w[over] - B.CAP).sum()
        w[over] = B.CAP
        w[~over] += sp * w[~over] / w[~over].sum()
    return w


def hrp_weights(L):
    rows = {}
    idx = L.index
    for i in range(B.MIN_HISTORY, len(idx), REB):
        hist = L.iloc[max(0, i - WIN):i]  # days before i only
        hist = hist.loc[:, hist.notna().all() & (hist.std() > 0)]
        if hist.shape[1] < 3:
            continue
        w = hrp(hist)
        for k, f in B.SCALE.items():
            if k in w.index:
                w[k] *= f
        rows[idx[i]] = cap(w / w.sum())
    W = pd.DataFrame(rows).T.reindex(columns=L.columns).fillna(0.0)
    return W.reindex(idx).ffill().fillna(0.0)


def stats(name, b):
    r = B.risk_layer(b)
    r18 = r[r.index >= B.SPLIT]
    m = B.months(r18)
    print(f"{name:12s} raw {B.sharpe(b):.2f} raw2018 {B.sharpe(b[b.index>=B.SPLIT]):.2f} | layer {B.sharpe(r):.2f} "
          f"2018+ {B.sharpe(r18):.2f} to2017 {B.sharpe(r[r.index<B.SPLIT]):.2f} | losing months {(m<0).sum()}/{len(m)} "
          f"worst {m.min():.3f} maxDD {(1-(1+r18).cumprod()/(1+r18).cumprod().cummax()).max():.3f}")
    return r


def main():
    L = B.legs()
    b0, _ = B.combine(L)
    W = hrp_weights(L)
    live = W.sum(axis=1) > 0
    b1 = (W * L.fillna(0.0)).sum(axis=1)[live]
    common = b0.index.intersection(b1.index)
    print("legs", list(L.columns), "days", len(common))
    stats("equal-risk", b0.loc[common])
    stats("HRP", b1.loc[common])
    print("mean weights 2018+: equal-risk / HRP")
    W0 = B.weights(L)
    print(pd.DataFrame({"eq": W0[W0.index >= B.SPLIT].mean(), "hrp": W[W.index >= B.SPLIT].mean()}).round(3))
    # bootstrap-free check: daily difference
    d = (b1.loc[common] - b0.loc[common])
    print("diff mean/std annual-sharpe", B.sharpe(d))


main()
