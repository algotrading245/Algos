"""Market return around the clock (Bondarenko, Muravyev, NFA draft March 2020 / JFQA 58(3), 2023).

E-mini S&P 500 futures, one-minute bars, 2004-2018.  Table 1: the four hours 23:30-3:30 New York ("EU-open")
earn 7.60% a year (t 6.35, Sharpe 1.67) and the other twenty -0.80%.  Table A.1: 23:30-1:30 1.70% (t 2.51),
1:30-3:30 5.90% (t 5.85), Asia before it (18:00-23:30) -1.25%.  Table 4: positive in each year 2004-2018, 2.25%
in 2017.  Table 5: Monday 4.8%, Tuesday 9.6%.  Table 7, standardised predictors of the EU-open return: VIX at
the previous close relative to its five-day average 0.13 (t 4.1), Asian volume 0.13, Asian volatility before
23:30 0.11 (t 3.0), VIX level 0.07, weekend -0.08, Asian return -0.06 (t -1.0).  Table 6, paying the spread of
1.56 bp: every night Sharpe 0.69 (1.65 before costs); the nights with the highest predicted return 1.39 (1.94).
VIX futures fall in the same hours (Table 8), which the authors read as uncertainty resolved at Europe's open.

Here: the same windows on the index CFD.  No volume, so the predictors are the previous US session's return,
the VIX level and shock, and the Asian return and realised volatility over 18:30-23:30 (after the rollover).
The predicted return comes from a regression on the nights before, refitted every night.

    python research/market_around_clock.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: to 2017 as in the paper - 2.8 bp a night (t 4.5), Sharpe 1.79 before costs (paper 1.67), nearly all
           of it in 1:30-3:30 (2.4 bp), Tuesday and Wednesday strongest.  From 2018 1.6 bp (t 2.3), Sharpe 0.77,
           and that is 2018 and 2020: 2021-2025 earn 0.4, 0.1, -2.6, -0.1 and 1.9% a year.  After 1 bp: 0.58
           (1.15 to 2017, 0.29 from 2018); after the paper's 1.56 bp 0.29 (0.79, 0.02).
  The predictors hold in both halves: high Asian volatility 4.6 bp against 0.5 bp in the low tercile, high VIX
           5.7 bp against 0.0, a weak US session 3.9 bp against 1.5, a falling Asian evening 3.4 bp.  The VIX
           shock adds nothing once the level is in (t 0.6); Monday is lower but not significantly.
  Selected nights after 1 bp: regression on US return, VIX shock and Asian volatility, top 30%, Sharpe 0.80
           (1.75 to 2017, 0.60 from 2018); plain "VIX in its top tercile" 0.92 (1.67, 0.74); with a weak US
           session as well, 1:30-3:30 only, 1.02 (1.35, 0.95).  The paper's 1.39 is not reached after 2017.
  DAX: these hours only from 2018, 3.2 bp (t 2.0), Sharpe 0.50 after 1.5 bp.  Nikkei: 1.5 bp (t 1.6), negative
           after 2 bp.
  As a Hydra leg: correlation 0.06 with the rest; high VIX moves the combined Sharpe from 3.01 to 3.08 at 1-2x
           and lowers it from 3x; high VIX with a weak US session 3.11 at 3x (2.74 to 2017, 3.41 from 2018).
           The same gain as research/overnight_drift.py, which is the same trade.  Not enough to earn a place.
"""
import numpy as np
import pandas as pd

from intraday_momentum import DATA, SPLIT, at, minutes
from overnight_drift import row, traded
from overnight_intraday_reversal import NY, matrix

MARKETS = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0}
COSTS = (1.0, 1.56)
VIX = DATA.parent / "vixidx" / "^VIX.csv"
PREDICTORS = ("us", "shock", "vix", "avol", "asia", "weekend")


def frame(symbol):
    """Per weekday morning d: the return from 23:30 the evening before to 3:30 (`eu`), its two halves, the rest
    of the day (3:30-23:30), and what was known at 23:30 - the Asian return and realised volatility since 18:30
    (the latter against its 60-night median), the last US session's return, the VIX level and shock at the last
    close, and whether the night follows a weekend."""
    days, p = matrix(symbol, NY)
    lp = pd.DataFrame(np.log(p.astype(float)), index=days)
    px = lambda t: pd.Series(at(lp.values, minutes(t)), index=days)
    eve = lambda x: x.reindex(days - pd.Timedelta(days=1)).set_axis(days)
    start = eve(px("23:30"))
    r = pd.DataFrame({"eu": px("03:30") - start, "first": px("01:30") - start, "second": px("03:30") - px("01:30"),
                      "rest": px("23:30") - px("03:30"), "asia": start - eve(px("18:30"))})
    five = lp.ffill(axis=1, limit=5).iloc[:, minutes("18:30"):minutes("23:30") + 1:5]
    avol = eve(np.sqrt((five.diff(axis=1) ** 2).sum(axis=1, min_count=30)))
    r = r[days.dayofweek < 5]
    avol = avol[r.index]
    r["avol"] = np.log(avol / avol.rolling(60, min_periods=30).median().shift(1))
    r["us"] = (px("16:00") - px("09:30"))[r.index].ffill().shift(1)
    v = pd.read_csv(VIX, index_col="date", parse_dates=True)["close"]
    known = pd.DataFrame({"vix": np.log(v), "shock": np.log(v / v.rolling(5).mean())}).shift(1)
    r = r.join(known.reindex(r.index, method="ffill"))
    r["weekend"] = (r.index.dayofweek == 0).astype(float)
    return r


def cell(x):
    x = x.dropna()
    return f"{x.mean() * 1e4:6.2f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):5.2f})"


def table(name, x):
    print(f"    {name:34s} {cell(x)}   {cell(x[:SPLIT])}   {cell(x[SPLIT:])}   {x.mean() * 252 * 100:5.1f}% a year")


def predicted(r, names, first=500):
    """Out-of-sample forecast of `eu`: least squares on all earlier nights, predictors standardised on them."""
    d = r[["eu", *names]].dropna()
    y, x = d["eu"].to_numpy(), d[list(names)].to_numpy()
    out = np.full(len(d), np.nan)
    for i in range(first, len(d)):
        m, s = x[:i].mean(axis=0), x[:i].std(axis=0)
        a = np.column_stack([np.ones(i), (x[:i] - m) / s])
        b = np.linalg.lstsq(a, y[:i], rcond=None)[0]
        out[i] = b[0] + ((x[i] - m) / s) @ b[1:]
    return pd.Series(out, index=d.index)


def top(f, share):
    """Nights whose forecast is in the top `share` of the forecasts made before."""
    return f > f.expanding(250).quantile(1 - share).shift(1)


def coefficients(r, names):
    d = r[["eu", *names]].dropna()
    x = (d[list(names)] - d[list(names)].mean()) / d[list(names)].std()
    a = np.column_stack([np.ones(len(d)), x])
    b, res = np.linalg.lstsq(a, d["eu"].to_numpy() * 100, rcond=None)[:2]
    se = np.sqrt(res[0] / (len(d) - a.shape[1]) * np.diag(np.linalg.inv(a.T @ a)))
    return "  ".join(f"{n} {c:6.3f} ({c / e:5.2f})" for n, c, e in zip(names, b[1:], se[1:]))


if __name__ == "__main__":
    for s, cost in MARKETS.items():
        r = frame(s)
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {cost} bp round trip")
        print("  mean a night, before costs:  all | to 2017 | 2018+      paper: 3.0, 0.7, 2.3, -0.3, -0.5 bp")
        table("EU-open 23:30-3:30", r["eu"])
        table("23:30-1:30", r["first"])
        table("1:30-3:30", r["second"])
        table("rest of the day 3:30-23:30", r["rest"])
        table("Asia 18:30-23:30", r["asia"])
        print("  every night")
        row("EU-open, before costs", r["eu"])
        row("1:30-3:30, before costs", r["second"])
        for c in sorted({cost, *COSTS}):
            row(f"EU-open after {c} bp", r["eu"] - c * 1e-4)
            row(f"1:30-3:30 after {c} bp", r["second"] - c * 1e-4)
        if s != "SPXUSD":
            continue
        print("  EU-open by year, % a year:  " + "  ".join(
            f"{y} {x.mean() * 252 * 100:4.1f}" for y, x in r["eu"].groupby(r.index.year)))
        print("  EU-open by weekday (paper: 4.8, 9.6, 8.7, 8.5, 6.0% a year)")
        for k, name in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")):
            table(name, r["eu"][r.index.dayofweek == k])
        print("  regression of the EU-open return (%) on standardised predictors, coefficient (t)")
        for name, x in (("all", r), ("to 2017", r[:SPLIT]), ("2018+", r[SPLIT:])):
            for names in (*((n,) for n in PREDICTORS), PREDICTORS):
                print(f"    {name:8s} {coefficients(x, names)}")
        print("  EU-open by tercile of what was known at 23:30 (terciles of the 750 nights before)")
        for n in PREDICTORS[:-1]:
            lo = r[n].rolling(750, min_periods=250).quantile(1 / 3).shift(1)
            hi = r[n].rolling(750, min_periods=250).quantile(2 / 3).shift(1)
            table(f"{n} low", r["eu"][r[n] < lo])
            table(f"{n} middle", r["eu"][(r[n] >= lo) & (r[n] <= hi)])
            table(f"{n} high", r["eu"][r[n] > hi])
        third = lambda n, q: r[n].rolling(750, min_periods=250).quantile(q).shift(1)
        rules = {"VIX high": r["vix"] > third("vix", 2 / 3), "US session low": r["us"] < third("us", 1 / 3),
                 "Asia low": r["asia"] < third("asia", 1 / 3), "Asian volatility high": r["avol"] > third("avol", 2 / 3)}
        rules["VIX high or US session low"] = rules["VIX high"] | rules["US session low"]
        rules["VIX high and US session low"] = rules["VIX high"] & rules["US session low"]
        rules["VIX high, Tuesday to Friday"] = rules["VIX high"] & (r.index.dayofweek > 0)
        for c in COSTS:
            print(f"  simple rules, traded as a daily series after {c} bp")
            for name, on in rules.items():
                row(name, traded(r["eu"], on, c))
                row("  1:30-3:30 only", traded(r["second"], on, c))
        sets = {"us, shock, avol": ("us", "shock", "avol"), "shock, avol": ("shock", "avol"),
                "avol": ("avol",), "shock": ("shock",), "all six": PREDICTORS}
        for c in COSTS:
            print(f"  traded as a daily series after {c} bp (paper after 1.56 bp: every night 0.69, selected 1.39)")
            for name, names in sets.items():
                f = predicted(r, names)
                live = f.notna().reindex(r.index).fillna(False)
                if name == "us, shock, avol":
                    row("every night, same sample", traded(r["eu"], live, c))
                for share in (0.5, 0.3):
                    row(f"{name}: top {share:.0%}", traded(r["eu"], top(f, share) & live, c)[live])
                    row(f"  1:30-3:30 only", traded(r["second"], top(f, share) & live, c)[live])
