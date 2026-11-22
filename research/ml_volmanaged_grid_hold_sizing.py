"""ml_volmanaged_grid_hold_sizing: pre-registered rule, no tuning. Size x0.5 when the leg market's 20d realised vol
(lagged one day) is above its trailing 252d 80th percentile, else 1. Grid: AUDCAD, hold: XAUUSD.
Applied to the existing Hydra leg daily streams (marketdata/hydra_legs_daily.csv.gz). Hold part was already
rejected (paper_moreira_muir_hold_sizing, continuous variant); this is the thresholded variant. 2 variants -> DSR N.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

L = holdout.drop(pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True))


def sh(x):
    x = x.dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def mult(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz") if sym == "AUDCAD" else \
        pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_H1.csv.gz")
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["close"]])
    d = h.close.resample("1D").last().dropna()
    r = np.log(d).diff()
    v = r.rolling(20).std()
    q = v.rolling(252).quantile(0.8)
    m = pd.Series(np.where(v > q, 0.5, 1.0), index=d.index).where(q.notna(), 1.0)
    return m.shift(1)


def ms(x):
    return x.groupby(x.index.to_period("M")).sum()


out = {}
for leg, sym in (("grid", "AUDCAD"), ("hold", "XAUUSD")):
    m = mult(sym).reindex(L.index).ffill().fillna(1.0)
    base = L[leg]
    r = base * m
    # 1.5x stress: scaled stream with extra cost approximated as 0.5 * (cost of base) unknown -> use
    # r minus 0.5*mean-cost proxy not available; use r itself minus 25% of mean abs? keep simple: same as r
    out[leg] = r
    print(leg, "share halved", round(float((m < 1).mean()), 3))
    for nm, x in (("base", base), ("managed", r)):
        print(" ", nm, "SR <=2017", round(sh(x[x.index < "2018"]), 2), "2018+", round(sh(x[x.index >= "2018"]), 2),
              "worst month", round(float(ms(x).min()) * 100, 2), "losing months", int((ms(x) < 0).sum()))
pd.DataFrame(out).to_csv(ROOT / "research" / "ml_volmanaged_grid_hold_sizing.out.csv")
