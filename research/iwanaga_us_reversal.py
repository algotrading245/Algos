"""Iwanaga: prior-day S&P 500 return reverses in the next day's intraday Japanese index futures.
Rule (fixed, no tuning): sign of the US500 NY-session close-to-close return (09:30 close to 16:00, last US day before the
local date), trade the opposite way on JPXJPY (Tokyo open 09:00 -> close 15:00) and GRXEUR (Berlin 09:00 -> 17:30).
Flat when |ret| < 0.25 x trailing 60-day sd of that return (past only).  Size = 0.01 / trailing 20-day sd of the leg's
open-to-close return, cap 4 (so it is a unit-vol leg like noise_gj).  Costs per round trip: JPN 2 bp, GER 1 bp;
1.5x and 2x shown.  Halves: to 2017, 2018 on.  Holdout dropped by holdout.drop.
    python research/iwanaga_us_reversal.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import holdout
from overnight_intraday_reversal import NY, matrix

SPLIT = pd.Timestamp("2018-01-01")
root = Path(__file__).resolve().parent.parent / "marketdata"
MK = {"JPXJPY": ("Asia/Tokyo", 540, 900, 2.0), "GRXEUR": ("Europe/Berlin", 540, 1050, 1.0)}


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def rep(l, x):
    print(f"{l:26s} all {sh(x):+.2f}  to2017 {sh(x[:SPLIT]):+.2f}  2018+ {sh(x[SPLIT:]):+.2f}  n={int((x != 0).sum())}")


d, p = matrix("SPXUSD", NY)
us = pd.Series(p[:, 960] / p[:, 570 - 1] - 1, index=d)   # NY 9:30 open-proxy ... see close-to-close below
cc = pd.Series(p[:, 960], index=d).dropna()
usr = (cc / cc.shift(1) - 1).dropna()
usr = usr[usr.index.dayofweek < 5]
usz = usr / usr.rolling(60).std().shift(1)


def leg(sym, cost, thr=0.25, sign=-1):
    zone, o, c, bp = MK[sym]
    days, q = matrix(sym, zone)
    q = pd.DataFrame(q.astype(float)).ffill(axis=1).to_numpy()
    po, pc = pd.Series(q[:, o], index=days), pd.Series(q[:, c], index=days)
    r = (pc / po - 1).dropna()
    r = r[r.index.dayofweek < 5]
    vol = r.rolling(20).std().shift(1)
    # last US day strictly before the local date
    idx = usz.index.searchsorted(r.index, side="left") - 1
    z = pd.Series(np.where(idx >= 0, usz.to_numpy()[np.clip(idx, 0, None)], np.nan), index=r.index)
    pos = sign * np.sign(z) * (z.abs() >= thr)
    size = (0.01 / vol).clip(upper=4)
    out = (pos * r - pos.abs() * cost * bp * 1e-4) * size
    out[pos == 0] = 0.0
    return holdout.drop(out.dropna())


if __name__ == "__main__":
    res, strs, mk = {}, {}, {}
    for s in MK:
        for m in (1.0, 1.5, 2.0):
            x = leg(s, m)
            rep(f"{s} {m}x", x)
            if m == 1.0:
                res[s] = x
            if m == 1.5:
                strs[s] = x
        rep(f"{s} no cost thr0", leg(s, 0.0, 0.0))
        rep(f"{s} same-sign (control)", leg(s, 1.0, 0.25, +1))
        mk[s] = res[s]
    cand = (res["JPXJPY"] + res["GRXEUR"]) / 2
    cs = (strs["JPXJPY"] + strs["GRXEUR"]) / 2
    rep("JPN+GER 1x", cand)
    rep("JPN+GER 1.5x", cs)
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        cand.rename("r").rename_axis("day").to_csv(root / "candidates" / "iwanaga_usrev.csv")
        cs.rename("r").rename_axis("day").to_csv(root / "candidates" / "iwanaga_usrev_stress.csv")
        pd.DataFrame(mk).rename_axis("day").to_csv(root / "candidates" / "iwanaga_usrev_markets.csv")
