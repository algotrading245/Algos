"""Overnight-intraday reversal (Della Corte, Kosowski, Wang 2015, "Market Closure and Short-Term Reversal").

CO-OC: the move from yesterday's close to today's open is faded from the open
to the close.  The paper's portfolio is cross-sectional (Lehmann weights
w_i = -(r_i - mean) on the overnight return, scaled to 50% margin) and gross of
costs; its Table 7 shows most of the profit is made in the first minute.  So
everything here is shown for several entry delays and round-trip costs.

    python research/overnight_intraday_reversal.py

Result on histdata minute bars (2009/2010 to 2026-10), not added to any EA:
  Cross-section: index Sharpe 0.2 before costs and -0.5 at 1 bp, currency 0.05, metals and oil -0.4. No dependence
           on the entry delay, so the first-minute effect of the paper's Table 7 is not in round-the-clock CFDs.
  Single markets: S&P 500, DAX, Nikkei about zero. Weekly version unstable (sign flips between the halves).
  Gold and silver do the opposite: the move since yesterday's 13:30 New York continues until today's 13:30 and
           turns back after it. Following it earns 0.5-0.6 alone in both halves at 1 bp (gold) and 5 bp (silver),
           uncorrelated with the Hydra legs, but lifts the combined Sharpe only from 3.01 to 3.08 and is gone
           at 2 bp (gold) or 8 bp (silver).
"""
import numpy as np
import pandas as pd

from intraday_momentum import DATA, SPLIT, at, minutes

NY = "America/New_York"
# group: (clock, open, close, {symbol: +1 quoted in USD / -1 USD is the base})
GROUPS = {
    # CME pit hours, as in the paper's futures sample
    "index (NY clock)": (NY, "09:30", "16:00", {"SPXUSD": 1, "GRXEUR": 1, "JPXJPY": 1}),
    "currency vs USD": (NY, "08:20", "15:00", {"AUDUSD": 1, "GBPUSD": 1, "EURUSD": 1, "NZDUSD": 1,
                                               "USDCAD": -1, "USDJPY": -1, "USDCHF": -1}),
    "metals and oil": (NY, "09:00", "13:30", {"XAUUSD": 1, "XAGUSD": 1, "WTIUSD": 1}),
}
# each market on its own exchange
OWN = {
    "SPXUSD": (NY, "09:30", "16:00"),
    "GRXEUR": ("Europe/Berlin", "09:00", "17:30"),
    "JPXJPY": ("Asia/Tokyo", "09:00", "15:00"),
    "XAUUSD": (NY, "08:20", "13:30"),
    "XAGUSD": (NY, "08:25", "13:25"),
    "WTIUSD": (NY, "09:00", "14:30"),
}
DELAYS = (0, 1, 5, 15)
COSTS = (0.0, 1.0, 2.0)


def matrix(symbol, zone):
    """Days x minutes of closes on the given clock; column m is the price at m."""
    cache = DATA / f"COOC_{symbol}_{zone.split('/')[-1]}.npz"
    if cache.exists():
        z = np.load(cache)
        return pd.DatetimeIndex(z["days"]), z["p"]
    m = pd.read_csv(DATA / f"{symbol}_M1.csv.gz", usecols=["time", "close"])
    # server clock is New York + 7h; bar time is the bar's open, so +60s is its close
    t = pd.to_datetime(m["time"] + 60 - 7 * 3600, unit="s")
    t = t.dt.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    t = t.dt.tz_convert(zone).dt.tz_localize(None)
    ok = t.notna().to_numpy()
    t, c = t[ok], m["close"].to_numpy()[ok]
    day = t.dt.normalize()
    days = pd.DatetimeIndex(np.unique(day))
    p = np.full((len(days), 1440), np.nan, dtype=np.float32)
    p[days.get_indexer(day), (t.dt.hour * 60 + t.dt.minute).to_numpy()] = c
    np.savez_compressed(cache, days=days.values, p=p)
    return days, p


def legs(symbol, zone, o, c, sign=1):
    """Overnight return and the open-to-close return for each entry delay."""
    days, p = matrix(symbol, zone)
    p = p.astype(float)
    o, c = minutes(o), minutes(c)
    d = pd.DataFrame({"open": at(p, o), "close": at(p, c)}, index=days)
    for k in DELAYS:
        d[f"in{k}"] = at(p, o + k)
    d = d[d.index.dayofweek < 5].dropna()
    gap = d.index.to_series().diff().dt.days
    r = pd.DataFrame({"co": d["open"] / d["close"].shift(1) - 1}, index=d.index)
    for k in DELAYS:
        r[f"oc{k}"] = d["close"] / d[f"in{k}"] - 1
    r = r[(gap <= 5) & (r["co"] != 0) & (r["oc0"] != 0)].dropna()
    return r * sign


def stats(x, per=252):
    x = x.dropna()
    if len(x) < 30 or x.std() == 0:
        return "   n/a"
    return f"{x.mean() / x.std() * np.sqrt(per):6.2f}"


def line(name, x, per=252):
    print(f"    {name:26s} all {stats(x, per)}   to 2017 {stats(x[:SPLIT], per)}   2018+ {stats(x[SPLIT:], per)}"
          f"   mean {x.mean() * 1e4:6.2f} bp")


def single(symbol):
    zone, o, c = OWN[symbol]
    r = legs(symbol, zone, o, c)
    big = r["co"].abs() > r["co"].abs().rolling(250, min_periods=60).quantile(0.7).shift(1)
    print(f"\n=== {symbol} own session {o}-{c}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days"
          f"  |co| {r['co'].abs().mean() * 1e4:.0f} bp  |oc| {r['oc0'].abs().mean() * 1e4:.0f} bp"
          f"  corr(co, oc) {np.corrcoef(r['co'], r['oc0'])[0, 1]:.3f}")
    out = {}
    for label, pos in (("fade every gap", -np.sign(r["co"])), ("fade big gap (top 30%)", -np.sign(r["co"]) * big)):
        print(f"  {label}")
        for k in DELAYS:
            for cost in COSTS:
                x = (pos * r[f"oc{k}"] - (pos != 0) * cost * 1e-4)
                line(f"entry +{k:2d} min, {cost:.0f} bp", x)
                out[(label, k, cost)] = x
    return out


def cross(name):
    zone, o, c, members = GROUPS[name]
    r = {s: legs(s, zone, o, c, sign) for s, sign in members.items()}
    co = pd.DataFrame({s: x["co"] for s, x in r.items()}).dropna()
    w = -co.sub(co.mean(axis=1), axis=0)
    w = w.div(w.abs().sum(axis=1) / 2, axis=0)          # one unit long, one unit short
    print(f"\n=== cross-section: {name}  {o}-{c} {zone}  {co.index[0].date()} to {co.index[-1].date()}"
          f"  {len(co)} days  {len(members)} assets")
    out = {}
    for k in DELAYS:
        oc = pd.DataFrame({s: x[f"oc{k}"] for s, x in r.items()}).reindex(co.index)
        for cost in COSTS:
            x = (w * oc).sum(axis=1) - 2 * cost * 1e-4  # both sides pay the round trip
            line(f"entry +{k:2d} min, {cost:.0f} bp", x)
            out[(k, cost)] = x
    return out


def weekly(name):
    """Friday close to Monday open is faded from Monday's open to Friday's close."""
    zone, o, c, members = GROUPS[name]
    co, oc = {}, {}
    for s, sign in members.items():
        days, p = matrix(s, zone)
        p = p.astype(float)
        d = pd.DataFrame({"open": at(p, minutes(o)), "close": at(p, minutes(c))}, index=days).dropna()
        mon, fri = d[d.index.dayofweek == 0], d[d.index.dayofweek == 4]
        prev = fri["close"].reindex(mon.index - pd.Timedelta(days=3)).to_numpy()
        nxt = fri["close"].reindex(mon.index + pd.Timedelta(days=4)).to_numpy()
        co[s] = pd.Series(sign * (mon["open"].to_numpy() / prev - 1), index=mon.index)
        oc[s] = pd.Series(sign * (nxt / mon["open"].to_numpy() - 1), index=mon.index)
    co, oc = pd.DataFrame(co).dropna(), pd.DataFrame(oc)
    oc = oc.reindex(co.index)
    ok = oc.notna().all(axis=1)
    co, oc = co[ok], oc[ok]
    w = -co.sub(co.mean(axis=1), axis=0)
    w = w.div(w.abs().sum(axis=1) / 2, axis=0)
    print(f"\n=== weekly cross-section: {name}  {len(co)} weeks")
    for cost in COSTS:
        line(f"{cost:.0f} bp", (w * oc).sum(axis=1) - 2 * cost * 1e-4, per=52)
    for s in members:
        line(f"{s} fade alone, 1 bp", -np.sign(co[s]) * oc[s] - 1e-4, per=52)


if __name__ == "__main__":
    for g in GROUPS:
        cross(g)
    for s in OWN:
        single(s)
    for g in GROUPS:
        weekly(g)
