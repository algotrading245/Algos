"""Loaders for the MT5 exports in marketdata/ (bars are bid prices, times are server time)."""
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "marketdata")
SYMBOL = "XAUUSD.pc"
POINT = 0.01


def bars(tf):
    df = pd.read_csv(os.path.join(ROOT, f"{SYMBOL}_{tf}.csv.gz"))
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["spread"] = df["spread_points"] * POINT
    df["dt"] = pd.to_datetime(df["time"], unit="s")
    return df


def tick_days():
    return sorted(glob.glob(os.path.join(ROOT, "ticks", f"{SYMBOL}_*.csv.gz")))


def ticks(path):
    df = pd.read_csv(path, usecols=["time_msc", "bid", "ask"])
    df = df[(df.bid > 0) & (df.ask > 0)]
    return df.time_msc.to_numpy(np.int64), df.bid.to_numpy(float), df.ask.to_numpy(float)
