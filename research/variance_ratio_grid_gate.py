"""Lo-MacKinlay VR(5) gate on the AUDCAD grid leg. Item variance_ratio_grid_gate.

Pre-registered: grid runs on day t only if VR(5) of AUDCAD daily log returns over the 120 days ending t-1 is < 1.0.
Daily close = last hourly bid of the day (HYDRA_H1). One threshold, one window, one q. Robustness: NZDCAD/AUDNZD not
available in hourly file, so only controls (random skip with same on-share). Degeneracy guard: stop if on-share <30% or >95%.

    python research/variance_ratio_grid_gate.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import backtest_hydra as H  # noqa: E402
import book_sim as B  # noqa: E402

Q, W, THR = 5, 120, 1.0


def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def vr(r, q):
    n = len(r)
    mu = r.mean()
    s1 = ((r - mu) ** 2).sum() / (n - 1)
    rq = r.rolling(q).sum().dropna()
    m = q * (n - q + 1) * (1 - q / n)
    sq = ((rq - q * mu) ** 2).sum() / m
    return sq / s1


def main():
    L = B.legs()
    h = H.hourly()
    h = h[h.index < pd.Timestamp("2025-10-13")]
    c = h["AUDCAD"].dropna().groupby(h["AUDCAD"].dropna().index.normalize()).last()
    c = c[c.index.dayofweek < 5]
    r = np.log(c).diff().dropna()
    v = pd.Series(np.nan, index=r.index)
    vals = r.values
    for i in range(W, len(r)):
        v.iloc[i] = vr(pd.Series(vals[i - W:i]), Q)  # window ends t-1
    on = (v < THR).reindex(L.index)
    have = v.reindex(L.index).notna()
    share = on[have].mean()
    print(f"VR days {have.sum()} share on {share:.3f}; VR median {v.median():.3f}")
    if share < 0.30 or share > 0.95:
        print("DEGENERATE gate, stop")
        return
    on = on.fillna(True).astype(float)  # before window: plain grid
    mo = lambda x: (x["2018":].groupby(x["2018":].index.to_period("M")).sum() < 0).sum()
    pb, _ = B.combine(L)
    Lg = L.copy()
    Lg["grid"] = L["grid"] * on
    gb, _ = B.combine(Lg)
    print(f"plain book: 2018+ {sh(pb['2018':]):.2f} to2017 {sh(pb[:'2017']):.2f} lose {mo(pb)}")
    print(f"VR gate book: 2018+ {sh(gb['2018':]):.2f} to2017 {sh(gb[:'2017']):.2f} lose {mo(gb)}")
    g, gg = L["grid"], L["grid"] * on
    print(f"grid alone: plain all {sh(g):.2f} 2018+ {sh(g['2018':]):.2f} to2017 {sh(g[:'2017']):.2f}; gated all {sh(gg):.2f} 2018+ {sh(gg['2018':]):.2f} to2017 {sh(gg[:'2017']):.2f}")
    print("corr gated vs plain grid", round(g.corr(gg), 3))
    for ym in ["2021-11", "2023-05"]:
        print(ym, "plain", round(g[ym].sum(), 4), "gated", round(gg[ym].sum(), 4), "on share", round(on[ym].mean(), 2))
    for s in range(5):
        rr = np.random.default_rng(s).random(len(L)) < share
        Lc = L.copy()
        Lc["grid"] = L["grid"] * rr
        cb, _ = B.combine(Lc)
        print(f"random control {s}: 2018+ {sh(cb['2018':]):.2f} lose {mo(cb)}")


if __name__ == "__main__":
    main()
