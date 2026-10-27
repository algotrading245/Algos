"""BTCUSD and ETHUSD M1 history for the sandbox, from Binance's public archive (data.binance.vision, spot USDT pairs).

Writes marketdata/histdata/{BTCUSD,ETHUSD}_M1.csv.gz in the desk's format: server-time epoch seconds (New York + 7),
open, high, low, close. Stops before the holdout (base.HOLDOUT, server time); nothing on or after it is fetched.
Resumable: months already downloaded sit in marketdata/histdata/raw/crypto/ and are not fetched again.

    python -m desk.fetch_crypto [BTCUSD ETHUSD]
"""
import datetime as dt
import io
import sys
import urllib.error
import urllib.request
import zipfile

import pandas as pd

from desk import clocks
from desk.edges import base

PAIRS = {"BTCUSD": ("BTCUSDT", dt.date(2017, 8, 1)), "ETHUSD": ("ETHUSDT", dt.date(2017, 8, 1))}
URL = "https://data.binance.vision/data/spot/{span}/klines/{pair}/1m/{pair}-1m-{stamp}.zip"
RAW = base.HIST / "raw" / "crypto"
LAST = base.HOLDOUT - dt.timedelta(days=2)  # the last UTC day fetched: it ends before the holdout in server time


def _get(url, dest):
    if dest.exists():
        return dest.read_bytes()
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    part.write_bytes(data)
    part.replace(dest)  # a stopped run leaves no half-written zip
    return data


def _frame(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=range(5))
    df.columns = ["open_ms", "open", "high", "low", "close"]
    if not str(df["open_ms"].iloc[0]).isdigit():
        df = df.iloc[1:]  # a header row in some files
    t = pd.to_numeric(df["open_ms"]).astype("int64")
    t = t // 1000 if t.iloc[0] < 10 ** 13 else t // 1_000_000  # ms, or us since 2025
    return pd.DataFrame({"time": t, "open": df["open"].astype(float), "high": df["high"].astype(float),
                         "low": df["low"].astype(float), "close": df["close"].astype(float)})


def _spans(start):
    m = start
    while (m.year, m.month) < (LAST.year, LAST.month):
        yield "monthly", m.strftime("%Y-%m")
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    d = m
    while d <= LAST:
        yield "daily", d.isoformat()
        d += dt.timedelta(days=1)


def to_server(utc_epoch):
    """UTC epoch seconds to server-time epoch seconds (New York + 7, so DST moves with New York)."""
    utc = pd.to_datetime(utc_epoch, unit="s", utc=True)
    off = (utc.dt.tz_convert(clocks.NY).dt.tz_localize(None) - utc.dt.tz_localize(None)).dt.total_seconds()
    off = off.astype("int64")
    return utc_epoch.values + off.values + 7 * 3600


def fetch(sym):
    pair, start = PAIRS[sym]
    parts = []
    for span, stamp in _spans(start):
        data = _get(URL.format(span=span, pair=pair, stamp=stamp), RAW / f"{pair}-1m-{stamp}.zip")
        if data:
            parts.append(_frame(data))
    df = pd.concat(parts).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["time"] = to_server(df["time"])
    df = df[df["time"] < base.HOLDOUT_EPOCH]
    out = base.HIST / f"{sym}_M1.csv.gz"
    part = base.HIST / f"{sym}_M1.part"
    df.to_csv(part, index=False, compression="gzip")
    part.replace(out)  # the sandbox never reads a half-written file
    return {"sym": sym, "rows": len(df), "from": str(pd.to_datetime(df["time"].iloc[0], unit="s")),
            "to": str(pd.to_datetime(df["time"].iloc[-1], unit="s")), "file": str(out)}


if __name__ == "__main__":
    for s in sys.argv[1:] or list(PAIRS):
        print(fetch(s), flush=True)
