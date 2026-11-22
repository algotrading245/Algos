"""Lunar cycle (Yuan, Zheng, Zhu 2006): returns are lower around full moon than around new moon, in 48 countries.
New-moon period = N days before + new moon day + N days after.  Rule: long the index close before the window, flat
otherwise.  N=3 (primary, 7-day window) and N=7 (15-day), 2 settings counted as trials.  Moon dates are computed
(Meeus mean new moon + main periodic terms, good to a few hours).  Markets: SPXUSD, NSXUSD, GRXEUR, JPXJPY, with XAUUSD
as control.  Costs: round trip bp per market, 1x and 1.5x, plus index carry from fomc_cycle.CARRY.

    python research/lunar_new_moon.py
"""
import numpy as np
import pandas as pd

from fomc_cycle import row, traded
from intraday_momentum import SPLIT
from turn_of_month import frame
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import holdout

MARKETS = {"SPXUSD": 1.0, "NSXUSD": 1.5, "GRXEUR": 1.5, "JPXJPY": 2.0}
CONTROL = {"XAUUSD": 2.0}
OUT = Path(__file__).resolve().parents[1] / "marketdata" / "candidates"


def new_moons(y0=2009, y1=2027):
    """Dates (UTC date) of new moons, Meeus ch. 49 with the main terms."""
    out = []
    for k in np.arange(int((y0 - 2000) * 12.3685) - 2, int((y1 - 2000) * 12.3685) + 2):
        T = k / 1236.85
        jde = 2451550.09766 + 29.530588861 * k + 0.00015437 * T ** 2
        M = np.radians(2.5534 + 29.10535670 * k)
        Mp = np.radians(201.5643 + 385.81693528 * k)
        F = np.radians(160.7108 + 390.67050284 * k)
        Om = np.radians(124.7746 - 1.56375588 * k)
        jde += (-0.40720 * np.sin(Mp) + 0.17241 * np.sin(M) + 0.01608 * np.sin(2 * Mp) + 0.01039 * np.sin(2 * F)
                + 0.00739 * np.sin(Mp - M) - 0.00514 * np.sin(Mp + M) + 0.00208 * np.sin(2 * M)
                - 0.00111 * np.sin(Mp - 2 * F) - 0.00057 * np.sin(Mp + 2 * F) + 0.00056 * np.sin(2 * Mp + M)
                - 0.00042 * np.sin(3 * Mp) + 0.00042 * np.sin(M + 2 * F) + 0.00038 * np.sin(M - 2 * F)
                - 0.00024 * np.sin(2 * Mp - M) - 0.00017 * np.sin(Om))
        out.append(pd.Timestamp("2000-01-01 12:00") + pd.Timedelta(days=jde - 2451545.0))
    return pd.DatetimeIndex(out).normalize()


def window(index, centres, n):
    """True on the trading days whose calendar date lies within n days of a centre date."""
    d = index.values.astype("datetime64[D]").astype(np.int64)
    c = centres.values.astype("datetime64[D]").astype(np.int64)
    pos = np.searchsorted(c, d)
    near = np.full(len(d), 99)
    for off in (-1, 0):
        j = np.clip(pos + off, 0, len(c) - 1)
        near = np.minimum(near, np.abs(d - c[j]))
    return pd.Series(near <= n, index=index)


def run(symbol, cost, n, new, full, mult=1.0):
    r = frame(symbol)
    r = holdout.drop(r)
    return r, traded(r, window(r.index, new, n), cost * mult)


if __name__ == "__main__":
    nm = new_moons()
    fm = nm + pd.Timedelta(days=14.765)
    fm = fm.normalize()
    print("check new moons 2024:", [str(x.date()) for x in nm[(nm.year == 2024)][:4]], "(real: 01-11, 02-09, 03-10, 04-08)")
    for n in (3, 7):
        print(f"\n######## N={n}")
        res, stress, mk = {}, {}, {}
        for s, c in {**MARKETS, **CONTROL}.items():
            r, x = run(s, c, n, nm, fm)
            _, xs = run(s, c, n, nm, fm, 1.5)
            _, x2 = run(s, c, n, nm, fm, 2.0)
            _, xf = run(s, c, n, fm, fm)
            print(f"  {s}  {r.index[0].date()} to {r.index[-1].date()}")
            row("new-moon window 1x", x)
            row("new-moon window 1.5x", xs)
            row("new-moon window 2x", x2)
            row("full-moon window (compare)", xf)
            row("every day", traded(r, r["r"].notna(), c))
            if s in MARKETS:
                res[s], stress[s], mk[s] = x, xs, x
        d = pd.DataFrame(res).fillna(0)
        ds = pd.DataFrame(stress).fillna(0)
        print("  equal-weight 4 indices")
        row("1x", d.mean(axis=1))
        row("1.5x", ds.mean(axis=1))
        if n == 3:
            out = d.mean(axis=1)
            out.index.name = "day"
            out.rename("r").to_csv(OUT / "paper_lunar_new_moon_indices.csv")
            ds.mean(axis=1).rename("r").rename_axis("day").to_csv(OUT / "paper_lunar_new_moon_indices_stress.csv")
            d.rename_axis("day").to_csv(OUT / "paper_lunar_new_moon_indices_markets.csv")
