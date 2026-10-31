"""Heston-Korajczyk-Sadka (2010) intraday periodicity, hourly, on EURUSD, USDJPY, XAUUSD, SPXUSD, NSXUSD.
(Paper not readable here, HTTP 403: rule taken from the queue item, unverified against the paper.)

For hour h (server clock, hours 1..22, rollover 23-01 out): signal = mean of the h-hour return over the previous 20 trading
days; long if in the top tercile of its trailing 250-day distribution, short if bottom tercile, else flat. Hold that hour.
Same parameters on all markets. Costs round trip bp: 1x / 1.5x / 2x. Holdout dropped.
Writes marketdata/candidates/hks_periodicity{,_stress}.csv and _markets.csv.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST_BP = {"XAUUSD": 1.0, "EURUSD": 0.8, "USDJPY": 0.8, "SPXUSD": 1.5, "NSXUSD": 2.0}
SPLIT = pd.Timestamp("2018-01-01")


def daily(sym, k):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    h = d.resample("1h").agg({"open": "first", "close": "last"}).dropna()
    h["r"] = np.log(h.close / h.open)
    h = h[(h.index.dayofweek < 5) & (h.index.hour >= 1) & (h.index.hour < 23)]
    h["day"] = h.index.normalize()
    p = h.pivot_table(index="day", columns=h.index.hour, values="r")
    sig = p.shift(1).rolling(20, min_periods=20).mean()
    hi = sig.rolling(250, min_periods=120).quantile(2 / 3)
    lo = sig.rolling(250, min_periods=120).quantile(1 / 3)
    pos = (sig > hi).astype(float) - (sig < lo).astype(float)
    n = (pos != 0) & p.notna()
    net = (pos * p).fillna(0) - n * COST_BP[sym] * 1e-4 * k
    s = net.where(n, 0).sum(axis=1)
    return s.where(n.sum(axis=1) > 0, 0.0), n.sum(axis=1)


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    out = {}
    for k, name in ((0.0, "gross"), (1.0, ""), (1.5, "_stress"), (2.0, "_2x")):
        cols = {s: daily(s, k)[0] for s in COST_BP}
        df = pd.DataFrame(cols).fillna(0)
        out[name] = df
        print(f"cost {k}x")
        for s in df:
            a, b = df[s][df.index < SPLIT], df[s][df.index >= SPLIT]
            print(f"  {s}: Sharpe train {sharpe(a):.2f} test {sharpe(b):.2f}  mean bp/day {df[s].mean()*1e4:.2f}")
        eq = df.mean(axis=1)
        print(f"  equal-weight: train {sharpe(eq[eq.index < SPLIT]):.2f} test {sharpe(eq[eq.index >= SPLIT]):.2f}")
    print("trades/day", {s: round(daily(s, 1.0)[1].mean(), 1) for s in COST_BP})
    for name in ("", "_stress"):
        out[name].mean(axis=1).rename("r").to_csv(ROOT / "marketdata" / "candidates" / f"hks_periodicity{name}.csv", index_label="day")
    out[""].to_csv(ROOT / "marketdata" / "candidates" / "hks_periodicity_markets.csv", index_label="day")
