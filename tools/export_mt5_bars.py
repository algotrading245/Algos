"""Export the deepest bar history a running MT5 terminal holds, for each timeframe.

Read-only, like export_mt5_data.py. A terminal serves at most "Max bars in chart" bars
per timeframe, so M1 reaches back only a few months while M15 reaches back years.

    python tools\\export_mt5_bars.py --terminal "C:\\Program Files\\MetaTrader 5 - 8\\terminal64.exe"
"""
import argparse
import csv
import gzip
import os
import sys
from datetime import datetime, timezone

import MetaTrader5 as mt5

ap = argparse.ArgumentParser()
ap.add_argument("--terminal", default=r"C:\Program Files\MetaTrader 5 - 14\terminal64.exe")
ap.add_argument("--symbol", default="XAUUSD.pc")
ap.add_argument("--timeframes", default="M5,M15,H1")
ap.add_argument("--out", default="marketdata")
args = ap.parse_args()

if not mt5.initialize(path=args.terminal):
    sys.exit(f"initialize failed: {mt5.last_error()}")
os.makedirs(args.out, exist_ok=True)
for name in args.timeframes.split(","):
    rates = mt5.copy_rates_from_pos(args.symbol, getattr(mt5, f"TIMEFRAME_{name}"), 0, 99999)
    if rates is None or len(rates) == 0:
        print(f"{name}: no data {mt5.last_error()}")
        continue
    path = os.path.join(args.out, f"{args.symbol}_{name}.csv.gz")
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "tick_volume", "spread_points"])
        for r in rates:
            w.writerow([int(r["time"]), r["open"], r["high"], r["low"], r["close"],
                        int(r["tick_volume"]), int(r["spread"])])
    first = datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc)
    print(f"{name}: {len(rates)} bars from {first:%Y-%m-%d} -> {path}")
mt5.shutdown()
