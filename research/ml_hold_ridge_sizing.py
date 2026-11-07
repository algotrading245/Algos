"""ml_hold_ridge_sizing: Ridge (alpha 10) predicts hold-leg next-20d pnl / trailing 60d pnl vol; size = clip(1+0.5*z,.25,1.75).
Walk-forward, expanding window refit yearly from 2008, 20-day purge. k fixed before run. VIX dropped (ends 2025-03, partial).
Stop before gating if OOF IC <= 0.05."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

TARGET, SWAP, COST, K = 0.107, 0.068, 0.8, 0.5
OUT = ROOT / "marketdata" / "candidates"


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def daily(sym):
    f = ROOT / "marketdata" / "histdata" / f"{sym}_H1.csv.gz"
    if f.exists():
        g = pd.read_csv(f)
    else:
        g = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz", usecols=["time", "close"])
        g = g[(g.time % 3600 == 0)]
    g.index = pd.to_datetime(g.time, unit="s")
    g = holdout.drop(g[["close"]])
    D = g.close[g.index.hour == 22]
    D.index = D.index.normalize()
    return D


D = daily("XAUUSD")
R = np.log(D).diff()
vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
sig = (sum(np.sign(D / D.shift(k) - 1) for k in (20, 60, 120, 250)) / 4).clip(lower=0)
pos0 = (sig * TARGET / vol).clip(-3, 3).shift(1)


def leg(pos, mult=1.0):
    return pos * R - pos.diff().abs() * COST * mult * 1e-4 / 2 - pos.clip(lower=0) * SWAP * mult / 252


base, base15 = leg(pos0), leg(pos0, 1.5)
book = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).hold
print("repro corr", round(base.corr(book), 3))

gross = pos0 * R
v60 = gross.rolling(60).std().replace(0, np.nan)
y = gross.rolling(20).sum().shift(-20) / v60  # forward 20d pnl / trailing vol (uses future: label only)
lr = np.log(D)
rv = R.rolling(63).std()
F = pd.DataFrame(index=D.index)
for k in (21, 63, 252):
    F[f"m{k}"] = (lr - lr.shift(k)) / (R.rolling(63).std() * np.sqrt(k))
F["volrank"] = rv.rolling(504).apply(lambda a: (a[-1] >= a).mean(), raw=True)
F["dist200"] = (lr - np.log(D.rolling(200).mean())) / (rv * np.sqrt(200))
fx = []
for s in ("EURUSD", "USDJPY"):
    d = np.log(daily(s))
    fx.append((d - d.shift(63)).reindex(D.index).ffill() * (-1 if s == "EURUSD" else 1))
F["dxy"] = (fx[0] + fx[1]) / 2
F = F.shift(1)  # lag one day
ok = F.notna().all(axis=1)

pred = pd.Series(np.nan, index=D.index)
for yr in range(2008, 2026):
    tr_end = pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=30)  # purge >20 trading days
    trm = ok & y.notna() & (D.index < tr_end)
    te = ok & (D.index.year == yr)
    if trm.sum() < 500 or te.sum() == 0:
        continue
    mu, sd = F[trm].mean(), F[trm].std()
    m = Ridge(alpha=10).fit((F[trm] - mu) / sd, y[trm])
    pred[te] = m.predict((F[te] - mu) / sd)
# z of prediction using expanding past stats
z = (pred - pred.expanding(250).mean().shift(1)) / pred.expanding(250).std().shift(1)
mask = pred.notna() & y.notna() & (pos0 > 0)
ic = pd.concat([pred[mask], y[mask]], axis=1).corr(method="spearman").iloc[0, 1]
ic_a = pd.concat([pred[mask & (pred.index >= "2018")], y[mask & (pred.index >= "2018")]], axis=1).corr(method="spearman").iloc[0, 1]
print("OOF IC (hold on days) all", round(ic, 3), "2018+", round(ic_a, 3), "n", int(mask.sum()))
if ic <= 0.05:
    print("IC <= 0.05: STOP per pre-registration")

mult = (1 + K * z).clip(0.25, 1.75).fillna(1.0)
pos = pos0 * mult
r, r15 = leg(pos), leg(pos, 1.5)
for nm, a, b in (("base", base, base15), ("ridge", r, r15)):
    print(nm, "SR <=2017", round(sh(a[a.index < "2018"]), 2), "2018+", round(sh(a[a.index >= "2018"]), 2),
          "1.5x all", round(sh(b), 2))
ms = lambda x: x.groupby(x.index.to_period("M")).sum()
print("losing months base", int((ms(base) < 0).sum()), "ridge", int((ms(r) < 0).sum()))
if ic > 0.05:
    for f, x in ((OUT / "ml_hold_ridge_sizing.csv", r), (OUT / "ml_hold_ridge_sizing_stress.csv", r15)):
        x.dropna().rename("r").rename_axis("day").to_csv(f)
