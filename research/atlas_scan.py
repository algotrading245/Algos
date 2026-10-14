"""Discovery scan for conditional session flows.

For every driver X (stock indices, oil, gold, the dollar) and every forex or metal symbol Y: after a day on which X
moved unusually far (top 15% of its last 250 days), is Y's move in a fixed window of the next server day related to
the sign of X's move? Rules are found on the days before 2018 only and then checked on 2018 onwards.

Half-hour bid closes on the server clock (New York + 7 hours, so a server day is 17:00 to 17:00 New York) are cached
in marketdata/histdata/ATLAS_HALF.npz.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "marketdata" / "histdata"
TARGETS = ["AUDCAD", "AUDJPY", "AUDNZD", "AUDUSD", "CADJPY", "EURAUD", "EURCHF", "EURGBP", "EURJPY", "EURUSD", "GBPCHF",
           "GBPJPY", "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "XAGUSD", "XAUUSD"]
DRIVERS = ["SPXUSD", "GRXEUR", "JPXJPY", "WTIUSD", "XAUUSD"]
DOLLAR = {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1, "USDJPY": 1, "USDCAD": 1, "USDCHF": 1}
COST = {"XAGUSD": 4.0, "XAUUSD": 1.0, "EURUSD": 0.8, "GBPUSD": 0.8, "USDJPY": 0.8}     # bp per round trip, others 1.5
LENS = (2, 4, 8)                                                                        # window lengths, half-hours
CUT = np.datetime64("2018-01-01")


def half():
    f = DATA / "ATLAS_HALF.npz"
    if f.exists():
        z = np.load(f)
        return {s: z[s] for s in z.files if s != "days"}, pd.DatetimeIndex(z["days"])
    days = pd.bdate_range("2009-06-01", "2026-10-09")
    dn = (days.to_numpy().astype("datetime64[D]").astype(np.int64))
    out = {}
    for s in sorted(set(TARGETS + DRIVERS)):
        m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"], dtype={"time": np.int64, "close": np.float64})
        x = m.groupby(m.time // 1800).close.last()
        del m
        k = x.index.to_numpy()
        row = np.searchsorted(dn, k // 48)
        ok = (row < len(dn)) & (dn[np.minimum(row, len(dn) - 1)] == k // 48)
        M = np.full((len(days), 48), np.nan, dtype=np.float32)
        M[row[ok], (k % 48)[ok]] = x.to_numpy()[ok]
        out[s] = pd.DataFrame(M).ffill(axis=1, limit=2).to_numpy(dtype=np.float32)
        print("built", s, flush=True)
    np.savez_compressed(f, days=days.to_numpy(), **out)
    return out, days


def close(M):
    """Last price of each server day, carried over days without one."""
    return pd.DataFrame(M).ffill(axis=1).iloc[:, -1].ffill().to_numpy(dtype=np.float64)


def signals(P, q=0.85):
    """{driver: +1/-1 on the day after an unusually large move of it, else 0}"""
    r = {s: np.diff(np.log(close(P[s])), prepend=np.nan) for s in set(DRIVERS) | set(DOLLAR)}
    r["DOLLAR"] = np.nanmean([sg * r[s] for s, sg in DOLLAR.items()], axis=0)
    out = {}
    for s in DRIVERS + ["DOLLAR"]:
        a = pd.Series(np.abs(r[s]))
        big = a >= a.rolling(250, min_periods=120).quantile(q).shift(1)
        out[s] = pd.Series(np.where(big, np.sign(r[s]), 0.0)).shift(1).fillna(0.0).to_numpy()
    return out


def tstat(x):
    n = (~np.isnan(x)).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nanmean(x, axis=0) / np.nanstd(x, axis=0) * np.sqrt(n), n


def scan(tmin=3.5):
    P, days = half()
    S = signals(P)
    tr = days.to_numpy() < CUT
    rows = []
    for y in TARGETS:
        lp = np.log(P[y].astype(np.float64))
        for L in LENS:
            R = lp[:, 1 + L:] - lp[:, 1:48 - L]                  # start slots 1..47-L (slot 0 is the rollover)
            for d, sg in S.items():
                if d == y:
                    continue
                X = np.where(sg[:, None] != 0, sg[:, None] * R, np.nan)
                t1, n1 = tstat(X[tr])
                t2, n2 = tstat(X[~tr])
                for a in np.flatnonzero(np.abs(np.nan_to_num(t1)) >= tmin):
                    c = COST.get(y, 1.5) * 1e-4
                    side = np.sign(t1[a])
                    net = side * X[~tr, a] - c
                    rows.append((d, y, a + 1, L, side, t1[a], n1[a], t2[a] * side, n2[a], 1e4 * np.nanmean(side * X[tr, a]),
                                 1e4 * np.nanmean(side * X[~tr, a]), 1e4 * np.nanmean(net)))
    T = pd.DataFrame(rows, columns=["driver", "pair", "slot", "len", "side", "t_train", "n_train", "t_test", "n_test",
                                    "bp_train", "bp_test", "bp_test_net"])
    ntests = len(TARGETS) * len(S) * sum(47 - L for L in LENS)
    print("tests %d, found on train with |t|>=%.1f: %d (chance alone would give about %.1f)" % (
        ntests, tmin, len(T), ntests * {3.0: 0.0027, 3.5: 0.00047, 4.0: 0.000063}.get(tmin, np.nan)))
    print("of those, same sign on test with t>=2: %d ; net of cost positive on test: %d" % (
        (T.t_test >= 2).sum(), ((T.t_test >= 2) & (T.bp_test_net > 0)).sum()))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    print(T.sort_values("t_test", ascending=False).round(2).to_string(index=False))
    return T


if __name__ == "__main__":
    scan(float(sys.argv[1]) if len(sys.argv) > 1 else 3.5)
