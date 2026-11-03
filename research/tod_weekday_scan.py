"""Time-of-day x weekday scan: XAUUSD, EURUSD, USDJPY, SPXUSD (US500), 2010/2009 on, split 2018, holdout dropped.

Cells are (hour, weekday) of the data clock, return = hourly bar open->close, from M1. Selection on the train half
only (to 2017): |t| above the Bonferroni bar over all cells (4 symbols x 120 cells). Judged on 2018 on: same sign,
net of cost at 1x / 1.5x / 2x. Survivors are written as one equal-weight stream for tools/gates.py.

    python research/tod_weekday_scan.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST_BP = {"XAUUSD": 1.0, "EURUSD": 0.8, "USDJPY": 0.8, "SPXUSD": 1.5}   # round trip, as research/atlas_scan.py
SYMS = list(COST_BP)
SPLIT = pd.Timestamp("2018-01-01")
NCELL = len(SYMS) * 120
BAR = stats.norm.isf(0.05 / NCELL / 2)


def hourly(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    h = d.resample("1h").agg({"open": "first", "close": "last"}).dropna()
    h["r"] = np.log(h.close / h.open)
    h["hr"] = h.index.hour
    h["wd"] = h.index.dayofweek
    return h[h.wd < 5]


def tstat(x):
    return x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 30 and x.std() > 0 else 0.0


if __name__ == "__main__":
    picks = {}
    for s in SYMS:
        h = hourly(s)
        tr, te = h[h.index < SPLIT], h[h.index >= SPLIT]
        rows = []
        for (hr, wd), g in tr.groupby(["hr", "wd"]):
            t1 = tstat(g.r)
            t2 = tstat(te[(te.hr == hr) & (te.wd == wd)].r)
            rows.append((hr, wd, t1, t2, g.r.mean() * 1e4))
        r = pd.DataFrame(rows, columns=["hr", "wd", "t_train", "t_test", "bp"])
        sel = r[r.t_train.abs() > BAR]
        print(f"{s}: cells {len(r)}, train |t|>{BAR:.2f}: {len(sel)}; max |t| train {r.t_train.abs().max():.2f}; "
              f"same sign test t>=2: {int(((np.sign(sel.t_train) == np.sign(sel.t_test)) & (sel.t_test.abs() >= 2)).sum())}")
        picks[s] = (h, sel)
    out = []
    for s, (h, sel) in picks.items():
        for _, c in sel.iterrows():
            sg = np.sign(c.t_train)
            g = h[(h.hr == c.hr) & (h.wd == c.wd)]
            out.append(pd.DataFrame({"day": g.index.normalize(), "r": sg * g.r, "s": s}))
    if not out:
        print("no cell clears the Bonferroni bar on the train half: nothing to gate")
        sys.exit(0)
    o = pd.concat(out)
    for k, name in ((1.0, ""), (1.5, "_stress")):
        o2 = o.copy()
        o2["r"] = o2.r - o2.s.map(COST_BP) * 1e-4 * k
        d = o2.groupby("day").r.sum() / max(1, o.groupby("s").size().shape[0])
        d.rename("r").to_csv(ROOT / "marketdata" / "candidates" / f"tod_weekday_scan{name}.csv", index_label="day")
    print(o.groupby("s").size())
