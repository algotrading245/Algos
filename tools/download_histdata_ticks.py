"""Download histdata.com tick quotes (bid and ask) for one pair and keep one window of the day.

A month of ticks is tens of megabytes, so only the server-time minutes --from to --to of each day are kept
(server time = New York time plus 7 hours, as in tools/download_histdata.py). One pickle per month is written to
--out as <PAIR>_<year>_<month>.pkl with the columns srv, bid, ask; months already there are skipped.

Usage: python tools/download_histdata_ticks.py XAUUSD --out <dir> --from 1360 --to 1400 --first 2015-01 --last 2026-09
"""
import argparse
import io
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}
SITE = "https://www.histdata.com/"


def month(pair, year, mon, lo, hi):
    """Ticks of one month inside the server minutes lo..hi of the day."""
    url = f"{SITE}download-free-forex-historical-data/?/ascii/tick-data-quotes/{pair.lower()}/{year}/{mon}"
    page = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")
    form = page[page.index('id="file_down"'):]
    fields = {k: re.search(rf'name="{k}"[^>]*value="([^"]*)"', form).group(1)
              for k in ("tk", "date", "datemonth", "platform", "timeframe", "fxpair")}
    req = urllib.request.Request(SITE + "get.php", data=urllib.parse.urlencode(fields).encode(), headers={**UA, "Referer": url})
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(req, timeout=600).read()))
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    out = []
    for c in pd.read_csv(z.open(name), header=None, names=["t", "bid", "ask", "v"], usecols=[0, 1, 2], dtype={"t": str},
                         chunksize=500000):
        # the file's clock is London time minus 5 hours all year
        london = pd.to_datetime(c.t, format="%Y%m%d %H%M%S%f") + pd.Timedelta(hours=5)
        c["srv"] = (london.dt.tz_localize("Europe/London", ambiguous="NaT", nonexistent="NaT")
                    .dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7))
        mod = c.srv.dt.hour * 60 + c.srv.dt.minute
        out.append(c[(mod >= lo) & (mod < hi)][["srv", "bid", "ask"]])
    return pd.concat(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pair", help="for example XAUUSD or USDJPY")
    ap.add_argument("--out", required=True, help="directory for the monthly files")
    ap.add_argument("--from", dest="lo", type=int, default=1360, help="first server minute of the day kept")
    ap.add_argument("--to", dest="hi", type=int, default=1400, help="server minute of the day the window ends at")
    ap.add_argument("--first", default="2015-01", help="first month, YYYY-MM")
    ap.add_argument("--last", required=True, help="last month, YYYY-MM")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for p in reversed(pd.period_range(a.first, a.last, freq="M")):
        dst = os.path.join(a.out, f"{a.pair}_{p.year}_{p.month}.pkl")
        if os.path.exists(dst):
            continue
        try:
            df = month(a.pair, p.year, p.month, a.lo, a.hi)
            df.to_pickle(dst)
            print(a.pair, p, len(df), "ticks kept", flush=True)
        except Exception as e:
            print(a.pair, p, "failed", repr(e)[:100], flush=True)
        time.sleep(1)
