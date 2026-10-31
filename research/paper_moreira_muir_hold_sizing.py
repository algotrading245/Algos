"""paper_moreira_muir_hold_sizing: Moreira & Muir (2017) vol-managed scale on the gold hold leg.
Scale_t = clip(raw_t / expanding mean(raw), 0.25, 2.0), raw_t = 1 / variance of the hold leg's own unscaled pnl
over the previous 22 days (lagged one day). Expanding mean = past-only c. No free parameter. Costs/swap on scaled pos.
Also tested on grid and bh series as belief check (XAUUSD, US500, US100 buy-and-hold).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

TARGET, SWAP, COST = 0.107, 0.068, 0.8
OUT = ROOT / "marketdata" / "candidates"


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def scale_of(p):
    var = (p.rolling(22).var()).shift(1)
    raw = 1.0 / var.replace(0, np.nan)
    raw = raw.clip(upper=raw.quantile(0.99) if raw.notna().any() else None)
    c = raw.expanding(250).mean().shift(1)
    return (raw / c).clip(0.25, 2.0)


g = pd.read_csv(ROOT / "marketdata" / "histdata" / "XAUUSD_H1.csv.gz")
g.index = pd.to_datetime(g.time, unit="s")
g = holdout.drop(g[["close"]])
D = g.close[g.index.hour == 22]
D.index = D.index.normalize()
R = np.log(D).diff()
vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
sig = (sum(np.sign(D / D.shift(k) - 1) for k in (20, 60, 120, 250)) / 4).clip(lower=0)
pos0 = (sig * TARGET / vol).clip(-3, 3).shift(1)


def leg(pos, mult=1.0):
    return pos * R - pos.diff().abs() * COST * mult * 1e-4 / 2 - pos.clip(lower=0) * SWAP * mult / 252


base, base15 = leg(pos0), leg(pos0, 1.5)
# scale from unscaled gross pnl of the position (past only)
gross = pos0 * R
s = scale_of(gross).fillna(1.0)
s = s.where(gross.expanding().count() > 300, 1.0)
pos = pos0 * s
r, r15 = leg(pos), leg(pos, 1.5)
book = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).hold
print("repro corr", round(base.corr(book), 3), "mean scale", round(float(s[pos0 > 0].mean()), 3))
for nm, a, b in (("base", base, base15), ("managed", r, r15)):
    print(nm, "SR <=2017", round(sh(a[a.index < "2018"]), 2), "2018+", round(sh(a[a.index >= "2018"]), 2),
          "1.5x all", round(sh(b), 2), "vol", round(float(a.std() * np.sqrt(252)), 3))
print("corr managed vs base", round(r.corr(base), 3))
ms = lambda x: x.groupby(x.index.to_period("M")).sum()
mb, mm = ms(base), ms(r)
print("losing months base", int((mb < 0).sum()), "managed", int((mm < 0).sum()), "worst month base",
      round(float(mb.min()) * 100, 2), "managed", round(float(mm.min()) * 100, 2))

# belief: buy-and-hold managed on XAUUSD, and other markets
mk = {}
for sym in ("XAUUSD", "US500", "US100", "EURUSD", "USDJPY"):
    f = ROOT / "marketdata" / "histdata" / f"{sym}_H1.csv.gz"
    if not f.exists():
        continue
    h = pd.read_csv(f)
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["close"]])
    d = h.close[h.index.hour == 22]
    d.index = d.index.normalize()
    rr = np.log(d).diff()
    sc = scale_of(rr).fillna(1.0)
    sc = sc.where(rr.expanding().count() > 300, 1.0)
    m = rr * sc.shift(0)  # scale uses lagged variance already
    d_sh = (sh(rr[rr.index >= "2005"]), sh(m[m.index >= "2005"]))
    print(sym, "bh SR", round(d_sh[0], 2), "managed", round(d_sh[1], 2))
    mk[sym] = m - rr  # excess
mk_df = pd.DataFrame({k: (v) for k, v in mk.items()})

# candidate: the increment of managing the hold (managed - base), alone it is overlay; write the managed leg
for f, x in ((OUT / "paper_moreira_muir_hold_sizing.csv", r), (OUT / "paper_moreira_muir_hold_sizing_stress.csv", r15)):
    x.dropna().rename("r").rename_axis("day").to_csv(f)
# markets file: managed minus unmanaged benefit per market is not a return stream; write managed returns
mr = {}
for sym in mk:
    pass
