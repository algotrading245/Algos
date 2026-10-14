"""Bitcoin intraday time-series momentum (Shen, Urquhart, Wang, Financial Review 57(2), 2022).

BTC/USD on five exchanges, one-minute bars, 2013-2020, day closing at 17:00 New York.  r_ONFH is the return from
the previous close to half an hour after the open (about 9:30), r_SLH the half hour 16:00-16:30 and r_LH the last
half hour 16:30-17:00.  Table 3: r_LH on r_ONFH 0.968 (t 4.38), R2 1.44%; on r_SLH -9.78 (t -10.2), R2 1.98%.
Table 4: the r_ONFH slope is 2.0 on days of high first-half-hour volume or volatility and 0.4-0.8 on low ones.
Table 7: 1.95 (t 5.1) after a positive r_ONFH, 0.05 after a negative one.  Table 10: the overnight part carries
it.  Table 5, timing the last half hour: sign of r_ONFH Sharpe 0.65, against the sign of r_SLH 1.72, both
agreeing 1.72; by year the first is 0.14 and -0.02 in 2017-18 and the second 0.04 in 2020.  Table 8: break-even
cost 3, 7 and 10 bp a trade over the sample and 2, 1 and 3 bp in 2020.  Table 12, 9:30-16:00 day: slope 0.37.

Here: Binance BTCUSDT and ETHUSDT hourly bars, so the half hours become hours - r_ONFH the previous 17:00 to
10:00 New York, r_SLH 15:00-16:00, r_LH 16:00-17:00.  Every day of the week; 2017-08 to 2020 overlaps the paper.

    python research/bitcoin_intraday_momentum.py

Result on Binance hourly bars (2017-08 to 2026-10), not added to any EA:
  Momentum: not there.  BTC last hour on r_ONFH 0.002 (t 0.4) over the sample; 0.016 (t 2.1) to 2020 and -0.015
           (t -2.5) from 2021, the sign turned.  Held by the sign of r_ONFH before costs: Sharpe -0.51 (-0.18 to
           2020, -0.80 from 2021), -2.0 bp a trade, negative in 2019, 2021 and 2023-2026.  The paper's stronger
           cases do no better: long only -0.36, high first-hour volume -0.39, high range -0.39.  ETH -0.74.
  Reversal of the hour before: BTC slope -0.054 (t -3.2), 2.0 bp a trade before costs (3.7 to 2020, 1.1 from
           2021), Sharpe 0.51; nothing left after 2 bp (0.00) and -0.75 after 5 bp.  ETH has the other sign from
           2021 (0.078, t 3.4).  Both agreeing: 0.40 to 2020, -0.33 from 2021.
  16:00 close: against the 15:00 hour 8.0 bp a trade and Sharpe 1.69 to 2020, -1.4 bp and -0.40 from 2021.
  The paper's own break-even of 1-3 bp in 2020 was the end of it.  Not tried as a Hydra leg.
"""
import numpy as np
import pandas as pd

from intraday_momentum import DATA

CRYPTO = DATA.parent / "crypto"
MARKETS = ("BTCUSDT", "ETHUSDT")
PAPER = "2021-01-01"                       # the paper's sample ends 2020-12-31
COSTS = (0.0, 2.0, 5.0, 10.0)
CLOSES = {"17:00 close": (10, 15, 16, 17), "16:00 close": (10, 14, 15, 16)}


def frame(symbol, first=10, sl=15, lh=16, close=17):
    """Per New York day: on (previous close to 9:00), fh (9:00 to `first`), onfh (their sum), slh (`sl` to `lh`),
    lh (`lh` to `close`), mid (`first` to `sl`), and the volume and high-low range of the 9:00-`first` hour
    against their 30-day medians."""
    d = pd.read_csv(CRYPTO / f"{symbol}_H1.csv.gz")
    t = pd.to_datetime(d["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    d["day"], d["hour"] = t.dt.tz_localize(None).dt.normalize().values, t.dt.hour.values
    d = d.drop_duplicates(["day", "hour"])
    c = np.log(d.pivot(index="day", columns="hour", values="close"))
    px = lambda h: c[h - 1]                 # the bar opening at h-1 closes at h
    r = pd.DataFrame({"on": px(9) - px(close).shift(1), "fh": px(first) - px(9), "slh": px(lh) - px(sl),
                      "lh": px(close) - px(lh), "mid": px(sl) - px(first)})
    r["onfh"] = r["on"] + r["fh"]
    hour = d[d["hour"] == first - 1].set_index("day")
    for name, x in (("volume", hour["volume"]), ("range", np.log(hour["high"] / hour["low"]))):
        r[name] = np.log(x / x.rolling(30, min_periods=15).median().shift(1)).replace([np.inf, -np.inf], np.nan)
    return r.dropna(subset=["onfh", "slh", "lh"])


def slope(d, names):
    """Least squares of lh on `names` with an intercept: coefficient (t) per predictor and R2 in %."""
    d = d[["lh", *names]].dropna()
    a = np.column_stack([np.ones(len(d)), d[list(names)]])
    y = d["lh"].to_numpy()
    b = np.linalg.lstsq(a, y, rcond=None)[0]
    e = y - a @ b
    se = np.sqrt(e @ e / (len(d) - a.shape[1]) * np.diag(np.linalg.inv(a.T @ a)))
    r2 = 1 - e @ e / ((y - y.mean()) @ (y - y.mean()))
    return "  ".join(f"{n} {c:7.3f} ({c / s:5.2f})" for n, c, s in zip(names, b[1:], se[1:])) + f"  R2 {r2 * 100:5.2f}%"


def stats(x, per=365):
    x = x.dropna()
    return "   n/a" if len(x) < 30 or x.std() == 0 else f"{x.mean() / x.std() * np.sqrt(per):6.2f}"


def row(name, x):
    """Sharpe of a daily series (flat days are zeros) and the mean per trade, by period."""
    x = x.dropna()
    a, b = x[:PAPER].iloc[:-1], x[PAPER:]
    bp = lambda y: y[y != 0].mean() * 1e4
    print(f"    {name:34s} all {stats(x)}   to 2020 {stats(a)}   2021+ {stats(b)}   per trade {bp(x):5.2f} / "
          f"{bp(a):5.2f} / {bp(b):5.2f} bp   trades {(x != 0).sum():4d}   win {(x[x != 0] > 0).mean() * 100:4.1f}%")


def timed(r, side, cost):
    """Last-hour return held in the direction `side` (+1, -1 or 0), after the round-trip cost."""
    return side * r["lh"] - np.abs(side) * cost * 1e-4


def rules(r):
    mom, rev = np.sign(r["onfh"]), -np.sign(r["slh"])
    hi = lambda n: (r[n] > r[n].rolling(365, min_periods=120).quantile(2 / 3).shift(1)).astype(float)
    return {"always long": pd.Series(1.0, index=r.index), "sign of r_ONFH": mom, "sign of r_ON": np.sign(r["on"]),
            "against r_SLH": rev, "both agree": mom.where(mom == rev, 0.0),
            "r_ONFH, long only": mom.clip(lower=0), "r_ONFH, high volume": mom * hi("volume"),
            "r_ONFH, high range": mom * hi("range"), "r_ONFH long, high volume": mom.clip(lower=0) * hi("volume"),
            "r_ONFH long, high range": mom.clip(lower=0) * hi("range"),
            "against r_SLH, high range": rev * hi("range"), "r_ONFH, weekdays": mom * (r.index.dayofweek < 5),
            "against r_SLH, weekdays": rev * (r.index.dayofweek < 5)}


if __name__ == "__main__":
    for s in MARKETS:
        for label, hours in CLOSES.items():
            r = frame(s, *hours)
            print(f"\n=== {s}, {label}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days")
            if label != "17:00 close" and s != "BTCUSDT":
                continue
            print("  last hour on what came before, coefficient (t)   paper: r_ONFH 0.97 (4.4), r_SLH -9.8 (-10.2)")
            for name, x in (("all", r), ("to 2020", r[:PAPER]), ("2021+", r[PAPER:])):
                for names in (("onfh",), ("slh",), ("onfh", "slh"), ("on", "fh", "slh"), ("mid",)):
                    print(f"    {name:8s} {slope(x * 100, names)}")
                print(f"    {name:8s} after a rise  {slope(x[x['onfh'] > 0] * 100, ('onfh', 'slh'))}")
                print(f"    {name:8s} after a fall  {slope(x[x['onfh'] < 0] * 100, ('onfh', 'slh'))}")
            for c in COSTS if label == "17:00 close" else COSTS[:2]:
                print(f"  timing the last hour, after {c} bp round trip   paper before costs: 0.65, 1.72, 1.72")
                for name, side in rules(r).items():
                    row(name, timed(r, side, c))
            if label != "17:00 close":
                continue
            print("  Sharpe by year, before costs:  r_ONFH | against r_SLH | both agree")
            k = rules(r)
            for y, x in r.groupby(r.index.year):
                print(f"    {y}   " + "   ".join(stats(timed(x, k[n].loc[x.index], 0.0))
                                                 for n in ("sign of r_ONFH", "against r_SLH", "both agree")))
