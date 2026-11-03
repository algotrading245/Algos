"""Quantile-regression take-profit for the London-breakout leg (queue item ml_quantile_exit_breakout_noise).

Entries and stops are research/london_breakout.py rules unchanged (as in metalabel_breakout.py). Only the exit changes:
a take-profit at max(0.5, q) ATR14 from the entry, q = 0.6-quantile forecast of the trade's max favourable excursion
(ATR14 units, up to the leg's own exit). Model: GradientBoostingRegressor(loss=quantile, alpha=0.6, depth 2, 100 trees),
trained on trades of 5 markets up to 10 days before 1 Jan of the test year, predicting USDJPY (the leg in the book).
Past-only features: ATR5/ATR50, prior-day range/ATR, gap/ATR, Asian-range width/ATR, hour, weekday.
Same-bar stop and TP: stop first. Controls: own exit, fixed TP of the same median size (ATR units), 3 seeds.
Only the breakout half is tested; the noise leg has no stored intraday path in its script (noted in the result).

    python research/ml_quantile_exit_breakout_noise.py
"""
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))
import holdout  # noqa: E402

DATA = ROOT / "marketdata" / "histdata"
OUT = ROOT / "marketdata" / "candidates"
MK = {"USDJPY": 1.2, "EURJPY": 1.4, "GBPUSD": 1.0, "XAUUSD": 1.0, "EURUSD": 0.8}
FEATS = ["atr_ratio", "prev_rng", "gap", "width_atr", "hour", "wd"]


def trades(s):
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz")
    t = pd.to_datetime(m.time, unit="s")
    m = m[t.dt.dayofweek < 5]
    g = m.assign(time=m.time // 300 * 300).groupby("time").agg(open=("open", "first"), high=("high", "max"),
                                                               low=("low", "min"), close=("close", "last"))
    g["day"] = pd.to_datetime(g.index, unit="s").normalize()
    g["h"] = (g.index % 86400) / 3600
    dd = g.groupby("day").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    pc = dd.close.shift(1)
    tr = pd.concat([dd.high - dd.low, (dd.high - pc).abs(), (dd.low - pc).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().shift(1)
    atr5 = tr.rolling(5).mean().shift(1)
    atr50 = tr.rolling(50).mean().shift(1)
    prev_rng = ((dd.high - dd.low) / atr14).shift(1)
    gap = (dd.open - pc) / atr14
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
        A14 = atr14.get(day, np.nan)
        if not A14 > 0:
            continue
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
            kend = k if x is not None else len(b) - 1
            if x is None:
                x = C[-1]
            R = abs(e - stop)
            # favourable excursion path (bars k0..kend) and adverse path for same-bar stop-first logic
            fav = (H[k0:kend + 1] - e) if side > 0 else (e - L[k0:kend + 1])
            adv = (e - L[k0:kend + 1]) if side > 0 else (H[k0:kend + 1] - e)
            stopped = (side * (x - stop) == 0) and x == stop
            out.append(dict(day=day, mk=s, R=R, rel=R / e, atr=A14, x=side * (x - e), fav=fav, adv=adv,
                            mfe=max(fav.max(), 0) / A14, hour=hrs[k0], wd=day.dayofweek,
                            atr_ratio=atr5.get(day, np.nan) / atr50.get(day, np.nan), prev_rng=prev_rng.get(day, np.nan),
                            gap=side * gap.get(day, np.nan), width_atr=(hi - lo) / A14))
    T = pd.DataFrame(out)
    return T


def tp_result(row, tp_atr, stop_dist):
    """Price P&L (in price units, signed to the trade) with take-profit tp_atr*ATR; stop first on same bar."""
    tp = tp_atr * row.atr
    fav, adv = row.fav, row.adv
    for f, a in zip(fav, adv):
        if a >= stop_dist - 1e-12 * 0 and a >= row.R:     # stop touched (stop at R from entry)
            return -row.R
        if f >= tp:
            return tp
    return row.x


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def daily(T, col):
    return pd.Series(T[col].to_numpy(), index=T.day).groupby(level=0).sum()


def net(T, pnl, mult):
    return pnl / T.R - mult * T.mk.map(MK) * 1e-4 / T.rel


if __name__ == "__main__":
    A = pd.concat([trades(s) for s in MK], ignore_index=True)
    A = A.dropna(subset=FEATS).reset_index(drop=True)
    A = A[A.day <= "2025-10-12"]
    A = holdout.drop(A.set_index("day")).reset_index().reset_index(drop=True)
    print(len(A), "trades", A.day.min(), A.day.max())
    A["pnl_own"] = A.x
    U_idx = A.index[A.mk == "USDJPY"]
    preds = {}
    for seed in (0, 1, 2):
        q = pd.Series(np.nan, index=A.index)
        for Y in range(2012, 2026):
            tr = A[A.day < pd.Timestamp(f"{Y}-01-01") - pd.Timedelta(days=10)]
            te = A[(A.day >= f"{Y}-01-01") & (A.day < f"{Y + 1}-01-01") & (A.mk == "USDJPY")]
            if len(te) == 0:
                continue
            m = GradientBoostingRegressor(loss="quantile", alpha=0.6, max_depth=2, n_estimators=100, learning_rate=0.05,
                                          subsample=0.8, random_state=seed)
            m.fit(tr[FEATS], tr.mfe)
            q[te.index] = m.predict(te[FEATS])
        preds[seed] = q
    U = A.loc[U_idx].copy()
    ok = preds[0][U.index].notna()
    U = U[ok]
    print("USDJPY OOS trades", len(U), "median MFE(ATR)", round(U.mfe.median(), 3))

    def run(tp_series):
        pnl = [tp_result(r, tp_series.loc[i], r.R) for i, r in zip(U.index, U.itertuples())] \
            if False else [tp_result(r, tp_series.loc[i], r.R) for i, r in zip(U.index, U.itertuples())]
        return pd.Series(pnl, index=U.index)

    res = {}
    own = U.x
    res["own"] = own
    tps = {}
    for seed in (0, 1, 2):
        tps[f"q{seed}"] = np.maximum(0.5, preds[seed][U.index])
    medtp = float(np.median(np.concatenate([tps[k].to_numpy() for k in tps])))
    tps["fixed"] = pd.Series(medtp, index=U.index)
    print("median predicted TP (ATR)", round(medtp, 3))
    for k, s in tps.items():
        res[k] = run(s)
    print(f"{'arm':8s} " + " ".join(f"{m}x all/<=17/18+" .ljust(22) for m in (1, 1.5, 2)))
    summ = {}
    for k, p in res.items():
        line = []
        for mult in (1, 1.5, 2):
            d = daily(U.assign(n=net(U, p, mult)), "n")
            line.append(f"{sh(d):.2f}/{sh(d[:'2017']):.2f}/{sh(d['2018':]):.2f}".ljust(22))
        summ[k] = daily(U.assign(n=net(U, p, 1)), "n")
        print(f"{k:8s} " + " ".join(line))
    # book gain via book_sim
    import book_sim as B
    bl = B.legs()["breakout"]
    plain = summ["own"]
    kscale = bl.std() / plain.reindex(bl.index).fillna(0).std()
    print("scale", round(kscale, 6))
    best = "q0"
    for col, mult, name in ((1, 1, "ml_quantile_exit_breakout_noise"), (2, 1.5, "ml_quantile_exit_breakout_noise_stress")):
        d = daily(U.assign(n=net(U, res[best], mult)), "n").reindex(plain.index).fillna(0)
        pre = daily(U.assign(n=net(U, res["own"], mult)), "n")
        d = d * kscale
        d.index.name = "day"
        d.name = "r"
        d.to_csv(OUT / f"{name}.csv", header=True)
    print("written (first OOS year 2012; days before = zero)")
