"""Market intraday momentum (Baltussen, Da, Lammers, Martens 2021, JFE 142).

The return from the previous close until half an hour before today's close
(r_ROD) predicts the last half hour (r_LH).  The paper reports no costs, so
everything here is shown against a round-trip cost in basis points.

    python research/intraday_momentum.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: beta 4.2 (t 3.0), R2 2.2% up to 2017, as in the paper; -1.4 (t -0.9) from 2018. Sign rule loses after
           any cost from 2018.
  DAX:     sign rule on the largest 30% of moves earns Sharpe 0.9 at 1 bp in both halves, but as a Hydra leg (stop,
           size by average move) only 0.54 (0.39 from 2018), flat since 2023, and the combined Sharpe does not move.
  Nikkei, gold, crude: nothing after costs. Silver: 0.8-1.0 before costs, gone at the 2 bp+ a silver CFD costs.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
SPLIT = "2018-01-01"

# symbol: (exchange time zone, open, close) on the exchange's own clock
MARKETS = {
    "SPXUSD": ("America/New_York", "09:30", "16:00"),
    "GRXEUR": ("Europe/Berlin", "09:00", "17:30"),
    "JPXJPY": ("Asia/Tokyo", "09:00", "15:00"),
    "XAUUSD": ("America/New_York", "08:20", "13:30"),
    "XAGUSD": ("America/New_York", "08:25", "13:25"),
    "WTIUSD": ("America/New_York", "09:00", "14:30"),
}


def minutes(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def matrix(symbol, zone):
    """Days x minutes of closes on the exchange clock; column m is the price at m."""
    cache = DATA / f"IMOM_{symbol}.npz"
    if cache.exists():
        z = np.load(cache)
        return pd.DatetimeIndex(z["days"]), z["p"]
    m = pd.read_csv(DATA / f"{symbol}_M1.csv.gz", usecols=["time", "close"])
    # server clock is New York + 7h; bar time is the bar's open, so +60s is its close
    t = pd.to_datetime(m["time"] + 60 - 7 * 3600, unit="s")
    t = t.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    t = t.dt.tz_convert(zone).dt.tz_localize(None)
    ok = t.notna().to_numpy()
    t, c = t[ok], m["close"].to_numpy()[ok]
    day = t.dt.normalize()
    days = pd.DatetimeIndex(np.unique(day))
    row = days.get_indexer(day)
    col = (t.dt.hour * 60 + t.dt.minute).to_numpy()
    p = np.full((len(days), 1440), np.nan)
    p[row, col] = c
    np.savez_compressed(cache, days=days.values, p=p)
    return days, p


def at(p, minute, stale=5):
    """Price at a minute, looking back at most `stale` minutes for a quote."""
    out = np.full(len(p), np.nan)
    for k in range(stale + 1):
        x = p[:, minute - k]
        out = np.where(np.isnan(out), x, out)
    return out


def table(symbol, last=30):
    zone, o, c = MARKETS[symbol]
    days, p = matrix(symbol, zone)
    o, c = minutes(o), minutes(c)
    d = pd.DataFrame({"open": at(p, o), "first": at(p, o + 30), "mid": at(p, c - 60),
                      "sig": at(p, c - last), "close": at(p, c)}, index=days)
    d = d[d.index.dayofweek < 5].dropna()
    md = d.index.month * 100 + d.index.day
    # US half days: 3 July, the Friday after Thanksgiving, Christmas Eve
    half = (md == 703) | (md == 1224) | ((d.index.month == 11) & (d.index.dayofweek == 4)
                                         & (d.index.day >= 23) & (d.index.day <= 29))
    if zone == "America/New_York":
        d = d[~half]
    prev = d["close"].shift(1)
    gap = d.index.to_series().diff().dt.days
    r = pd.DataFrame({
        "rod": d["sig"] / prev - 1,
        "onfh": d["first"] / prev - 1,
        "m": d["mid"] / d["first"] - 1,
        "slh": d["sig"] / d["mid"] - 1,
        "lh": d["close"] / d["sig"] - 1,
    })
    r = r[(gap <= 5) & (r["lh"] != 0)].dropna()
    return r


def ols(y, x):
    x = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.lstsq(x, y, rcond=None)[0]
    e = y - x @ b
    xi = np.linalg.inv(x.T @ x)
    v = xi @ (x.T * e ** 2) @ x @ xi          # White standard errors
    return b[1], b[1] / np.sqrt(v[1, 1]), 1 - e.var() / y.var()


def stats(x):
    if len(x) < 30 or x.std() == 0:
        return "      n/a"
    return f"{x.mean() * 252 * 1e2:6.2f}%/yr sh {x.mean() / x.std() * np.sqrt(252):5.2f}"


def rules(r):
    big = r["rod"].abs() > r["rod"].abs().rolling(250, min_periods=60).quantile(0.7).shift(1)
    return {
        "sign(rod)": np.sign(r["rod"]),
        "onfh & rod agree": np.sign(r["rod"]) * (np.sign(r["rod"]) == np.sign(r["onfh"])),
        "big |rod| (top 30%)": np.sign(r["rod"]) * big,
        "sign(slh)": np.sign(r["slh"]),
        "rod & slh agree": np.sign(r["rod"]) * (np.sign(r["rod"]) == np.sign(r["slh"])),
        "big & slh agree": np.sign(r["rod"]) * big * (np.sign(r["rod"]) == np.sign(r["slh"])),
    }


def study(symbol, last=30, costs=(0.0, 0.5, 1.0, 2.0)):
    r = table(symbol, last)
    print(f"\n=== {symbol}  last {last} min  {r.index[0].date()} to {r.index[-1].date()}"
          f"  {len(r)} days  |lh| mean {r['lh'].abs().mean() * 1e4:.1f} bp")
    for name, part in (("all", r), ("to 2017", r[:SPLIT]), ("2018+", r[SPLIT:])):
        b, t, r2 = ols(part["lh"].to_numpy(), part["rod"].to_numpy())
        bs, ts, _ = ols(part["lh"].to_numpy(), part["slh"].to_numpy())
        print(f"  {name:8s} beta_rod {b * 100:6.2f} (t {t:5.2f}) R2 {r2 * 100:5.2f}%"
              f"   beta_slh {bs * 100:6.2f} (t {ts:5.2f})")
    for name, pos in rules(r).items():
        pos = pos.fillna(0.0)
        traded = pos != 0
        print(f"  {name:20s} trades {traded.mean() * 100:3.0f}%  win "
              f"{(pos * r['lh'] > 0)[traded].mean() * 100:4.1f}%  gross/trade "
              f"{(pos * r['lh'])[traded].mean() * 1e4:5.2f} bp")
        for cost in costs:
            x = pos * r["lh"] - traded * cost * 1e-4
            print(f"      cost {cost:3.1f} bp  all {stats(x)}   to 2017 {stats(x[:SPLIT])}"
                  f"   2018+ {stats(x[SPLIT:])}")
    return r


if __name__ == "__main__":
    for s in MARKETS:
        if (DATA / f"{s}_M1.csv.gz").exists():
            study(s)
    study("SPXUSD", last=15)
