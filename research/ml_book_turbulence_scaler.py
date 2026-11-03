"""Turbulence-index overlay on the whole book (Kritzman-Li 2010, as restated in Kamauchi-Yokouchi 2021).

Weekly returns of 6 markets (XAUUSD, SPXUSD, NSXUSD, EURUSD, USDJPY, AUDCAD; M1 histdata, holdout dropped).
TI_w = (y_w - mu)' Sigma^-1 (y_w - mu), mu/Sigma from the 104 weeks BEFORE week w.
Weight for the next week = 1 - 0.4 * pct rank of the 13-week mean TI within the last 104 weeks of that mean (0.6..1.0).
One pre-set rule, no fit: 1 trial. Overlay is applied to the book after the risk layer (tools/book_sim).
    python research/ml_book_turbulence_scaler.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import book_sim as B  # noqa: E402

SPLIT = pd.Timestamp("2018-01-01")
SYMS = ["XAUUSD", "SPXUSD", "NSXUSD", "EURUSD", "USDJPY", "AUDCAD"]
WIN, AVG = 104, 13


def weekly_close(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    return d.close.resample("W-FRI").last().dropna()


def weight_series():
    W = pd.concat({s: np.log(weekly_close(s)).diff() for s in SYMS}, axis=1).dropna()
    y = W.values
    ti = np.full(len(W), np.nan)
    for i in range(WIN, len(W)):
        past = y[i - WIN:i]
        mu = past.mean(0)
        S = np.cov(past.T)
        dlt = y[i] - mu
        ti[i] = dlt @ np.linalg.pinv(S) @ dlt
    ti = pd.Series(ti, index=W.index)
    avg = ti.rolling(AVG).mean()
    rank = avg.rolling(WIN).apply(lambda a: (a[:-1] < a[-1]).mean() if len(a) > 1 else np.nan, raw=True)
    w = 1 - 0.4 * rank
    return w, ti


def sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def maxdd(x):
    c = x.cumsum()
    return float((c - c.cummax()).min())


def monthly(x):
    return x.groupby([x.index.year, x.index.month]).sum()


def main():
    w, ti = weight_series()
    base_legs = B.legs()
    book, _ = B.combine(base_legs)
    b = B.risk_layer(book)
    # weight known at Friday close of week k applies to days of week k+1 (days after that Friday)
    wd = w.dropna().reindex(b.index.union(w.index)).ffill().reindex(b.index)
    # a day on/after Monday uses the Friday before: shift weekly stamps by 1 day so Friday close applies from Saturday on
    ws = w.dropna()
    ws.index = ws.index + pd.Timedelta(days=1)
    wd = ws.reindex(ws.index.union(b.index)).ffill().reindex(b.index)
    ok = wd.notna()
    b0, wv = b[ok], wd[ok]
    b1 = b0 * wv
    # equal-vol comparison: rescale scaled stream to the unscaled one's vol over the whole period
    k = b0.std() / b1.std()
    b1n = b1 * k
    print(f"days {len(b0)} from {b0.index[0].date()} to {b0.index[-1].date()}; mean weight {wv.mean():.3f}, vol scale k {k:.3f}")
    for name, sl in (("to 2017", b0.index < SPLIT), ("2018 on", b0.index >= SPLIT), ("all", b0.index > b0.index[0])):
        x0, x1, x1n = b0[sl], b1[sl], b1n[sl]
        m0, m1 = monthly(x0), monthly(x1)
        print(f"{name:8s} Sharpe base {sharpe(x0):.2f} scaled {sharpe(x1):.2f} | maxDD base {maxdd(x0):.3f} scaled {maxdd(x1):.3f}"
              f" scaled@equal-vol {maxdd(x1n):.3f} | losing months base {(m0<0).sum()}/{len(m0)} scaled {(m1<0).sum()}/{len(m1)}"
              f" | worst month base {m0.min():.3f} scaled {m1.min():.3f}")
    # yearly Sharpe 2018+
    for yr in sorted(set(b0.index.year)):
        if yr >= 2018:
            s = b0.index.year == yr
            print(f"  {yr}: base {sharpe(b0[s]):.2f} scaled {sharpe(b1[s]):.2f}")
    # bootstrap-free robustness: sharpe diff of daily paired streams, 2018+ (t-stat)
    sl = b0.index >= SPLIT
    d = (b1n - b0)[sl]
    print(f"paired diff (equal vol) 2018+: mean {d.mean()*252:.4f}/yr t {d.mean()/d.std()*np.sqrt(len(d)):.2f}")
    # worst-weeks check: mean book return when weight <0.7
    lo = wv < 0.7
    print(f"days with weight<0.7: {lo.mean():.1%}; base mean/day there {b0[lo].mean():.5f} vs others {b0[~lo].mean():.5f}; vol there {b0[lo].std():.4f} vs {b0[~lo].std():.4f}")
    out = ROOT / "marketdata" / "candidates"
    pd.DataFrame({"day": b1n.index.strftime("%Y-%m-%d"), "r": b1n.values}).to_csv(out / "ml_book_turbulence_scaler.csv", index=False)


if __name__ == "__main__":
    main()
