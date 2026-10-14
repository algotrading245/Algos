"""Crude oil intraday momentum around the EIA inventory report (Wen, Indriawan, Lien, Xu 2023, Energy Journal 44(5)).

On Wednesdays with the 10:30 New York release the paper finds that the third half hour (10:30-11:00) predicts the
last half hour of the USO session (15:30-16:00), only when volatility is high and mostly in the first half of the
month; on other days the return from the previous close to 10:00 (its overnight part) predicts it.  The paper
reports no costs.  Here: WTI CFD minute bars, the paper's clock and the futures clock (settlement 14:28-14:30), the
sign rule of the paper's Table 6, costs in basis points per round trip.

    python research/oil_eia_intraday.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  The paper's clock (15:30-16:00): beta of r3 on EIA days 0.002 (t 0.1) to 2017 and -0.096 (t -1.9) from 2018; the
  sign rule loses before costs (-1.6 bp a trade), and more so under high OVX or in the first half of the month.
  The futures clock (14:00-14:30): 1.7 bp a trade before costs, Sharpe 0.16 (-0.07 to 2017), nothing at 3 bp.
  Other days, overnight or first half hour: under 0.3 bp a trade before costs.  Holding from 11:00 to 14:30 on EIA
  days earns 10 bp a trade, Sharpe 0.3 at 3 bp (0.5 to 2017, 0.1 from 2018): too weak for a leg.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

import intraday_momentum as M

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
SPLIT = M.SPLIT


def table(close="16:00"):
    days, p = M.matrix("WTIUSD", "America/New_York")
    c = M.minutes(close)
    g = lambda text: M.at(p, M.minutes(text))
    d = pd.DataFrame({"o": g("09:30"), "a": g("10:00"), "e0": g("10:30"), "e15": g("10:45"), "e30": g("11:00"),
                      "sig": M.at(p, c - 30), "close": M.at(p, c), "ref": g("16:00")}, index=days)
    d = d[d.index.dayofweek < 5].dropna()
    prev = d["ref"].shift(1)
    r = pd.DataFrame({"r1": d["a"] / prev - 1, "night": d["o"] / prev - 1, "open": d["a"] / d["o"] - 1,
                      "r3": d["e30"] / d["e0"] - 1, "r3q": d["e15"] / d["e0"] - 1,
                      "mid": d["sig"] / d["e30"] - 1, "lh": d["close"] / d["sig"] - 1})
    r = r[(d.index.to_series().diff().dt.days <= 5) & (r["lh"] != 0)].dropna()
    # the report moves to Thursday or Friday when a federal holiday falls on Monday to Wednesday
    hol = USFederalHolidayCalendar().holidays(r.index[0], r.index[-1])
    week = lambda x: x - pd.to_timedelta(x.dayofweek, unit="D")
    moved = set(week(hol[hol.dayofweek < 3]))
    r["eia"] = (r.index.dayofweek == 2) & ~week(r.index).isin(moved)
    return r


def line(name, pos, ret, cost):
    pos = pos.reindex(ret.index).fillna(0.0)
    on = pos != 0
    x = (pos * ret - on * cost * 1e-4)[on]
    n = on.groupby(on.index.year).sum().mean()                       # trades a year
    sh = lambda y: y.mean() / y.std() * np.sqrt(n) if len(y) > 20 and y.std() > 0 else np.nan
    print(f"  {name:40s} n {on.sum():4d}  win {(x > -cost * 1e-4).mean() * 100:4.1f}%  gross "
          f"{(pos * ret)[on].mean() * 1e4:6.2f} bp   sharpe all {sh(x):5.2f}  to 2017 {sh(x[:SPLIT]):5.2f}  "
          f"2018+ {sh(x[SPLIT:]):5.2f}")


def study(close, cost):
    r = table(close)
    ovx = pd.read_csv(ROOT / "volidx" / "OVX.csv", index_col=0, parse_dates=True)["close"].shift(1)
    ovx = ovx.reindex(r.index).ffill()
    hi = ovx > ovx.rolling(500, min_periods=120).median()
    first = pd.Series(r.index.day <= 15, index=r.index)
    eia, non, mon = r["eia"], ~r["eia"], pd.Series(r.index.dayofweek == 0, index=r.index)
    print(f"\n=== last half hour to {close} New York, cost {cost} bp, {r.index[0].date()} to {r.index[-1].date()}, "
          f"{len(r)} days, {eia.sum()} EIA days, |lh| mean {r['lh'].abs().mean() * 1e4:.1f} bp")
    for name, part in (("to 2017", r[:SPLIT]), ("2018+", r[SPLIT:])):
        e = part[part["eia"]]
        b3, t3, r2 = M.ols(e["lh"].to_numpy(), e["r3"].to_numpy())
        n = part[~part["eia"]]
        b1, t1, _ = M.ols(n["lh"].to_numpy(), n["r1"].to_numpy())
        print(f"  {name:8s} EIA days: beta r3 {b3:6.3f} (t {t3:5.2f}) R2 {r2 * 100:5.2f}%    "
              f"other days: beta r1 {b1:6.3f} (t {t1:5.2f})")
    s3, s3q, s1, sn = np.sign(r["r3"]), np.sign(r["r3q"]), np.sign(r["r1"]), np.sign(r["night"])
    for name, pos in (("EIA: sign(r3)", s3 * eia), ("EIA: sign(r3 first 15 min)", s3q * eia),
                      ("EIA: sign(r3), high OVX", s3 * (eia & hi)), ("EIA: sign(r3), low OVX", s3 * (eia & ~hi)),
                      ("EIA: sign(r3), first half of month", s3 * (eia & first)),
                      ("EIA: sign(r3), second half", s3 * (eia & ~first)),
                      ("EIA: sign(r3), high OVX and first half", s3 * (eia & hi & first)),
                      ("EIA: sign(r3), held from 11:00", None),
                      ("other days: sign(r3)", s3 * non), ("other days: sign(r1)", s1 * non),
                      ("other days: sign(overnight)", sn * non),
                      ("other days: sign(overnight), high OVX", sn * (non & hi)),
                      ("Mondays: sign(r1)", s1 * mon), ("all days: long", s1 * 0 + 1)):
        if pos is None:
            line(name, s3 * eia, (1 + r["mid"]) * (1 + r["lh"]) - 1, cost)
        else:
            line(name, pos, r["lh"], cost)


if __name__ == "__main__":
    for close in ("16:00", "14:30"):
        for cost in (0.0, 3.0):
            study(close, cost)
