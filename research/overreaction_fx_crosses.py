"""Pre-registered variant of overreaction_fx: identical rule (2sd, n=20, 01:00->08:00 fade), crosses only.
Costs round trip bp: EURJPY 1.4, GBPJPY 2.0, AUDJPY 1.8, AUDCAD 2.0, EURGBP 1.2. No parameter changed."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

PAIRS = {"EURJPY": 1.4, "GBPJPY": 2.0, "AUDJPY": 1.8, "AUDCAD": 2.0, "EURGBP": 1.2}
N, K = 20, 2.0


def trades(name):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{name}_M1.csv.gz")
    d = d.drop_duplicates("time").sort_values("time")
    d["dt"] = pd.to_datetime(d.time, unit="s")
    d = d[d.dt < holdout.START]
    d["day"] = d.dt.dt.normalize()
    d["mod"] = d.dt.dt.hour * 60 + d.dt.dt.minute
    d = d[d.dt.dt.dayofweek < 5]
    o1 = d[d["mod"] == 60].groupby("day").open.first()
    c22 = d[d["mod"] == 22 * 60 + 59].groupby("day").close.last()
    o8 = d[d["mod"] == 8 * 60].groupby("day").open.first()
    df = pd.DataFrame({"o1": o1, "c22": c22, "o8": o8}).dropna(subset=["o1", "c22"])
    df["R"] = df.c22 / df.o1 - 1
    m = df.R.rolling(N).mean().shift(1)
    s = df.R.rolling(N).std().shift(1)
    sig = pd.Series(0, index=df.index)
    sig[df.R > m + K * s] = -1
    sig[df.R < m - K * s] = 1
    sn = sig.shift(1)
    sn = sn.where(df.index.to_series().diff().dt.days <= 4, 0).fillna(0)
    g = (sn * (df.o8 / df.o1 - 1)).where(sn != 0).dropna()
    return g


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


idx = pd.bdate_range("2009-01-01", holdout.START - pd.Timedelta(days=1))
D = {1.0: {}, 1.5: {}, 2.0: {}}
for p, c in PAIRS.items():
    g = trades(p)
    h1, h2 = g[g.index < "2018-01-01"], g[g.index >= "2018-01-01"]
    print(p, len(g), "net1x bp", round((h1 - c * 1e-4).mean() * 1e4, 2), round((h2 - c * 1e-4).mean() * 1e4, 2), "n", len(h1), len(h2))
    for m in D:
        D[m][p] = (g - c * 1e-4 * m).reindex(idx).fillna(0)
for m in D:
    df = pd.DataFrame(D[m])
    r = df.mean(axis=1)
    print(f"book {m}x: to2017 {sh(r[r.index < '2018-01-01']):.2f} 2018on {sh(r[r.index >= '2018-01-01']):.2f}")
    if m == 1.0:
        for p in PAIRS:
            print("  ", p, round(sh(df[p][df.index < '2018-01-01']), 2), round(sh(df[p][df.index >= '2018-01-01']), 2))
cand = ROOT / "marketdata" / "candidates"
for m, f in ((1.0, "var_overreaction_fx_crosses.csv"), (1.5, "var_overreaction_fx_crosses_stress.csv")):
    r = pd.DataFrame(D[m]).mean(axis=1)
    pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(cand / f, index=False)
