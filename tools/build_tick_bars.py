"""Turn the histdata.com gold tick zips into 1-minute bid and ask bars, so backtests can pay the quoted spread.

Reads   marketdata/histdata/ticks_raw/XAUUSD_YYYY_MM.zip   (time = London time minus 5 hours, bid, ask)
Writes  marketdata/histdata/ticks_m1/XAUUSD_YYYY_MM.npz    one file a month, resumable
        marketdata/histdata/XAUUSD_BA_M1.npz               all months joined (stage 'join')

Columns: time (unix seconds of the bar open, server time = New York + 7 h), bid open/high/low/close,
ask open/high/low/close, sp (mean quoted spread of the minute), n (quotes in the minute).

Usage: python -I tools/build_tick_bars.py [months] [join]
"""
import sys
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
COLS = ["time", "bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "sp", "n"]


def month(f, out):
    with zipfile.ZipFile(f) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as h:
            t = pd.read_csv(h, header=None, names=["t", "bid", "ask", "v"], usecols=[0, 1, 2],
                            dtype={"t": str, "bid": "float64", "ask": "float64"})
    t = t[(t.bid > 0) & (t.ask >= t.bid)]
    # minute of the quote, read straight from the text 'YYYYMMDD HHMMSSfff'
    t["m"] = t.t.str.slice(0, 13)
    t["sp"] = t.ask - t.bid
    g = t.groupby("m", sort=True)
    b = g.agg(bo=("bid", "first"), bh=("bid", "max"), bl=("bid", "min"), bc=("bid", "last"),
              ao=("ask", "first"), ah=("ask", "max"), al=("ask", "min"), ac=("ask", "last"),
              sp=("sp", "mean"), n=("bid", "size"))
    # the file clock is London time minus 5 hours (New York time except in the weeks the two change clocks apart)
    lon = (pd.to_datetime(b.index, format="%Y%m%d %H%M") + pd.Timedelta(hours=5)).tz_localize(
        "Europe/London", ambiguous="NaT", nonexistent="NaT")
    b = b[lon.notna()]
    ny = lon[lon.notna()].tz_convert("America/New_York").tz_localize(None)
    srv = ny + pd.Timedelta(hours=7)
    b.insert(0, "time", (srv - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))
    np.savez_compressed(out, **{c: b[c].to_numpy() for c in COLS})
    return len(t), len(b), float(b.sp.median())


def stage_months():
    out = ROOT / "ticks_m1"
    out.mkdir(exist_ok=True)
    for f in sorted((ROOT / "ticks_raw").glob("XAUUSD_*.zip")):
        o = out / (f.stem + ".npz")
        if o.exists():
            continue
        try:
            nt, nb, sp = month(f, o)
            print(f"{f.stem}: {nt} quotes, {nb} minutes, median spread {sp:.3f}", flush=True)
        except Exception as e:
            print(f"{f.stem}: failed, {e}", flush=True)


def stage_join():
    parts = [np.load(f) for f in sorted((ROOT / "ticks_m1").glob("XAUUSD_*.npz"))]
    d = {c: np.concatenate([p[c] for p in parts]) for c in COLS}
    k = np.argsort(d["time"], kind="stable")
    np.savez_compressed(ROOT / "XAUUSD_BA_M1.npz", **{c: v[k] for c, v in d.items()})
    print(f"XAUUSD_BA_M1.npz: {len(k)} minutes, {pd.to_datetime(d['time'][k[0]], unit='s')} to "
          f"{pd.to_datetime(d['time'][k[-1]], unit='s')} server time", flush=True)


if __name__ == "__main__":
    for s in sys.argv[1:] or ["months", "join"]:
        globals()["stage_" + s]()
