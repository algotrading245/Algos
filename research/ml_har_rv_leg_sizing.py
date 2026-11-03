"""HAR-RV (Corsi 2009) leg sizing for breakout (USDJPY RV) and noise (SPXUSD RV, US500 proxy), past-only.
mult_t+1 = clip(median_250d(vol) / HARforecast(vol_t+1), 0.5, 1.5); forecast from monthly-refit expanding OLS on log vol.
Judged: leg and book Sharpe halves, book 2018+ vs unscaled, random-multiplier control, vol-target-only control."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
import book_sim as B
import holdout

OUT = "marketdata/candidates/"


def daily_rv(sym):
    d = pd.read_csv(f"marketdata/histdata/{sym}_M1.csv.gz", usecols=["time", "close"])
    d = holdout.drop(d.assign(day=pd.to_datetime(d.time, unit="s")).set_index("day"))
    c = d["close"]
    c5 = c.resample("5min").last().dropna()
    r = np.log(c5).diff().dropna()
    r = r[(r.index.hour != 23) & (r.index.hour != 0)] if False else r
    rv = (r ** 2).groupby(r.index.normalize()).sum()
    rv = rv[rv > 0]
    return np.sqrt(rv)


def har_mult(vol, idx, lo=0.5, hi=1.5, seed_shift=0):
    v = np.log(vol[vol > 0])
    X = pd.DataFrame({"d": v, "w": v.rolling(5).mean(), "m": v.rolling(22).mean()})
    y = v.shift(-1)
    D = pd.concat([X, y.rename("y")], axis=1).dropna()
    pred = pd.Series(np.nan, index=v.index)
    months = pd.PeriodIndex(v.index, freq="M")
    ok = X.dropna()
    beta = None
    last = None
    for day in ok.index:
        m = months[v.index.get_loc(day)]
        if m != last:
            tr = D[D.index < day - pd.Timedelta(days=1)]  # target of day-1 known only at day
            if len(tr) > 500:
                A = np.c_[np.ones(len(tr)), tr[["d", "w", "m"]].to_numpy()]
                beta = np.linalg.lstsq(A, tr["y"].to_numpy(), rcond=None)[0]
            last = m
        if beta is not None:
            pred[day] = beta[0] + beta[1] * X.at[day, "d"] + beta[2] * X.at[day, "w"] + beta[3] * X.at[day, "m"]
    fc = np.exp(pred)
    med = vol.rolling(250, min_periods=100).median()
    mult = (med / fc).clip(lo, hi)
    vt = (med / vol.rolling(20).mean()).clip(lo, hi)  # vol-target-only control (trailing)
    # forecast made at close of day t applies to P&L of next trading day
    f = lambda s: s.reindex(idx, method="ffill").shift(0)
    return f(mult).shift(1), f(vt).shift(1)


def main():
    L = B.legs()
    base_b, _ = B.combine(L)
    s0 = B.sharpe(B.risk_layer(base_b)[lambda x: x.index >= B.SPLIT])
    print("baseline book 2018+ (risk layer):", round(s0, 3), " raw combine 2018+", round(B.sharpe(base_b[base_b.index >= B.SPLIT]), 3))
    rv = {"breakout": daily_rv("USDJPY"), "noise": daily_rv("SPXUSD")}
    mult, vtm = {}, {}
    for k in rv:
        mult[k], vtm[k] = har_mult(rv[k], L.index)
        mm = mult[k].dropna()
        print(k, "mult mean %.2f sd %.2f n %d" % (mm.mean(), mm.std(), len(mm)))
        raw = L[k].dropna()
        for nm, m in (("har", mult[k]), ("vt", vtm[k])):
            r = (raw * m.reindex(raw.index).fillna(1.0))
            print(" ", k, nm, "Sharpe all/pre/post: %.2f %.2f %.2f" % (B.sharpe(r), B.sharpe(r[r.index < B.SPLIT]), B.sharpe(r[r.index >= B.SPLIT])),
                  " raw %.2f %.2f %.2f" % (B.sharpe(raw), B.sharpe(raw[raw.index < B.SPLIT]), B.sharpe(raw[raw.index >= B.SPLIT])))

    def book(m, label, ret=False):
        E = {k: L[k] * m[k].reindex(L.index).fillna(1.0) for k in rv}
        LL = L.copy()
        for k in rv:
            LL[k] = E[k].where(L[k].notna())
        b, _ = B.combine(LL)
        x = B.risk_layer(b)
        a = x[x.index >= B.SPLIT]
        mo = B.months(x)
        print("%-12s book2018+ %.3f  all %.3f  worst month %.4f  losing months %d/%d  halves %.2f/%.2f" % (
            label, B.sharpe(a), B.sharpe(x), mo.min(), (mo < 0).sum(), len(mo),
            B.sharpe(x[x.index < B.SPLIT]), B.sharpe(a)))
        return (b, x) if ret else B.sharpe(a)

    book({k: pd.Series(1.0, index=L.index) for k in rv}, "unscaled")
    sh = book(mult, "HAR")
    book(vtm, "vol-target")
    rng = np.random.default_rng(0)
    ctl = []
    for s in range(20):
        mr = {k: pd.Series(rng.permutation(mult[k].fillna(1.0).to_numpy()), index=L.index) for k in rv}
        E = L.copy()
        for k in rv:
            E[k] = (L[k] * mr[k]).where(L[k].notna())
        b, _ = B.combine(E)
        x = B.risk_layer(b)
        ctl.append(B.sharpe(x[x.index >= B.SPLIT]))
    print("random-multiplier control book2018+: mean %.3f sd %.3f max %.3f" % (np.mean(ctl), np.std(ctl), np.max(ctl)))
    w = {"breakout": 0.25, "noise": 0.037}  # book weights of the two re-sized legs
    r = sum(w[k] * (L[k] * mult[k].reindex(L.index).fillna(1.0)) for k in w).dropna() / sum(w.values())
    r.rename("r").rename_axis("day").to_csv(OUT + "ml_har_rv_leg_sizing.csv")
    # stress: the HAR sizing changes size, not trade count; costs are in the leg series, so the 1.5x file takes the
    # same series less half of the legs' average cost drag (taken as 0.5 x 1bp/day, conservative for a 2-leg mix)
    (r - 0.00005).rename("r").rename_axis("day").to_csv(OUT + "ml_har_rv_leg_sizing_stress.csv")
    return mult, L


if __name__ == "__main__":
    main()
