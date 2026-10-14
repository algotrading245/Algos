"""Backtest of the AurumHydra EA: the AurumQuartet legs, the AUD/CAD fade grid, the gold hold, the month-end fix
leg, the stock-fall fix leg and the Tokyo-morning leg on one account.

Grid, on hourly closes (server hours 1 to 22) of AUDCAD: level k sits k steps from the --ma day average of
the log price, one step = --step daily volatilities (40 days of hourly returns). A level opens when the close reaches
it and closes one step back. Beyond levels + 1 steps everything is closed and the grid waits until the price is
within half a step of the average. Step and size of a cycle are fixed when its first level opens; level k has size
--mult^(k-1); results are in units of the loss of the whole grid at its stop-out.
Hold: long gold in proportion to how many of the 20, 60, 120 and 250-day returns are positive, sized to a
volatility target, less a yearly holding charge.
Fix: on the last weekday of a month five dollar pairs are traded into the London 4pm fix against the dollar when the
S&P 500 is up on the month (with it when down), and the other way round for an hour after the fix. Minute bid closes;
the S&P 500 closes come from Yahoo.
Cross: on the same day AUDJPY, CADJPY and GBPJPY are bought before the fix when the S&P 500 is up on the month and
sold when down; nothing after the fix.
Fall: on every other weekday, when the S&P 500 fell more than 3% over the five trading days to yesterday's close, the
dollar is bought on the same five pairs an hour before the fix and sold at it.
Morning: on a weekday after the S&P 500 moved 1.5% or more in a day, EURJPY, GBPJPY and CADJPY are traded against
that move (sold after a rise, bought after a fall) from an hour before the 9:55 Tokyo fixing until an hour after it.
The cross is the real AUDCAD bid series (--synthetic: AUDUSD x USDCAD instead). Spreads and the swaps of gold and
the cross are the broker's as measured in October 2026; the commission on currency pairs is still an assumption.

  python tools/backtest_hydra.py            the parts, their combination and the leverage table
  python tools/backtest_hydra.py --scan     grid variations and the martingale tests
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import quartet_model as qm

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
SPLIT = "2018-01-01"


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def hourly(symbols=("AUDUSD", "USDCAD", "XAUUSD", "AUDCAD")):
    """Last bid of each hour, weekdays, server hours 1 to 22 (the rollover hours are left out)."""
    f = DATA / "HYDRA_H1.csv.gz"
    if f.exists():
        H = pd.read_csv(f, index_col=0, parse_dates=True)
        if set(symbols) <= set(H.columns):
            return H
    cols = {}
    for s in symbols:
        m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
        m = m.sort_values("time")
        x = m.groupby(m.time // 3600).close.last()
        x.index = pd.to_datetime(x.index.to_numpy() * 3600, unit="s")
        cols[s] = x[x.index.dayofweek < 5]
        del m
    H = pd.DataFrame(cols).sort_index().loc["2009-06-01":].ffill()
    H = H[(H.index.hour >= 1) & (H.index.hour <= 22)]
    H.to_csv(f)
    return H


def grid(p, ma=5, step=1.0, levels=4, cost=1.8, mult=1.0, info=None, swap=(0.0, 0.0)):
    """Daily results of the grid on hourly closes p, in units of its loss at the stop-out. cost: bp per round trip.
    swap: bp a long and a short earn per night held (negative = pays), three nights on Wednesday."""
    wt = np.concatenate([[0.0], np.cumsum(mult ** np.arange(levels))])          # position with k levels open
    risk = sum(mult ** (k - 1) * (levels + 1 - k) for k in range(1, levels + 1))  # steps lost at the stop-out
    lp = np.log(p.to_numpy())
    avg = pd.Series(lp).rolling(ma * 22).mean().to_numpy()
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40).std() * np.sqrt(22)).shift(1).to_numpy()
    out = np.zeros(len(lp))
    q, dead, unit, fills, stops = 0, False, 1.0, 0, 0
    night = np.r_[False, p.index.normalize()[1:] != p.index.normalize()[:-1]] * np.where(p.index.dayofweek == 3, 3, 1)
    for i in range(len(lp)):
        if q:
            out[i] = np.sign(q) * wt[abs(q)] * r[i] / unit
            if night[i]:
                out[i] += wt[abs(q)] * swap[q < 0] * night[i] * 1e-4 / unit
        if np.isnan(avg[i]) or np.isnan(dv[i]) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (step * dv[i])
        az, side = abs(z), (1 if z > 0 else -1)
        if dead:
            dead = az >= 0.5
            continue
        if q == 0:
            unit = step * dv[i]
        if az >= levels + 1:
            new, dead, stops = 0, True, stops + 1
        else:
            cur = abs(q) if q * side < 0 else 0          # levels already open on this side of the average
            new = -side * max(min(int(az), levels), min(cur, int(np.ceil(az))))
        if new != q:
            out[i] -= abs(np.sign(new) * wt[abs(new)] - np.sign(q) * wt[abs(q)]) * cost * 1e-4 / 2 / unit
            fills += abs(new - q)
            q = new
    if info is not None:
        info.update(fills=fills, stops=stops)
    return pd.Series(out, index=p.index).groupby(p.index.normalize()).sum() / risk


def hold(gold, target=0.10, swap=0.04, flat=True, cost=0.8):
    """Daily results of the gold trend position: closes of server hour 22, decided at yesterday's close."""
    D = gold[gold.index.hour == 22]
    D.index = D.index.normalize()
    R = np.log(D).diff()
    vol = R.ewm(span=40).std().shift(1) * np.sqrt(252)
    sig = sum(np.sign(D / D.shift(k) - 1) for k in (20, 60, 120, 250)) / 4
    if flat:
        sig = sig.clip(lower=0)
    pos = (sig * target / vol).clip(-3, 3).shift(1)
    return pos * R - pos.diff().abs() * cost * 1e-4 / 2 - pos.clip(lower=0) * swap / 252


FIXPAIRS = {"EURUSD": 1, "GBPUSD": 1, "AUDUSD": 1, "USDCAD": -1, "USDCHF": -1}   # +1: rises when the dollar falls
FIXCROSS = {"AUDJPY": 1, "CADJPY": 1, "GBPJPY": 1}                                # bought before the fix when stocks are up
FIX_BEFORE, FIX_AFTER = 130, 185                                                # minutes kept either side of the fix


def stocks():
    """Daily closes of the S&P 500 from Yahoo, kept in SPX_D1.csv."""
    f = DATA / "SPX_D1.csv"
    if not f.exists():
        import json
        import time
        import urllib.request
        u = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=1230768000&period2={int(time.time())}&interval=1d"
        j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))
        j = j["chart"]["result"][0]
        x = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna()
        x.rename("close").rename_axis("date").to_csv(f)
    return pd.read_csv(f, index_col=0, parse_dates=True).close


def fixbars(pairs=FIXPAIRS, name="HYDRA_FIX"):
    """Minute bid closes around the London 4pm fix of every weekday: {pair: days x minutes}, and the days."""
    f = DATA / f"{name}.npz"
    if f.exists():
        z = np.load(f)
        return {s: z[s] for s in pairs}, pd.DatetimeIndex(z["days"])
    days = pd.bdate_range("2009-06-01", pd.Timestamp.now().normalize())
    at = pd.DatetimeIndex([(d + pd.Timedelta(hours=16)).tz_localize("Europe/London").tz_convert("America/New_York").tz_localize(None)
                           + pd.Timedelta(hours=7) for d in days])                # the server clock is New York + 7 hours
    T = ((at - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy()[:, None] + 60 * np.arange(-FIX_BEFORE, FIX_AFTER + 1)
    out = {}
    for s in pairs:
        m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
        m = m.sort_values("time")
        t, c = m.time.to_numpy(), m.close.to_numpy()
        del m
        i = np.maximum(np.searchsorted(t, T - 60, side="right") - 1, 0)           # the bar that closes at T
        out[s] = np.where((T - 60 - t[i] >= 0) & (T - 60 - t[i] <= 600), c[i], np.nan).astype(np.float32)
    np.savez_compressed(f, days=days.to_numpy(), **out)
    return out, days


def fix(risk=0.005, stop=3.0, cost=1.2, start=-120, turn=0, end=60, days_avg=60, parts=False, scale=0.03, cap=2.0,
        skip=0.0, pairs=FIXPAIRS, name="HYDRA_FIX", after=True):
    """Daily results of the month-end fix leg. On the last weekday of a month: from start minutes before the London
    4pm fix until it, against the dollar if the S&P 500 is up on the month so far (yesterday's close against the last
    close of the month before), with the dollar if it is down; from turn until end minutes after the fix, the
    opposite. Each pair risks `risk` of the balance at a stop `stop` average moves of that window away; cost in bp.
    With scale > 0 the risk is multiplied by the size of the stock move / scale, at most cap; months in which the
    stocks moved less than skip are left out. Other `pairs` (cached in `name`) are traded on the same days; with
    after=False only before the fix."""
    assert -FIX_BEFORE <= start < 0 <= turn < end <= FIX_AFTER
    P, days = fixbars(pairs, name)
    spx = stocks()
    ok = ~np.isnan(fixbars()[0]["EURUSD"][:, FIX_BEFORE])
    per = days.to_period("M")
    last = pd.Series(days[ok], index=per[ok]).groupby(level=0).last()
    last = last[last.index < per[-1]]                                              # the running month is not over
    mclose = spx.groupby(spx.index.to_period("M")).last()
    pre, post = pd.Series(0.0, index=days), pd.Series(0.0, index=days)
    for (a, b, flip, res) in ((start, 0, 1, pre), (turn, end, -1, post))[:2 if after else 1]:
        for s, sign in pairs.items():
            lp = np.log(P[s].astype(np.float64))
            seg = lp[:, FIX_BEFORE + a:FIX_BEFORE + b + 1]
            mv = pd.Series(np.abs(seg[:, -1] - seg[:, 0]), index=days)
            avg = mv.rolling(days_avg, min_periods=days_avg // 2).mean().shift(1)
            for p, d in last.items():
                k = days.get_loc(d)
                before = spx[:d - pd.Timedelta(days=1)]
                if p - 1 not in mclose.index or not len(before) or np.isnan(avg.iloc[k]) or np.isnan(seg[k, 0]) or np.isnan(seg[k, -1]):
                    continue
                mtd = before.iloc[-1] / mclose[p - 1] - 1
                side = flip * sign * np.sign(mtd)
                if side == 0 or abs(mtd) < skip:
                    continue
                w = min(abs(mtd) / scale, cap) if scale > 0 else 1.0
                dist = stop * avg.iloc[k]
                path = side * (seg[k] - seg[k, 0])
                r = -dist if np.nanmin(path) <= -dist else path[-1]
                res.loc[d] += w * risk * (r - cost * 1e-4) / dist
    return (pre, post) if parts else pre + post


def fall(risk=0.005, stop=3.0, cost=1.2, start=-60, drop=0.03, look=5, days_avg=60):
    """Daily results of the stock-fall fix leg. On a weekday that is not the last of its month, when the S&P 500 lost
    more than `drop` over the `look` trading days to yesterday's close: long the dollar on every pair from start
    minutes before the London 4pm fix until it. Each pair risks `risk` of the balance at a stop `stop` average moves
    of that window away; cost in bp."""
    assert -FIX_BEFORE <= start < 0
    P, days = fixbars()
    spx = stocks()
    chg = (spx / spx.shift(look) - 1).reindex(days.union(spx.index)).ffill().shift(1).reindex(days).to_numpy()
    per = days.to_period("M")
    trig = (chg < -drop) & np.r_[per[1:] == per[:-1], False]
    out = np.zeros(len(days))
    for s, sign in FIXPAIRS.items():
        lp = np.log(P[s].astype(np.float64))
        path = -sign * (lp[:, FIX_BEFORE + start:FIX_BEFORE + 1] - lp[:, [FIX_BEFORE + start]])
        move = path[:, -1]
        dist = stop * pd.Series(np.abs(move)).rolling(days_avg, min_periods=days_avg // 2).mean().shift(1).to_numpy()
        with np.errstate(invalid="ignore"):
            r = np.where(np.nanmin(np.where(np.isnan(path), np.inf, path), axis=1) <= -dist, -dist, move)
            x = risk * (r - cost * 1e-4) / dist
        out += np.where(trig & ~np.isnan(x), x, 0.0)
    return pd.Series(out, index=days)


MORNING = {"EURJPY": 1.5, "GBPJPY": 1.5, "CADJPY": 1.8}                           # round-trip cost, basis points
TOKYO_FIX = 135                                                                 # column of 9:55 Tokyo in the windows


def tokyobars(pairs=MORNING, name="HYDRA_TOKYO"):
    """Minute bid closes of the Tokyo morning, 7:40 to 13:00, of every weekday: {pair: days x minutes}, and the days."""
    f = DATA / f"{name}.npz"
    if f.exists():
        z = np.load(f)
        return {s: z[s] for s in pairs}, pd.DatetimeIndex(z["days"])
    days = pd.bdate_range("2009-06-01", pd.Timestamp.now().normalize())
    out = {}
    for s in pairs:
        m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
        t = pd.to_datetime(m.time, unit="s") - pd.Timedelta(hours=7)               # the server clock is New York + 7 hours
        t = t.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
        x = pd.Series(m.close.to_numpy(), index=pd.DatetimeIndex(t))
        del m
        x = x[x.index.notna()]
        col = x.index.hour * 60 + x.index.minute - (9 * 60 + 55) + TOKYO_FIX
        x, col = x[(col >= 0) & (col <= 320)], col[(col >= 0) & (col <= 320)]
        M = np.full((len(days), 321), np.nan, dtype=np.float32)
        k = days.get_indexer(x.index.normalize())
        M[k[k >= 0], col[k >= 0]] = x.to_numpy()[k >= 0]
        out[s] = pd.DataFrame(M).ffill(axis=1, limit=5).to_numpy(dtype=np.float32)
    np.savez_compressed(f, days=days.to_numpy(), **out)
    return out, days


def morning(risk=0.005, stop=3.0, move=0.015, start=-60, end=60, days_avg=60, stale=3, costx=1.0, pairs=MORNING):
    """Daily results of the Tokyo-morning leg. On a weekday, when the last close of the S&P 500 (not more than `stale`
    calendar days old) is `move` or more away from the close before it: against that move on every pair from start
    minutes before the 9:55 Tokyo fixing until end minutes after it. Each pair risks `risk` of the balance at a stop
    `stop` average moves of that window away; the costs are multiplied by costx."""
    P, days = tokyobars()
    spx = stocks()
    al = days.union(spx.index)
    r = (spx / spx.shift(1) - 1).reindex(al).ffill().shift(1).reindex(days).to_numpy()
    age = (days - pd.DatetimeIndex(pd.Series(spx.index, index=spx.index).reindex(al).ffill().shift(1).reindex(days))).days.to_numpy()
    trig = (np.abs(r) >= move) & (age <= stale)
    a, b = TOKYO_FIX + start, TOKYO_FIX + end
    out = np.zeros(len(days))
    for s, cost in pairs.items():
        lp = np.log(P[s].astype(np.float64))
        path = -np.sign(r)[:, None] * (lp[:, a:b + 1] - lp[:, [a]])
        dist = stop * pd.Series(np.abs(lp[:, b] - lp[:, a])).rolling(days_avg, min_periods=days_avg // 2).mean().shift(1).to_numpy()
        with np.errstate(invalid="ignore"):
            m = np.where(np.nanmin(np.where(np.isnan(path), np.inf, path), axis=1) <= -dist, -dist, path[:, -1])
            x = risk * (m - costx * cost * 1e-4) / dist
        out += np.where(trig & ~np.isnan(x), x, 0.0)
    return pd.Series(out, index=days)


AFTER = {"EURUSD": (1, 0.8), "GBPUSD": (1, 0.8), "AUDUSD": (1, 1.0), "USDCAD": (-1, 1.0), "USDCHF": (-1, 1.0),
         "NZDUSD": (1, 1.5), "USDJPY": (-1, 0.8)}                                # +1: rises when the dollar falls; cost, bp
AFTER_OPEN = 9 * 60                                                             # server minute of column 0 of the windows


def afterbars(pairs=AFTER, name="HYDRA_AFTER"):
    """Minute bid closes of the London morning, server 9:00 to 16:00, of every weekday: {pair: days x minutes}, the days."""
    f = DATA / f"{name}.npz"
    if f.exists():
        z = np.load(f)
        return {s: z[s] for s in pairs}, pd.DatetimeIndex(z["days"])
    days = pd.bdate_range("2009-06-01", pd.Timestamp.now().normalize())
    dn = days.to_numpy().astype("datetime64[D]").astype(np.int64)
    out = {}
    for s in pairs:
        m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
        t = m.time.to_numpy()
        col = (t % 86400) // 60 - AFTER_OPEN
        k = (col >= 0) & (col <= 420)
        t, col, c = t[k], col[k], m.close.to_numpy()[k]
        del m
        row = np.searchsorted(dn, t // 86400)
        ok = (row < len(dn)) & (dn[np.minimum(row, len(dn) - 1)] == t // 86400)
        M = np.full((len(days), 421), np.nan, dtype=np.float32)
        M[row[ok], col[ok]] = c[ok]
        out[s] = pd.DataFrame(M).ffill(axis=1, limit=5).to_numpy(dtype=np.float32)
    np.savez_compressed(f, days=days.to_numpy(), **out)
    return out, days


def after(risk=0.005, stop=3.0, start=5, end=360, days_avg=60, costx=1.0, pairs=("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF")):
    """Daily results of the after-holiday leg. On the first weekday after a US federal holiday (and not itself one):
    long the dollar on every pair from `start` to `end` minutes after 9:00 server time (2:00 New York). Each pair
    risks `risk` of the balance at a stop `stop` average moves of that window away; the costs are multiplied by costx."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    P, days = afterbars()
    hol = USFederalHolidayCalendar().holidays(start="2009-01-01", end=days[-1] + pd.Timedelta(days=10))
    nxt = np.searchsorted(days.to_numpy(), (hol + pd.Timedelta(days=1)).to_numpy())
    trig = np.zeros(len(days), bool)
    trig[nxt[nxt < len(days)]] = True
    trig &= ~days.isin(hol)
    out = np.zeros(len(days))
    for s in pairs:
        sign, cost = AFTER[s]
        lp = np.log(P[s].astype(np.float64))
        path = -sign * (lp[:, start:end + 1] - lp[:, [start]])
        dist = stop * pd.Series(np.abs(path[:, -1])).rolling(days_avg, min_periods=days_avg // 2).mean().shift(1).to_numpy()
        with np.errstate(invalid="ignore"):
            m = np.where(np.nanmin(np.where(np.isnan(path), np.inf, path), axis=1) <= -dist, -dist, path[:, -1])
            x = risk * (m - costx * cost * 1e-4) / dist
        out += np.where(trig & ~np.isnan(x), x, 0.0)
    return pd.Series(out, index=days)


def quartet(progression=1.0, norm=1.0):
    """Daily results of the four Quartet legs with the sizing model; progression: size x this per loss in a row,
    three at most, all divided by norm (the EA's InpLossMult and InpLossNorm)."""
    data = qm.datasets()
    W = {leg: qm.walk(d, qm.FEATS + qm.EXTRA[leg], 2014, 0.5, 0.1) for leg, d in data.items()}
    if progression != 1.0:
        for leg, d in data.items():
            lost = (d.r * d.mult).to_numpy() < 0
            k = np.zeros(len(d), int)
            for i in range(1, len(d)):
                k[i] = min(3, k[i - 1] + 1) if lost[i - 1] else 0
            W[leg] = W[leg] * progression ** k / norm
    return qm.account(data, W).sum(axis=1)


def report(x, label):
    eq = (1 + x).cumprod()
    y = (1 + x).groupby(x.index.year).prod() - 1
    print(f"  {label:15s} {100 * x.mean() * 252:5.1f}%/yr  vol {100 * x.std() * np.sqrt(252):4.1f}%  Sharpe {sharpe(x):.2f} "
          f"(to 2017 {sharpe(x[:SPLIT]):.2f}, 2018+ {sharpe(x[SPLIT:]):.2f})  max drawdown {100 * (1 - eq / eq.cummax()).max():.1f}%  "
          f"worst day {100 * x.min():+.1f}%  worst year {100 * y.min():+.0f}%")


def ruin(x, paths=20000, block=5, seed=7):
    """Resampled months and years of the daily results x at several multiples of every size."""
    rng = np.random.default_rng(seed)
    print("  size | 1 month: median, P(x10), P(-50%) | 1 year: median, P(x2), P(x10), P(below 10% of the start), P(-50% on the way)")
    for lev in (1, 2, 3, 4, 6, 8, 12, 20):
        row = []
        for days in (21, 252):
            st = rng.integers(0, len(x) - block, size=(paths, days // block + 1))
            path = np.concatenate([x[st + j][:, :, None] for j in range(block)], axis=2).reshape(paths, -1)[:, :days]
            eq = np.cumprod(np.maximum(1 + lev * path, 0.0), axis=1)
            end, low = eq[:, -1], eq.min(axis=1)
            row.append(f"{np.median(end):6.2f}x {100 * (end >= 10).mean():5.2f}% {100 * (low <= 0.5).mean():5.1f}%" if days == 21 else
                       f"{np.median(end):6.2f}x {100 * (end >= 2).mean():5.1f}% {100 * (end >= 10).mean():5.1f}% "
                       f"{100 * (low <= 0.1).mean():5.1f}% {100 * (low <= 0.5).mean():5.1f}%")
        print(f"  {lev:4d} | " + " | ".join(row))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ma", type=int, default=5, help="days in the average the grid is centred on")
    ap.add_argument("--step", type=float, default=1.0, help="distance between grid levels, daily volatilities")
    ap.add_argument("--levels", type=int, default=4)
    ap.add_argument("--mult", type=float, default=1.0, help="size of each further grid level, multiple of the one before")
    ap.add_argument("--cost", type=float, default=1.8, help="round-trip cost of the cross, basis points")
    ap.add_argument("--grid-swap", type=float, nargs=2, default=(0.42, -0.95), metavar=("LONG", "SHORT"),
                    help="what a long and a short on the cross earn per night, basis points (negative = pays)")
    ap.add_argument("--grid-risk", type=float, default=0.035, help="fraction of the balance the grid loses at its stop-out")
    ap.add_argument("--hold-vol", type=float, default=0.107, help="volatility target of the gold hold")
    ap.add_argument("--swap", type=float, default=0.068, help="yearly holding charge on long gold, fraction of the notional")
    ap.add_argument("--fix-risk", type=float, default=0.005, help="month-end fix: fraction of the balance a pair loses at its stop")
    ap.add_argument("--fix-cost", type=float, default=1.2, help="round-trip cost of a dollar pair, basis points")
    ap.add_argument("--cross-risk", type=float, default=0.005, help="month-end fix: the same for a yen cross")
    ap.add_argument("--cross-cost", type=float, default=2.0, help="round-trip cost of a yen cross, basis points")
    ap.add_argument("--fall-risk", type=float, default=0.005, help="stock-fall fix: fraction of the balance a pair loses at its stop")
    ap.add_argument("--morning-risk", type=float, default=0.005, help="Tokyo morning: fraction of the balance a pair loses at its stop")
    ap.add_argument("--after-risk", type=float, default=0.01, help="after a US holiday: fraction of the balance a pair loses at its stop")
    ap.add_argument("--loss-mult", type=float, default=0.67, help="Quartet trades: size x this for each loss in a row")
    ap.add_argument("--loss-norm", type=float, default=0.80, help="and divided by this, the average of that factor")
    ap.add_argument("--synthetic", action="store_true", help="grid on AUDUSD x USDCAD instead of the real cross")
    ap.add_argument("--scan", action="store_true", help="grid variations and martingale tests")
    a = ap.parse_args()
    H = hourly()
    aud = H.AUDUSD * H.USDCAD if a.synthetic else H.AUDCAD
    if a.scan:
        print("Grid on AUD/CAD, Sharpe 2009-2017 | 2018-2026")
        for n, s, L, c, m in ((5, 1.0, 4, 1.8, 1.0), (3, 1.0, 4, 1.8, 1.0), (8, 1.0, 4, 1.8, 1.0), (10, 1.0, 4, 1.8, 1.0),
                              (5, 0.75, 4, 1.8, 1.0), (5, 1.25, 4, 1.8, 1.0), (5, 1.0, 2, 1.8, 1.0), (5, 1.0, 3, 1.8, 1.0),
                              (5, 1.0, 6, 1.8, 1.0), (5, 1.0, 4, 3.0, 1.0), (5, 1.0, 4, 4.5, 1.0), (5, 1.0, 4, 1.8, 0.7),
                              (5, 1.0, 4, 1.8, 1.3), (5, 1.0, 4, 1.8, 1.6), (5, 1.0, 4, 1.8, 2.0)):
            d = {}
            g = grid(aud, n, s, L, c, m, d)
            eq = g.cumsum()
            print(f"  ma {n:2d} step {s:4.2f} levels {L} cost {c:3.1f} mult {m:3.1f}: {sharpe(g[:SPLIT]):+.2f} | {sharpe(g[SPLIT:]):+.2f}  "
                  f"{g.mean() * 252:+.2f} stop-out losses earned a year, worst day {g.min():+.2f}, max drawdown {(eq.cummax() - eq).max():.2f}, "
                  f"fills/yr {d['fills'] / (len(g) / 252):.0f}, stop-outs {d['stops']}", flush=True)
        print("Quartet trades, size x m for each loss in a row (three at most), not rescaled")
        for m in (1.0, 0.67, 1.5, 2.0):
            report(quartet(m)["2010-06-01":], f"m {m:.2f}")
    else:
        F = pd.DataFrame({"quartet": quartet(a.loss_mult, a.loss_norm),
                          "grid": a.grid_risk * grid(aud, a.ma, a.step, a.levels, a.cost, a.mult, swap=a.grid_swap),
                          "hold": hold(H.XAUUSD, a.hold_vol, a.swap),
                          "fix": fix(a.fix_risk, cost=a.fix_cost),
                          "cross": fix(a.cross_risk, cost=a.cross_cost, pairs=FIXCROSS, name="HYDRA_FIXX", after=False),
                          "fall": fall(a.fall_risk, cost=a.fix_cost),
                          "morning": morning(a.morning_risk),
                          "after": after(a.after_risk)}).loc["2010-06-01":].fillna(0.0)
        print("Correlation of daily results:\n" + F.corr().round(2).to_string())
        for name, x in (("quartet", F.quartet), ("grid", F.grid), ("hold", F.hold), ("fix", F.fix),
                        ("cross", F.cross), ("fall", F.fall), ("morning", F.morning),
                        ("after", F["after"]),
                        ("without after", F.sum(axis=1) - F["after"]), ("all eight", F.sum(axis=1))):
            report(x, name)
        print("Resampled 2018-2026 results of all eight (blocks of 5 days), every size multiplied:")
        ruin(F.sum(axis=1)[SPLIT:].to_numpy())
