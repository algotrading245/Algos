"""Download 1-minute history from histdata.com and convert it to the layout of the MT5 exports.

histdata.com serves one zip per past year and one per month of the current year. Bars are bid prices stamped in a
clock that runs 5 hours behind London. They are shifted to the broker's server clock (UTC+2, UTC+3 while the US is
on daylight saving), so 17:00 New York is always 00:00 server time, as in marketdata/XAUUSD.pc_*.csv.gz.

Output: marketdata/histdata/raw/*.zip and marketdata/histdata/<SYMBOL>_M1.csv.gz (time, open, high, low, close).
The source has no spread and no real volume, and it is a different liquidity feed from the broker's.

    python tools\\download_histdata.py [--from 2009] [SYMBOL ...]      (default XAUUSD; e.g. EURUSD SPXUSD WTIUSD)
"""
import argparse
import io
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{}/"
OUT = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(period, symbol="XAUUSD"):
    """period is '2023' or '2026/4'. Returns the path of the downloaded zip."""
    path = OUT / "raw" / f"{symbol}_M1_{period.replace('/', '_')}.zip"
    if path.exists() and path.stat().st_size > 1000:
        return path
    url = BASE.format(symbol.lower()) + period
    page = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")
    form = page[page.index('id="file_down"'):]
    fields = {k: re.search(rf'name="{k}"[^>]*value="([^"]*)"', form).group(1)
              for k in ("tk", "date", "datemonth", "platform", "timeframe", "fxpair")}
    req = urllib.request.Request("https://www.histdata.com/get.php", data=urllib.parse.urlencode(fields).encode(),
                                 headers={**UA, "Referer": url})
    body = urllib.request.urlopen(req, timeout=180).read()
    if not body.startswith(b"PK"):
        raise RuntimeError(f"{period}: server did not return a zip ({len(body)} bytes)")
    path.write_bytes(body)
    return path


def read(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(io.BytesIO(z.read(name)), sep=";", header=None,
                         names=["stamp", "open", "high", "low", "close", "volume"])
    df["est"] = pd.to_datetime(df.stamp, format="%Y%m%d %H%M%S")
    return df[["est", "open", "high", "low", "close"]]


def _between(t, first, last):
    """True where t falls between the given Sundays of its year; each is (month, n), n = -1 for the last Sunday."""
    out = pd.Series(False, index=t.index)
    for y in t.dt.year.unique():
        lo, hi = (pd.date_range(f"{y}-{m:02d}-01", periods=31, freq="D") for m, _ in (first, last))
        lo, hi = (d[(d.dayofweek == 6) & (d.month == m)][n - 1 if n > 0 else -1] for d, (m, n) in ((lo, first), (hi, last)))
        out |= (t >= lo) & (t < hi)
    return out


def to_server(stamp):
    """The file's clock is London time minus 5 hours all year (checked against the broker's bars, 2022-2026)."""
    london = stamp + pd.Timedelta(hours=5)
    us = _between(london, (3, 2), (11, 1)).astype(int)
    uk = _between(london, (3, -1), (10, -1)).astype(int)
    return london + pd.to_timedelta(2 + us - uk, unit="h")


def build(symbol, first):
    today = date.today()
    periods = [str(y) for y in range(first, today.year)] + [f"{today.year}/{m}" for m in range(1, today.month + 1)]
    parts = []
    for p in periods:
        try:
            parts.append(read(fetch(p, symbol)))
            print(f"{symbol} {p}: {len(parts[-1])} bars", flush=True)
        except Exception as e:
            print(f"{symbol} {p}: failed, {e}", flush=True)
        time.sleep(1)
    if not parts:
        return
    df = pd.concat(parts).drop_duplicates("est").sort_values("est").reset_index(drop=True)
    server = to_server(df.est)
    df.insert(0, "time", (server - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))
    df = df.drop(columns="est")
    tmp = OUT / f"{symbol}_M1.csv.gz.part"
    df.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(OUT / f"{symbol}_M1.csv.gz")
    print(f"{symbol}: {len(df)} bars, {pd.to_datetime(df.time.iloc[0], unit='s')} -> "
          f"{pd.to_datetime(df.time.iloc[-1], unit='s')} server time", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", type=int, default=2009)
    ap.add_argument("symbols", nargs="*", default=["XAUUSD"])
    a = ap.parse_args()
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    for sym in a.symbols:
        build(sym.upper(), a.first)
