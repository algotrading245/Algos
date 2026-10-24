"""Erb & Harvey (2013) style rate-shock rule: DGS10 5-day change z-scored by 60d sd of that change.
z>1: short XAUUSD, long USDJPY, short NSXUSD; z<-1 opposite. Hold 5 trading days, one position at a time,
signal uses DGS10 up to the prior day. Same params on 3 markets. Holdout dropped.
Writes marketdata/candidates/erb_yield_shock{,_stress}.csv and _markets.csv.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST_BP = {"XAUUSD": 1.0, "USDJPY": 0.8, "NSXUSD": 2.0}
SIGN = {"XAUUSD": -1, "USDJPY": 1, "NSXUSD": -1}
SPLIT = pd.Timestamp("2018-01-01")
HOLD = 5


def closes(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    c = d.close.resample("1D").last().dropna()
    return c[c.index.dayofweek < 5]


def signal():
    y = pd.read_csv(ROOT / "marketdata" / "fred" / "DGS10.csv", parse_dates=["observation_date"]).set_index("observation_date").DGS10
    y = y.dropna()
    dy = y.diff(5)
    z = dy / dy.rolling(60).std()
    return z


def run(sym, k, z):
    c = closes(sym)
    r = np.log(c / c.shift(1)).fillna(0)
    zz = z.reindex(c.index, method="ffill").shift(1)  # known at prior day
    pos = pd.Series(0.0, index=c.index)
    net = pd.Series(0.0, index=c.index)
    i, n, ntr = 0, len(c), 0
    zv = zz.values
    while i < n:
        if not np.isnan(zv[i]) and abs(zv[i]) > 1:
            s = np.sign(zv[i]) * SIGN[sym]
            j = min(i + HOLD, n)
            net.iloc[i:j] = s * r.iloc[i:j].values
            net.iloc[j - 1] -= COST_BP[sym] * 1e-4 * k
            ntr += 1
            i = j
        else:
            i += 1
    return net, ntr


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    z = signal()
    out = {}
    for k, name in ((0.0, "gross"), (1.0, ""), (1.5, "_stress"), (2.0, "_2x")):
        df = pd.DataFrame({s: run(s, k, z)[0] for s in COST_BP}).fillna(0)
        out[name] = df
        print(f"cost {k}x")
        for s in df:
            a, b = df[s][df.index < SPLIT], df[s][df.index >= SPLIT]
            print(f"  {s}: Sharpe train {sharpe(a):.2f} test {sharpe(b):.2f}  mean bp/day {df[s].mean()*1e4:.2f}")
        eq = df.mean(axis=1)
        print(f"  equal-weight: train {sharpe(eq[eq.index < SPLIT]):.2f} test {sharpe(eq[eq.index >= SPLIT]):.2f}")
    print("trades", {s: run(s, 1.0, z)[1] for s in COST_BP})
    for name in ("", "_stress"):
        out[name].mean(axis=1).rename("r").to_csv(ROOT / "marketdata" / "candidates" / f"erb_yield_shock{name}.csv", index_label="day")
    out[""].to_csv(ROOT / "marketdata" / "candidates" / "erb_yield_shock_markets.csv", index_label="day")
