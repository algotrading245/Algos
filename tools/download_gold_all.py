"""Download every free gold price history that can be fetched without an account.

Stages (each one resumes: files already on disk are skipped):

    daily      monthly averages since 1833 (datahub.io), COMEX gold futures and the GLD fund, daily (Yahoo),
               and Dukascopy daily bid and ask candles                  -> marketdata/gold/daily/
    histticks  histdata.com tick quotes (bid and ask), one zip a month  -> marketdata/histdata/ticks_raw/
    dukam1     Dukascopy 1-minute bid and ask candles, one file a day   -> marketdata/dukascopy/XAUUSD_M1/
    dukaticks  Dukascopy ticks (bid, ask, volumes), one file an hour    -> marketdata/dukascopy/XAUUSD/
    build      Dukascopy 1-minute files -> marketdata/dukascopy/XAUUSD_M1.csv.gz (UTC; bid OHLC, ask OHLC, volume)

Dukascopy answers slowly and with 503 when pressed, so its files are fetched over a few parallel connections
with retries.

    python tools\\download_gold_all.py daily histticks dukam1 build dukaticks
"""
import argparse
import io
import json
import lzma
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DUKA = "http://datafeed.dukascopy.com/datafeed/XAUUSD/"
HIST = "https://www.histdata.com/"
FIRST = date(2003, 5, 5)          # first day Dukascopy has for gold


def get(url, data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def duka(path, target, pause=0.0):
    """Fetch one Dukascopy file. An empty file is a closed market; it is stored empty so it is not asked for again."""
    if target.exists():
        return False
    wait = 2
    for _ in range(15):
        try:
            body = get(DUKA + path, timeout=60)
            tmp = target.with_suffix(".part")
            tmp.write_bytes(body)
            tmp.replace(target)
            time.sleep(pause)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                target.write_bytes(b"")
                return True
        except Exception:
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60)
    print("   gave up on", path, flush=True)
    return False


def duka_many(jobs, threads, label):
    """jobs: (url path, target file). The server answers slowly per connection, so several run side by side."""
    jobs = [j for j in jobs if not j[1].exists()]
    print(f"{label}: {len(jobs)} files to fetch", flush=True)
    t0, done = time.time(), 0
    with ThreadPoolExecutor(threads) as ex:
        for ok in ex.map(lambda j: duka(*j), jobs):
            done += 1
            if done % 250 == 0:
                left = (len(jobs) - done) * (time.time() - t0) / done / 3600
                print(f"{label}: {done}/{len(jobs)}, about {left:.1f} h left", flush=True)
    print(f"{label} complete", flush=True)


def days(first, last):
    d = first
    while d <= last:
        if d.weekday() != 5:      # nothing trades on Saturday
            yield d
        d += timedelta(days=1)


def stage_daily(a):
    out = ROOT / "gold" / "daily"
    out.mkdir(parents=True, exist_ok=True)
    (out / "monthly_1833.csv").write_bytes(get("https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"))
    print("monthly averages since 1833 saved", flush=True)
    for sym, name in (("GC=F", "comex_futures_daily"), ("GLD", "gld_fund_daily")):
        j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
                           f"?period1=0&period2={int(time.time())}&interval=1d"))["chart"]["result"][0]
        q = j["indicators"]["quote"][0]
        rows = ["date,open,high,low,close,volume"]
        for i, t in enumerate(j["timestamp"]):
            if q["close"][i] is not None:
                rows.append(f"{datetime.fromtimestamp(t, timezone.utc).date()},{q['open'][i]},{q['high'][i]},{q['low'][i]},"
                            f"{q['close'][i]},{q['volume'][i]}")
        (out / f"{name}.csv").write_text("\n".join(rows) + "\n")
        print(f"{name}: {len(rows) - 1} days, {rows[1][:10]} to {rows[-1][:10]}", flush=True)
    raw = out / "dukascopy_raw"
    raw.mkdir(exist_ok=True)
    rows = ["date,side,open,high,low,close,volume"]
    for y in range(1999, date.today().year + 1):
        for side in ("BID", "ASK"):
            f = raw / f"{y}_{side}.bi5"
            if y == date.today().year and f.exists():
                f.unlink()
            duka(f"{y}/{side}_candles_day_1.bi5", f, a.pause)
            if f.exists() and f.stat().st_size:
                b = lzma.decompress(f.read_bytes())
                for k in range(0, len(b), 24):
                    s, o, c, lo, h, v = struct.unpack(">5if", b[k:k + 24])
                    if v > 0:
                        rows.append(f"{date(y, 1, 1) + timedelta(seconds=s)},{side},{o / 1000},{h / 1000},{lo / 1000},{c / 1000},{v:.4f}")
    (out / "dukascopy_daily.csv").write_text("\n".join(rows) + "\n")
    print(f"dukascopy daily candles: {len(rows) - 1} rows, first {rows[1][:10] if len(rows) > 1 else '-'}", flush=True)


def stage_histticks(a):
    out = ROOT / "histdata" / "ticks_raw"
    out.mkdir(parents=True, exist_ok=True)
    today = date.today()
    for y in range(2009, today.year + 1):
        for m in range(1, 13):
            if (y, m) >= (today.year, today.month):
                break
            f = out / f"XAUUSD_{y}_{m:02d}.zip"
            if f.exists():
                continue
            url = f"{HIST}download-free-forex-historical-data/?/ascii/tick-data-quotes/xauusd/{y}/{m}"
            for attempt in range(4):
                try:
                    page = get(url, timeout=60).decode("utf-8", "replace")
                    if 'id="file_down"' not in page:
                        print(f"histdata ticks {y}-{m:02d}: not offered", flush=True)
                        break
                    form = page[page.index('id="file_down"'):]
                    fields = {k: re.search(rf'name="{k}"[^>]*value="([^"]*)"', form).group(1)
                              for k in ("tk", "date", "datemonth", "platform", "timeframe", "fxpair")}
                    body = get(HIST + "get.php", urllib.parse.urlencode(fields).encode(), {"Referer": url}, 900)
                    if body[:2] != b"PK":      # the page exists but the month has no file
                        print(f"histdata ticks {y}-{m:02d}: not offered", flush=True)
                        break
                    tmp = f.with_suffix(".part")
                    tmp.write_bytes(body)
                    tmp.replace(f)
                    print(f"histdata ticks {y}-{m:02d}: {len(body) / 1e6:.1f} MB", flush=True)
                    break
                except Exception as e:
                    print(f"histdata ticks {y}-{m:02d}: {e}, retry", flush=True)
                    time.sleep(20 * (attempt + 1))
            time.sleep(1)


def stage_dukam1(a):
    out = ROOT / "dukascopy" / "XAUUSD_M1"
    out.mkdir(parents=True, exist_ok=True)
    duka_many([(f"{d.year}/{d.month - 1:02d}/{d.day:02d}/{side}_candles_min_1.bi5", out / f"{d:%Y%m%d}_{side}.bi5")
               for d in days(max(FIRST, a.first), date.today() - timedelta(days=2)) for side in ("BID", "ASK")],
              a.threads, "dukascopy M1")


def stage_dukaticks(a):
    out = ROOT / "dukascopy" / "XAUUSD"
    out.mkdir(parents=True, exist_ok=True)
    duka_many([(f"{d.year}/{d.month - 1:02d}/{d.day:02d}/{h:02d}h_ticks.bi5", out / f"{d:%Y%m%d}_{h:02d}.bi5")
               for d in days(max(FIRST, a.first), date.today() - timedelta(days=2)) for h in range(24)],
              a.threads, "dukascopy ticks")


def stage_build(a):
    import numpy as np
    import pandas as pd
    src = ROOT / "dukascopy" / "XAUUSD_M1"
    dt = np.dtype([("s", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"), ("h", ">i4"), ("v", ">f4")])
    parts = {"BID": [], "ASK": []}
    for f in sorted(src.glob("*.bi5")):
        if not f.stat().st_size:
            continue
        day, side = f.stem.split("_")
        r = np.frombuffer(lzma.decompress(f.read_bytes()), dt)
        r = r[r["v"] > 0]
        t0 = int(datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp())
        parts[side].append(pd.DataFrame({"time": t0 + r["s"].astype("int64"), "open": r["o"] / 1000, "high": r["h"] / 1000,
                                         "low": r["l"] / 1000, "close": r["c"] / 1000, "volume": r["v"].astype("float64")}))
    bid = pd.concat(parts["BID"]).set_index("time")
    ask = pd.concat(parts["ASK"]).set_index("time").drop(columns="volume").add_prefix("ask_")
    m = bid.join(ask, how="left").reset_index().round(3)
    m.to_csv(ROOT / "dukascopy" / "XAUUSD_M1.csv.gz", index=False)
    print(f"XAUUSD_M1.csv.gz: {len(m)} bars, {pd.to_datetime(m.time.iloc[0], unit='s')} to "
          f"{pd.to_datetime(m.time.iloc[-1], unit='s')} UTC", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stages", nargs="+", choices=["daily", "histticks", "dukam1", "dukaticks", "build"])
    p.add_argument("--pause", type=float, default=0.4, help="seconds between Dukascopy requests")
    p.add_argument("--threads", type=int, default=12, help="parallel Dukascopy connections")
    p.add_argument("--first", type=date.fromisoformat, default=FIRST)
    a = p.parse_args()
    for s in a.stages:
        globals()["stage_" + s](a)
