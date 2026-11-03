"""Moreira & Muir volatility-managed long, daily version, on SPXUSD (paper's market), XAUUSD (extension), USDJPY, EURUSD.

w_t = min(CAP, c / RV_t^2) with RV^2 = sum of the last 22 daily squared log returns (to yesterday's close, applied to
the next day's return). c fixed on data to 2017 so the managed std equals buy-and-hold's (long 1x). Costs per unit
|dw|: half the round trip (SPX 1.0 bp rt, XAU 1.0 bp, USDJPY 0.7 bp, EURUSD 0.6 bp -> half each side) plus 0.5 bp swap per day
on |w|, x1.0/1.5/2.0. Holdout dropped. Trials: 4 markets x caps {1,2} = 8.
Judged: Sharpe of managed minus Sharpe of buy-and-hold, per half (to 2017, 2018 on); the stream for gates.py is the
managed-minus-hold overlay? No: the managed long itself, SPXUSD cap 2 (chosen on the train half).
    python research/volmanaged_mm.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

RT = {"SPXUSD": 1.0e-4, "XAUUSD": 1.0e-4, "USDJPY": 0.7e-4, "EURUSD": 0.6e-4}
SWAP = 0.5e-4
SPLIT = pd.Timestamp("2018-01-01")


def daily(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    cl = d.close.resample("1D").last().dropna()
    cl = cl[cl.index.dayofweek < 5]
    return np.log(cl).diff().dropna()


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan


def run(r, cap, mult):
    rv2 = (r ** 2).rolling(22).sum().shift(1)  # known at yesterday's close for today's return
    w0 = 1.0 / rv2
    tr = r[r.index < SPLIT]
    base = (w0.loc[tr.index] * tr).dropna()
    ok = w0.loc[tr.index].notna()
    c = tr[ok].std() / base.std() if False else None
    # c so that capped managed std over train equals buy-and-hold std
    lo, hi = 1e-6, 1.0
    target = tr[ok].std()
    for _ in range(60):
        mid = (lo * hi) ** 0.5 if lo > 0 else hi / 2
        wm = np.minimum(cap, mid * w0.loc[tr.index][ok])
        s = (wm * tr[ok]).std()
        if s < target:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0000001:
            break
        hi = max(hi, lo * 1.0001)
    # bracket by growth instead (monotone in c): simple expansion search
    c0 = target / base.std()
    cs = np.linspace(c0 * 0.2, c0 * 20, 4000)
    best = min(cs, key=lambda cc: abs((np.minimum(cap, cc * w0.loc[tr.index][ok]) * tr[ok]).std() - target))
    w = np.minimum(cap, best * w0).dropna()
    rr = r.loc[w.index]
    cost = (w.diff().abs().fillna(0) * RT_ / 2 + w.abs() * SWAP) * mult
    hold_cost = SWAP * mult
    net = w * rr - cost
    hold = rr - hold_cost
    return net, hold, best, w


for sym in RT:
    RT_ = RT[sym]
    r = daily(sym)
    print(f"== {sym}: {r.index[0].date()} .. {r.index[-1].date()}  {len(r)} days")
    for cap in (1, 2):
        for mult in (1.0, 1.5, 2.0):
            net, hold, c, w = run(r, cap, mult)
            a, b = net[net.index < SPLIT], net[net.index >= SPLIT]
            ha, hb = hold.loc[a.index], hold.loc[b.index]
            print(f"cap {cap} x{mult}: managed Sh {sh(a):.2f}/{sh(b):.2f}  hold {sh(ha):.2f}/{sh(hb):.2f}  "
                  f"delta {sh(a)-sh(ha):+.2f}/{sh(b)-sh(hb):+.2f}  mean w {w.mean():.2f}")
        if sym == "SPXUSD" and cap == 2:
            n1, _, _, _ = run(r, cap, 1.0)
            n15, _, _, _ = run(r, cap, 1.5)
            out = ROOT / "marketdata" / "candidates"
            n1.rename("r").rename_axis("day").to_csv(out / "volmanaged_mm.csv")
            n15.rename("r").rename_axis("day").to_csv(out / "volmanaged_mm_stress.csv")
