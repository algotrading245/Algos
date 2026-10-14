"""Pre-announcement returns and heightened uncertainty (Hu, Pan, Wang, Zhu, "Premium for heightened uncertainty:
Explaining pre-announcement market returns", NBER WP 25817 / Journal of Financial Economics 2022).

E-mini S&P 500 futures, September 1994 to May 2018.  The pre-announcement window runs from the previous 16:00
close to five minutes before the release (8:25 for payrolls and GDP, 9:55 for ISM manufacturing); days that are
also FOMC days are left out; all three GDP estimates count.  Table 1: FOMC 27.1 bp (t 6.0), payrolls 10.1 (3.6),
ISM 9.1 (2.1), GDP 7.5 (2.1), seven other indicators nothing; other days close to open 0.7 bp.  Table 2: the three
together 9.5 bp over the sample and 7.0 bp (t 2.3) in 2012-2018, 36 events a year.  Table 6: when the VIX rose
most over the six days before (VIX(t-1) - VIX(t-7) in its top fifth) the return is 17 bp against 7 bp; Table 7:
3.5 bp per VIX point.  Table 10, "heightened VIX days": after a close with VIX - EWMA(VIX, eta) >= 2.5-3 points
the S&P earns 35-57 bp close to close the next day (8-11 days a year); Table 11: the six-day build-up predicts the
next day's return on those days (6.7 bp a point) and on announcement days (5.4), not on normal days (0.3).

Here: the same windows on the S&P 500 CFD (bid minute bars), the VIX from daily closes.  Payrolls dates from the
ALFRED release calendar, GDP from ALFRED and the BEA schedule, ISM as the first business day of the month.

    python research/pre_announcement_drift.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  Pre-announcement: to 2017 the three earn 8.7 bp an event (t 2.3; NFP 7.8, GDP 8.4, ISM 7.9) against 1.7 bp on
           other nights, as the paper's 7.0 for 2012-2018.  From 2018 it is 2.9 bp (t 0.7) against 4.2 bp on
           other nights - no premium left; NFP -0.5, GDP 1.3, only ISM 8.6 (t 1.2).  Starting at 15:30 gives the
           same, starting at 19:00 (after the rollover) 7.1 bp then -0.9 bp.
  VIX build-up: to 2017 the top fifth earns 16.0 bp against 7.1, the paper's Table 6 to the decimal; from 2018
           -0.9 against 4.0.  Slope 2.3 bp a point (t 1.8) then 0.6 (t 0.6).
  Heightened VIX days: 13-24 bp the next day at cutoffs 2.5-3, a third of the paper's 35-57, and no t above 1.5
           in either half; the mean moves by 20 bp with eta.  The build-up cannot be tested inside them (it is
           positive on 198 of 212).  On normal days the top fifth of the build-up earned 19 bp to 2017, -0.1 since.
  Traded after 1 bp and carry: the three events Sharpe 0.72 to 2017 and 0.06 from 2018; with a positive build-up
           0.83 and 0.10; heightened VIX days 0.2-0.35.  Holding every night to 8:25 does better (0.49, both
           halves).  The effect ended with the paper's sample, as the pre-FOMC drift did.  Not tried as a Hydra leg.
"""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessMonthBegin

from fomc_cycle import CARRY, EXTRA
from intraday_momentum import SPLIT, at, minutes
from overnight_intraday_reversal import NY, matrix, stats
from pre_fomc_drift import FOMC, dates

SYMBOL, COST = "SPXUSD", 1.0
VIX = "marketdata/vixidx/^VIX.csv"
NFP = {2010: "1105 1203",
       2011: "0107 0204 0304 0401 0506 0603 0708 0805 0902 1007 1104 1202",
       2012: "0106 0203 0309 0406 0504 0601 0706 0803 0907 1005 1102 1207",
       2013: "0104 0201 0308 0405 0503 0607 0705 0802 0906 1022 1108 1206",
       2014: "0110 0207 0307 0404 0502 0606 0703 0801 0905 1003 1107 1205",
       2015: "0109 0206 0306 0403 0508 0605 0702 0807 0904 1002 1106 1204",
       2016: "0108 0205 0304 0401 0506 0603 0708 0805 0902 1007 1104 1202",
       2017: "0106 0203 0310 0407 0505 0602 0707 0804 0901 1006 1103 1208",
       2018: "0105 0202 0309 0406 0504 0601 0706 0803 0907 1005 1102 1207",
       2019: "0104 0201 0308 0405 0503 0607 0705 0802 0906 1004 1101 1206",
       2020: "0110 0207 0306 0403 0508 0605 0702 0807 0904 1002 1106 1204",
       2021: "0108 0205 0305 0402 0507 0604 0702 0806 0903 1008 1105 1203",
       2022: "0107 0204 0304 0401 0506 0603 0708 0805 0902 1007 1104 1202",
       2023: "0106 0203 0310 0407 0505 0602 0707 0804 0901 1006 1103 1208",
       2024: "0105 0202 0308 0405 0503 0607 0705 0802 0906 1004 1101 1206",
       2025: "0110 0207 0307 0404 0502 0606 0703 0801 0905 1120 1216",
       2026: "0109 0211 0306 0403 0508 0605 0702 0807 0904 1002"}
# advance, second and third estimates; the shutdowns of 2013, 2019 and 2025 moved or dropped some
GDP = {2010: "1123 1222",
       2011: "0128 0225 0325 0428 0526 0624 0729 0826 0929 1027 1122 1222",
       2012: "0127 0229 0329 0427 0531 0628 0727 0829 0927 1026 1129 1220",
       2013: "0130 0228 0328 0426 0530 0626 0731 0829 0926 1107 1205 1220",
       2014: "0130 0228 0327 0430 0529 0625 0730 0828 0926 1030 1125 1223",
       2015: "0130 0227 0327 0429 0529 0624 0730 0827 0925 1029 1124 1222",
       2016: "0129 0226 0325 0428 0527 0628 0729 0826 0929 1028 1129 1222",
       2017: "0127 0228 0330 0428 0526 0629 0728 0830 0928 1027 1129 1221",
       2018: "0126 0228 0328 0427 0530 0628 0727 0829 0927 1026 1128 1221",
       2019: "0228 0328 0426 0530 0627 0726 0829 0926 1030 1127 1220",
       2020: "0130 0227 0326 0429 0528 0625 0730 0827 0930 1029 1125 1222",
       2021: "0128 0225 0325 0429 0527 0624 0729 0826 0930 1028 1124 1222",
       2022: "0127 0224 0330 0428 0526 0629 0728 0825 0929 1027 1130 1222",
       2023: "0126 0223 0330 0427 0525 0629 0727 0830 0928 1026 1129 1221",
       2024: "0125 0228 0328 0425 0530 0627 0725 0829 0926 1030 1127 1219",
       2025: "0130 0227 0327 0430 0529 0626 0730 0828 0925 1223",
       2026: "0122 0220 0313 0409 0430 0528 0625 0730 0826 0930"}
ETAS, CUTS = (0.0, 0.15, 0.30), (1.5, 2.0, 2.5, 3.0, 3.5, 4.0)


def calendar(days):
    """Release minute by indicator for each day (NaN when none), FOMC days removed."""
    ism = pd.date_range(days[0], days[-1], freq=CustomBusinessMonthBegin(calendar=USFederalHolidayCalendar()))
    fomc = dates(FOMC).append(pd.DatetimeIndex(EXTRA))
    e = pd.DataFrame(index=days)
    for name, when, minute in (("NFP", dates(NFP), "08:30"), ("GDP", dates(GDP), "08:30"), ("ISM", ism, "10:00")):
        e[name] = np.where(days.isin(when) & ~days.isin(fomc), minutes(minute), np.nan)
    e["FOMC"] = days.isin(fomc)
    return e


def frame():
    """Per weekday: the pre- and post-announcement windows for both release times, the day's close-to-close
    return, and what the VIX said at the previous close."""
    days, p = matrix(SYMBOL, NY)
    lp = np.log(p.astype(float))
    eve = pd.Series(at(lp, minutes("19:00")), index=days)
    week = days.dayofweek < 5
    lp, days = lp[week], days[week]
    c = pd.Series(at(lp, minutes("16:00")), index=days)
    last = c.ffill().shift(1)
    r = pd.DataFrame({"r": c - last}, index=days)
    r["late"] = c - pd.Series(at(lp, minutes("16:15")), index=days).ffill().shift(1)
    r["nights"] = pd.Series(days, index=days).diff().dt.days.fillna(1).to_numpy()
    for m in ("08:30", "10:00"):
        k = minutes(m)
        r[f"pre {m}"] = at(lp, k - 5) - last
        r[f"pre1530 {m}"] = at(lp, k - 5) - pd.Series(at(lp, minutes("15:30")), index=days).ffill().shift(1)
        r[f"night {m}"] = at(lp, k - 5) - eve.reindex(days - pd.Timedelta(days=1)).to_numpy()
        r[f"post {m}"] = at(lp, k + 55) - at(lp, k - 5)
        r[f"rest {m}"] = c - at(lp, k + 55)
    v = pd.read_csv(VIX, index_col="date", parse_dates=True)["close"]
    build = v.shift(1) - v.shift(7)
    r["build"] = build.reindex(days)
    r["high"] = (build > build.rolling(750, min_periods=250).quantile(0.8).shift(1)).reindex(days)
    for eta in ETAS:
        r[f"jump {eta}"] = (v - v.ewm(alpha=1 - eta, adjust=False).mean().shift(1)).shift(1).reindex(days)
    return r.join(calendar(days)).iloc[1:]


def cell(x):
    x = x.dropna()
    if len(x) < 20:
        return f"   n/a           ({len(x):4d})"
    return f"{x.mean() * 1e4:6.1f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):5.2f}, {len(x):4d})"


def table(name, x):
    print(f"    {name:38s} all {cell(x)}   to 2017 {cell(x[:SPLIT])}   2018+ {cell(x[SPLIT:])}")


def row(name, x):
    x = x.dropna()
    print(f"    {name:38s} all {stats(x)}   to 2017 {stats(x[:SPLIT])}   2018+ {stats(x[SPLIT:])}"
          f"   in market {(x != 0).mean() * 100:4.1f}%")


def traded(r, x, on, cost=COST):
    """Daily series of holding the window overnight on the flagged days: round-trip cost and the nights' carry."""
    on = on.reindex(r.index).fillna(False).astype(bool)
    pay = pd.Series(r.index.year, index=r.index).map(CARRY) / 100 / 360 * r["nights"]
    return ((x - pay - cost * 1e-4) * on).fillna(0.0)


def event(r, names, column):
    """The window `column` taken at each day's own release time, on days with one of `names`."""
    minute = r[list(names)].min(axis=1)
    x = pd.Series(np.nan, index=r.index)
    for m in ("08:30", "10:00"):
        x = x.where(minute != minutes(m), r[f"{column} {m}"])
    return x


if __name__ == "__main__":
    r = frame()
    macro = ("NFP", "GDP", "ISM")
    print(f"=== {SYMBOL}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {COST} bp round trip")
    print("  events a year:  " + "  ".join(
        f"{y} {int(x['NFP'].notna().sum())}/{int(x['GDP'].notna().sum())}/{int(x['ISM'].notna().sum())}"
        for y, x in r.groupby(r.index.year)))
    quiet = r[list(macro)].isna().all(axis=1) & ~r["FOMC"]
    print("  16:00 to release - 5 min (paper: NFP 10.1, ISM 9.1, GDP 7.5, all three 7.0 in 2012-2018; other days 0.7)")
    for n in macro:
        table(n, event(r, (n,), "pre"))
    pre = event(r, macro, "pre")
    table("NFP, GDP or ISM", pre)
    table("other days, to 8:25", r["pre 08:30"][quiet])
    table("other days, to 9:55", r["pre 10:00"][quiet])
    print("  other windows on the three")
    table("15:30 to release - 5", event(r, macro, "pre1530"))
    table("19:00 to release - 5", event(r, macro, "night"))
    table("other days, 19:00 to 8:25", r["night 08:30"][quiet])
    table("release - 5 to + 55", event(r, macro, "post"))
    table("release + 55 to 16:00", event(r, macro, "rest"))
    table("close to close", r["r"][pre.notna()])
    table("other days, close to close", r["r"][quiet])
    print("  by year, bp an event:  " + "  ".join(
        f"{y} {x.mean() * 1e4:5.1f}" for y, x in pre.dropna().groupby(pre.dropna().index.year)))
    print("  VIX(t-1) - VIX(t-7) in its top fifth (paper: 17.0 against 7.1; 3.5 bp a point)")
    table("high build-up", pre[r["high"] == True])
    table("other", pre[r["high"] == False])
    table("build-up > 0", pre[r["build"] > 0])
    table("build-up <= 0", pre[r["build"] <= 0])
    for name, x in (("all", r), ("to 2017", r[:SPLIT]), ("2018+", r[SPLIT:])):
        d = pd.DataFrame({"y": pre, "x": x["build"]}).reindex(x.index).dropna()
        b = np.polyfit(d["x"], d["y"], 1)[0]
        se = (d["y"] - np.polyval(np.polyfit(d["x"], d["y"], 1), d["x"])).std() / d["x"].std() / np.sqrt(len(d))
        print(f"    slope, {name:8s} {b * 1e4:5.2f} bp a point (t {b / se:5.2f}, {len(d)})")
    print("  heightened VIX days: close to close after VIX - EWMA >= cutoff (paper, eta 0.3: 2.5 35 bp, 3.0 57 bp)")
    for eta in ETAS:
        for cut in CUTS:
            on = r[f"jump {eta}"] >= cut
            table(f"eta {eta:4.2f} cutoff {cut:3.1f} ({on.sum() / len(r) * 252:4.1f} a year)", r["r"][on])
    on = r["jump 0.3"] >= 2.5
    table("eta 0.30 cutoff 2.5, from 16:15", r["late"][on])
    table("... and build-up > 0", r["late"][on & (r["build"] > 0)])
    table("... and build-up <= 0", r["late"][on & (r["build"] <= 0)])
    table("normal days, build-up in top fifth", r["r"][quiet & ~on & (r["high"] == True)])
    table("normal days, other", r["r"][quiet & ~on & (r["high"] == False)])
    print(f"  traded long, after {COST} bp a round trip and carry")
    row("every night to 8:25", traded(r, r["pre 08:30"], r["pre 08:30"].notna()))
    row("NFP, GDP or ISM", traded(r, pre, pre.notna()))
    row("NFP only", traded(r, pre, r["NFP"].notna()))
    row("the three, high build-up", traded(r, pre, pre.notna() & (r["high"] == True)))
    row("the three, build-up > 0", traded(r, pre, pre.notna() & (r["build"] > 0)))
    for eta, cut in ((0.0, 2.5), (0.3, 2.5), (0.3, 3.0), (0.3, 2.0)):
        row(f"heightened VIX {eta}/{cut}, from 16:15", traded(r, r["late"], r[f"jump {eta}"] >= cut))
