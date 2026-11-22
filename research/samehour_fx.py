"""Same-half-hour continuation (Murphy & Thirumalai 2017) on EURUSD, USDJPY, XAUUSD, SPXUSD.

Signal for slot s on day t: sign of the mean slot-s return over the previous 5 trading days (past only).
Hold that 30-min bar, slots 08:00-20:30 data clock (rollover 23-01 excluded). Parameters fixed, not tuned.
Cost: round trip bp per trade, 1x / 1.5x / 2x. Holdout dropped. Writes marketdata/candidates/samehour_fx*.csv
and samehour_fx_markets.csv (per-market daily r).

    python research/samehour_fx.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST_BP = {"XAUUSD": 1.0, "EURUSD": 0.8, "USDJPY": 0.8, "SPXUSD": 1.5}
SPLIT = pd.Timestamp("2018-01-01")
LOOK = 5


def daily(sym, k):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    h = d.resample("30min").agg({"open": "first", "close": "last"}).dropna()
    h["r"] = np.log(h.close / h.open)
    h = h[(h.index.dayofweek < 5) & (h.index.hour >= 8) & (h.index.hour < 21)]
    h["day"] = h.index.normalize()
    h["slot"] = h.index.hour * 2 + h.index.minute // 30
    p = h.pivot_table(index="day", columns="slot", values="r")
    sig = np.sign(p.shift(1).rolling(LOOK, min_periods=LOOK).mean())   # previous 5 days only
    pnl = sig * p
    n = sig.notna() & p.notna() & (sig != 0)
    net = pnl.fillna(0) - n * COST_BP[sym] * 1e-4 * k
    return net.where(n, 0).sum(axis=1).where(n.sum(axis=1) > 0, 0.0), n.sum(axis=1)


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
    for name in ("", "_stress"):
        out[name].mean(axis=1).rename("r").to_csv(ROOT / "marketdata" / "candidates" / f"samehour_fx{name}.csv", index_label="day")
    out[""].to_csv(ROOT / "marketdata" / "candidates" / "samehour_fx_markets.csv", index_label="day")
