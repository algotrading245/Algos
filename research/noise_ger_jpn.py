"""Noise-area rule (Zarattini, Aziz, Barbon) on GER40 and JPN225 with the paper's parameters (VM 1, 14 days, 30 min),
no tuning.  Costs per round trip: DAX 1.0 bp, Nikkei 2.0 bp (FTMO-type CFD spreads), stress 1.5x.  Candidate "noise_gj"
= half DAX + half Nikkei; markets file shows the same rule on four indices.
    python research/noise_ger_jpn.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import holdout
from noise_area_index import run, sharpe

SPLIT = pd.Timestamp("2018-01-01")
COST = {"GRXEUR": 1.0, "JPXJPY": 2.0, "SPXUSD": 1.0, "NSXUSD": 0.4}
root = Path(__file__).resolve().parent.parent / "marketdata"


def clean(x):
    x = x.copy()
    x.index = pd.to_datetime(x.index).tz_localize(None).normalize()
    return holdout.drop(x)


def rep(l, x):
    print(f"{l:28s} all {sharpe(x):+.2f}  to2017 {sharpe(x[:SPLIT]):+.2f}  2018+ {sharpe(x[SPLIT:]):+.2f}  2022+ {sharpe(x['2022':]):+.2f}")


res, stress, mk = {}, {}, {}
for s, c in COST.items():
    x, _ = run(s, 1.0, c)
    y, _ = run(s, 1.0, 1.5 * c)
    res[s], stress[s] = clean(x), clean(y)
    mk[s] = res[s]
    rep(s + " 1x", res[s])
    rep(s + " 1.5x", stress[s])
    z, _ = run(s, 1.0, 2 * c)
    rep(s + " 2x", clean(z))

cand = (res["GRXEUR"] + res["JPXJPY"]) / 2
cs = (stress["GRXEUR"] + stress["JPXJPY"]) / 2
rep("GER+JPN 1x", cand["2010":])
rep("GER+JPN 1.5x", cs["2010":])
us = (res["SPXUSD"] + res["NSXUSD"]) / 2
print("corr to US noise leg", pd.concat([cand, us], axis=1).dropna().corr().iloc[0, 1])
cand["2010":].rename("r").rename_axis("day").to_csv(root / "candidates" / "noise_gj.csv")
cs["2010":].rename("r").rename_axis("day").to_csv(root / "candidates" / "noise_gj_stress.csv")
pd.DataFrame(mk)["2010":].rename_axis("day").to_csv(root / "candidates" / "noise_gj_markets.csv")
