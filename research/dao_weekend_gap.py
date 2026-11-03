"""Dao, McGroarty, Urquhart (2016) weekend-gap reversal on 8 FX pairs, FTMO-style costs.
Rule (fixed from the paper, nothing tuned): gap = ln(first bar of week / last bar of previous week); large = outside the
5%/95% quantile of the previous 260 weekend gaps of the same pair; trade opposite the gap at the week's first bar, hold
to the week's last bar. Equal weight over the 8 pairs (a pair in position gets 1/8 of the book).
Costs: round-trip spread per pair (assumed typical FTMO, pips) + swap for 6 nights (Mon open to Fri close incl. Wed triple).
Writes marketdata/candidates/dao_gap.csv (+ _stress at 1.5x) and dao_gap_markets.csv (per pair, real costs)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
import holdout

PAIRS = {  # pip size, assumed round-trip spread in pips (incl. wider weekly open), swap long/short points/night
    "EURUSD": (1e-4, 1.2, -10.08, 0.41), "GBPUSD": (1e-4, 1.8, -5.36, -4.07), "USDJPY": (1e-2, 1.8, 3.33, -20.31),
    "AUDUSD": (1e-4, 1.8, -2.87, -6.31), "NZDUSD": (1e-4, 2.5, -4.87, 0.04), "USDCHF": (1e-4, 2.2, 2.56, -13.37),
    "USDCAD": (1e-4, 2.2, 1.17, -12.5), "AUDCAD": (1e-4, 3.0, 2.24, -10.78)}
POINT = {"USDJPY": 1e-3}
Q, WIN = 0.05, 260


def load(p):
    d = pd.read_csv(f"marketdata/histdata/{p}_M1.csv.gz")
    d["t"] = pd.to_datetime(d["time"], unit="s") + pd.Timedelta(hours=7)   # EST: Sunday 17:00 -> Monday 00:00
    d = d.set_index("t")
    d = d[d.index < holdout.START]
    return d


def run(p, mult):
    pip, spr, sl, ss = PAIRS[p][0], PAIRS[p][1], PAIRS[p][2], PAIRS[p][3]
    pt = POINT.get(p, 1e-5)
    d = load(p)
    gap_id = (d.index.to_series().diff() > pd.Timedelta(hours=24)).cumsum()
    g = d.groupby(gap_id.values)
    first = g["open"].first(); last = g["close"].last()
    start = g.apply(lambda x: x.index[0]); end = g.apply(lambda x: x.index[-1])
    wk = pd.DataFrame({"fo": first, "lc": last, "s": start, "e": end})
    wk = wk[(wk.e - wk.s) > pd.Timedelta(days=3)]          # full weeks only
    wk["gap"] = np.log(wk.fo / wk.lc.shift(1))
    # past-only quantiles
    past = wk.gap.shift(1)
    lo = past.rolling(WIN, min_periods=WIN).quantile(Q); hi = past.rolling(WIN, min_periods=WIN).quantile(1 - Q)
    wk["dir"] = np.where(wk.gap >= hi, -1, np.where(wk.gap <= lo, 1, 0))
    daily_close = d["close"].groupby(d.index.normalize()).last()
    rows = {}
    ntr = 0
    for i, w in wk.iterrows():
        if w.dir == 0 or np.isnan(w.gap):
            continue
        ntr += 1
        days = daily_close[(daily_close.index >= w.s.normalize()) & (daily_close.index <= w.e.normalize())]
        px = np.r_[w.fo, days.values]
        # last close of the week equals days.iloc[-1]
        r = w.dir * np.diff(np.log(px))
        swap_pts = sl if w.dir > 0 else ss
        mid = w.fo
        cost_in = mult * spr * pip / mid
        swap_d = swap_pts * pt / mid / 1.0                    # per night, points -> fraction of price
        nights = np.r_[np.zeros(len(r))]
        for k in range(len(r)):
            nights[k] = swap_d * (3 if days.index[k].dayofweek == 2 else 1) if days.index[k].dayofweek < 4 else 0
        r = r + nights * mult
        r[0] -= cost_in
        for dt, v in zip(days.index, r):
            rows[dt] = rows.get(dt, 0) + v
    return pd.Series(rows, dtype=float).sort_index(), ntr


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan


if __name__ == "__main__":
    out = {1.0: [], 1.5: [], 2.0: []}
    mk = {}
    for p in PAIRS:
        for m in out:
            s, n = run(p, m)
            out[m].append(s.rename(p))
            if m == 1.0:
                mk[p] = s
                print(p, "trades", n, "sharpe all", round(sharpe(s.reindex(pd.bdate_range(s.index[0], s.index[-1])).fillna(0)), 2))
    res = {}
    for m, lst in out.items():
        df = pd.concat(lst, axis=1)
        idx = pd.bdate_range("2010-01-01", df.index.max())
        df = df.reindex(idx).fillna(0)
        basket = df.sum(axis=1) / len(PAIRS)
        res[m] = basket
        h1 = basket[basket.index < "2018-01-01"]; h2 = basket[basket.index >= "2018-01-01"]
        print(f"cost {m}x  sharpe all {sharpe(basket):.2f}  to2017 {sharpe(h1):.2f}  2018on {sharpe(h2):.2f}  "
              f"ann ret {basket.mean()*252:.4f}  tradedays {(basket != 0).sum()}")
    b = res[1.0]
    pd.DataFrame({"day": b.index.strftime("%Y-%m-%d"), "r": b.values}).to_csv("marketdata/candidates/dao_gap.csv", index=False)
    b = res[1.5]
    pd.DataFrame({"day": b.index.strftime("%Y-%m-%d"), "r": b.values}).to_csv("marketdata/candidates/dao_gap_stress.csv", index=False)
    mdf = pd.concat([mk[p].rename(p) for p in PAIRS], axis=1)
    mdf = mdf.reindex(pd.bdate_range("2010-01-01", mdf.index.max())).fillna(0)
    mdf.index.name = "day"
    mdf.to_csv("marketdata/candidates/dao_gap_markets.csv", date_format="%Y-%m-%d")
