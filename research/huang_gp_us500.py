"""Huang (2015) gold/platinum ratio timing of US stock indices (queue item paper_huang_gold_platinum_us500).

GP = log(gold / platinum), month-end. Signal at month-end M (past only): z = GP - mean of GP over the previous 120
month-ends (including M). Long the index for the next month when z > 0 (variant A), or position = clip(z/sd,0,1)
(variant B, sd = trailing 120m std). Flat otherwise. Index = mean of ES and NQ daily close-to-close returns (US500 +
US100). Costs: 1.5 bp per side at 1x on every position change (spread), swap 2.5 bp a night (calendar days) while
long, both scaled 1x/1.5x/2x. Settings fixed by the paper (120 months), not tuned. Holdout dropped.

    python research/huang_gp_us500.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_huang_gold_platinum_us500"
SIDE_BP, SWAP_BP = 1.5, 2.5


def load(n):
    d = pd.read_csv(ROOT / "marketdata" / "commod" / f"{n}.csv", parse_dates=["date"]).set_index("date")["close"]
    return d[~d.index.duplicated()].sort_index()


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def run(gc, pl, idx_ret, variant, cx):
    gp = np.log(gc / pl).dropna()
    me = gp.groupby(gp.index.to_period("M")).last()
    mu = me.rolling(120, min_periods=120).mean()
    sd = me.rolling(120, min_periods=120).std()
    z = me - mu
    w = (z > 0).astype(float) if variant == "A" else (z / sd).clip(0, 1)
    w = w.where(mu.notna())
    # signal for month P+1 known at the end of P
    w.index = w.index + 1
    pos = pd.Series(w.reindex(idx_ret.index.to_period("M")).values, index=idx_ret.index).fillna(0.0)
    gap = pd.Series(idx_ret.index, index=idx_ret.index).diff().dt.days.fillna(1).clip(lower=1)
    r = pos * idx_ret - pos.diff().abs().fillna(0) * SIDE_BP * 1e-4 * cx - pos * gap * SWAP_BP * 1e-4 * cx
    return r, pos


def main():
    gc, pl = load("GC"), load("PL")
    ix = pd.concat({k: load(k).pct_change() for k in ("ES", "NQ")}, axis=1).dropna()
    mk = ix.mean(axis=1)
    mk = holdout.drop(mk)
    gc, pl = holdout.drop(gc), holdout.drop(pl)
    print("data", mk.index[0].date(), mk.index[-1].date(), len(mk))
    half = pd.Timestamp("2018-01-01")
    bh = mk
    print("buy&hold sharpe all/<2018/>=2018", round(sh(bh), 2), round(sh(bh[bh.index < half]), 2), round(sh(bh[bh.index >= half]), 2))
    res = {}
    for v in ("A", "B"):
        for cx in (1.0, 1.5, 2.0):
            r, pos = run(gc, pl, mk, v, cx)
            r = r[r.index >= pos[pos.notna()].index[0]]
            res[(v, cx)] = r
            a, b = r[r.index < half], r[r.index >= half]
            print(v, cx, "sh all %.2f  <2018 %.2f  >=2018 %.2f  ann %.2f%%  inmkt %.0f%%" % (
                sh(r), sh(a), sh(b), r.mean() * 252 * 100, (pos.reindex(r.index) > 0).mean() * 100))
    # same exposure random? compare to buy-and-hold in-market days
    r1, pos = run(gc, pl, mk, "A", 1.0)
    m = pos > 0
    print("mean daily ret in-market %.4f%% vs out %.4f%% (>=2011)" % (
        mk[m & (mk.index >= "2015-01-01")].mean() * 100, mk[~m & (mk.index >= "2015-01-01")].mean() * 100))
    print("post-2015 only sharpe A 1x:", round(sh(res[("A", 1.0)][res[("A", 1.0)].index >= "2015-01-01"]), 2),
          "bh:", round(sh(mk[mk.index >= "2015-01-01"]), 2))
    v = "A"
    for tag, cx in (("", 1.0), ("_stress", 1.5)):
        r = res[(v, cx)]
        r = r[r.index.dayofweek < 5]
        r.rename("r").rename_axis("day").to_csv(OUT / f"{ID}{tag}.csv", header=True)
    print("written", ID)


if __name__ == "__main__":
    main()
