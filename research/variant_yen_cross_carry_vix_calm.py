"""Yen-cross carry held only while VIX is calm (queue id variant_yen_cross_carry_vix_calm).

Fixed rule, no sweep: long pair at the 22:59 server-clock daily close when (a) prior-day VIX close < trailing-250d median
(VIX lagged one day, median over days up to the lag) and (b) pair close > 100d SMA; exit when either fails or close falls
3 ATR(20) (close-to-close abs-move mean) below entry.  Cost: one spread per round trip (bid data, buy at ask) + the
FTMO long swap in points (7 nights per 5 weekdays) as a constant.  Stress 1.5x / 2x on the spread and negative swap only.
Equal risk: each pair scaled to 10% annual vol using 20d trailing vol; portfolio = mean over 4 pairs (flat = 0).
Holdout dropped through tools/holdout.py.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

# spread points (0.001), swap_long points per lot-day (docs/ftmo_specs.json); NZDJPY snapshot spread 0 -> 25 assumed
PAIRS = {"AUDJPY": (20, 4.27), "NZDJPY": (25, 0.84), "CADJPY": (14, 0.54), "GBPJPY": (28, 5.14)}
PT = 0.001


def daily_close(name):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{name}_M1.csv.gz")
    d = d.drop_duplicates("time").sort_values("time")
    d["dt"] = pd.to_datetime(d.time, unit="s")
    d = d[d.dt < holdout.START]
    d["day"] = d.dt.dt.normalize()
    d["mod"] = d.dt.dt.hour * 60 + d.dt.dt.minute
    d = d[(d.dt.dt.dayofweek < 5) & (d["mod"] <= 22 * 60 + 59)]
    return d.groupby("day").close.last()


def run(name, vix, sp_mult=1.0, swap_mult=1.0):
    spread_pts, swap_pts = PAIRS[name]
    c = daily_close(name)
    c = c[c.index.dayofweek < 5]
    ret = c.pct_change()
    sma = c.rolling(100).mean()
    v = vix.reindex(c.index).ffill().shift(1)  # lagged one day
    med = v.rolling(250).median()
    calm = v < med
    atr = c.diff().abs().rolling(20).mean()
    vol = ret.rolling(20).std().shift(1)
    sig = (calm & (c > sma)).fillna(False)
    pos = np.zeros(len(c))
    entry_stop = np.nan
    prev = 0
    cv, av, sv = c.values, atr.values, sig.values
    for i in range(len(c) - 1):
        # decide at close i for day i+1
        if prev == 1:
            if (not sv[i]) or cv[i] < entry_stop:
                p = 0
            else:
                p = 1
        else:
            if sv[i] and not np.isnan(av[i]):
                p = 1
                entry_stop = cv[i] - 3 * av[i]
            else:
                p = 0
        pos[i + 1] = p
        prev = p
    pos = pd.Series(pos, index=c.index)
    w = ((0.10 / np.sqrt(252)) / vol).clip(upper=4)
    gross = pos * ret
    trans = (pos.diff().abs().fillna(0))
    # one spread per round trip: charge half at entry and half at exit
    cost = trans * 0.5 * (spread_pts * PT / c) * sp_mult
    dow = pd.Series(c.index.dayofweek, index=c.index)
    nights = np.where(dow.values == 2, 3.0, 1.0) * 5 / 7 * 1.0  # 7 nights per 5 weekdays
    swap = pos.shift(0) * (swap_pts * PT / c) * nights
    swap = swap.where(swap >= 0, swap) * swap_mult  # positive; stress scales only if swap_mult<1
    net = (gross - cost + swap) * w
    return net.dropna(), pos


def main():
    vx = pd.read_csv(ROOT / "marketdata" / "vixidx" / "^VIX.csv", parse_dates=["date"]).set_index("date").close
    res = {}
    for lab, spm in (("1x", 1.0), ("1.5x", 1.5), ("2x", 2.0)):
        cols = {}
        for p in PAIRS:
            n, pos = run(p, vx, spm, 1.0)
            cols[p] = n
        df = pd.DataFrame(cols)
        res[lab] = df
    idx = pd.bdate_range("2010-06-01", holdout.START - pd.Timedelta(days=1))
    out = {}
    for lab, df in res.items():
        df = df.reindex(idx).fillna(0)
        out[lab] = df
    book = out["1x"].mean(axis=1)
    stress = out["1.5x"].mean(axis=1)
    s2 = out["2x"].mean(axis=1)

    def sh(x):
        return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")

    for lab, x in (("1x", book), ("1.5x", stress), ("2x", s2)):
        print(lab, "full", round(sh(x), 3), "to2017", round(sh(x[x.index < "2018-01-01"]), 3),
              "2018on", round(sh(x[x.index >= "2018-01-01"]), 3), "ann%", round(x.mean() * 252 * 100, 2))
    print("per pair 1x Sharpe (to2017 / 2018on):")
    mk = out["1x"]
    for p in PAIRS:
        a, b = mk[p][mk.index < "2018-01-01"], mk[p][mk.index >= "2018-01-01"]
        print(" ", p, round(sh(a), 2), round(sh(b), 2), "full", round(sh(mk[p]), 2))
    # time in market
    for p in PAIRS:
        _, pos = run(p, vx)
        print(p, "share long", round(pos.mean(), 2))
    cd = ROOT / "marketdata" / "candidates"
    book.rename("r").rename_axis("day").to_csv(cd / "variant_yen_cross_carry_vix_calm.csv")
    stress.rename("r").rename_axis("day").to_csv(cd / "variant_yen_cross_carry_vix_calm_stress.csv")
    mk.rename_axis("day").to_csv(cd / "variant_yen_cross_carry_vix_calm_markets.csv")


if __name__ == "__main__":
    main()
