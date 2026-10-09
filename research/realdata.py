"""Loaders for the MT5 exports in marketdata/ (bars are bid prices, times are server time).

Set AURUM_DATA=histdata to read the 2009+ internet history built by tools/download_histdata.py instead. That feed
has no spread and no volume: spread_points is filled with HIST_SPREAD_POINTS and tick_volume with the number of
1-minute bars. AURUM_FROM / AURUM_TO (YYYY-MM-DD) cut the period for either source."""
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "marketdata")
SYMBOL = "XAUUSD.pc"
POINT = 0.01


SOURCE = os.environ.get("AURUM_DATA", "broker")
HIST_SPREAD_POINTS = 11
SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def _hist(tf):
    """histdata 1-minute bars resampled to tf, cached next to the source file."""
    src = os.path.join(ROOT, "histdata", "XAUUSD_M1.csv.gz")
    out = os.path.join(ROOT, "histdata", f"XAUUSD_{tf}.csv.gz")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return pd.read_csv(out)
    m = pd.read_csv(src)
    m = m[pd.to_datetime(m.time, unit="s").dt.dayofweek < 5]          # a few stray quotes after the Friday close
    m["time"] = m.time // SECONDS[tf] * SECONDS[tf]
    df = m.groupby("time").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                               close=("close", "last"), tick_volume=("close", "size")).reset_index()
    df["spread_points"] = HIST_SPREAD_POINTS
    if tf != "M1":
        tmp = f"{out}.{os.getpid()}.tmp.gz"
        df.to_csv(tmp, index=False)
        os.replace(tmp, out)
    return df


def bars(tf):
    df = _hist(tf) if SOURCE == "histdata" else pd.read_csv(os.path.join(ROOT, f"{SYMBOL}_{tf}.csv.gz"))
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    for key, keep in (("AURUM_FROM", lambda t, x: t >= x), ("AURUM_TO", lambda t, x: t < x)):
        if os.environ.get(key):
            df = df[keep(df.time, pd.Timestamp(os.environ[key]).timestamp())].reset_index(drop=True)
    df["spread"] = df["spread_points"] * POINT
    df["dt"] = pd.to_datetime(df["time"], unit="s")
    return df


def tick_days():
    return sorted(glob.glob(os.path.join(ROOT, "ticks", f"{SYMBOL}_*.csv.gz")))


def ticks(path):
    df = pd.read_csv(path, usecols=["time_msc", "bid", "ask"])
    df = df[(df.bid > 0) & (df.ask > 0)]
    return df.time_msc.to_numpy(np.int64), df.bid.to_numpy(float), df.ask.to_numpy(float)
