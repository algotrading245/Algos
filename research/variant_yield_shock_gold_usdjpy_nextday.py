"""variant_yield_shock_gold_usdjpy_nextday: 1-day DGS10 change z (sd of last 60 daily changes, past only).
|z|>=1.5 -> trade sign for next H trading days (returns of days t+1..t+H, signal known at the t NY close).
Signs fixed: XAUUSD -1, EURUSD -1, USDJPY +1 vs yield change. Main H=3, second cell H=1 (2 trials).
Cost per trade round turn bp: XAU 1.0, USDJPY 0.8, EURUSD 0.8 (x1, 1.5, 2). Equal weight combo.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "variant_yield_shock_gold_usdjpy_nextday"
COST = {"XAUUSD": 1.0, "USDJPY": 0.8, "EURUSD": 0.8}
SIGN = {"XAUUSD": -1, "USDJPY": 1, "EURUSD": -1}
SPLIT = pd.Timestamp("2018-01-01")


def closes(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    c = d.close.resample("1D").last().dropna()
    return c[c.index.dayofweek < 5]


y = pd.read_csv(ROOT / "marketdata" / "fred" / "DGS10.csv", parse_dates=["observation_date"]).set_index("observation_date").DGS10.dropna()
dy = y.diff()
Z = dy / dy.rolling(60).std().shift(1)
C = {s: closes(s) for s in COST}


def run(sym, H, k):
    c = C[sym]
    r = np.log(c / c.shift(1)).fillna(0).values
    z = Z.reindex(c.index).values  # FRED date t == calendar day t
    n = len(c)
    net = np.zeros(n)
    i = 0
    while i < n - 1:
        if not np.isnan(z[i]) and abs(z[i]) >= 1.5:
            s = np.sign(z[i]) * SIGN[sym]
            j = min(i + 1 + H, n)
            net[i + 1:j] = s * r[i + 1:j]
            net[j - 1] -= COST[sym] * 1e-4 * k
            i = j - 1
        i += 1
    return pd.Series(net, index=c.index)


def sh(x):
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


for H in (3, 1):
    print("== H", H)
    for s in COST:
        a = run(s, H, 1.0)
        g = run(s, H, 0.0)
        print(s, "gross bp/day", round(g.mean() * 1e4, 2), "SR<=2017", round(sh(a[a.index < SPLIT]), 2),
              "2018+", round(sh(a[a.index >= SPLIT]), 2), "1.5x", round(sh(run(s, H, 1.5)), 2))
    for k in (1.0, 1.5, 2.0):
        df = pd.DataFrame({s: run(s, H, k) for s in COST}).fillna(0)
        e = df.mean(axis=1)
        print("combo", k, "x: <=2017", round(sh(e[e.index < SPLIT]), 2), "2018+", round(sh(e[e.index >= SPLIT]), 2))
        if H == 3 and k == 1.0:
            main = e
            mk = df
        if H == 3 and k == 1.5:
            st = e

main.rename("r").rename_axis("day").to_csv(OUT / f"{ID}.csv")
st.rename("r").rename_axis("day").to_csv(OUT / f"{ID}_stress.csv")
mk.rename_axis("day").to_csv(OUT / f"{ID}_markets.csv")
