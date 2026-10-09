"""Export XAUUSD.pc history from a running MT5 terminal for research in the cloud sandbox.

Read-only: it only calls copy_rates_range / copy_ticks_range and never sends orders, so
it is safe to run against the live Terminal 14 without closing it.

    python tools\\export_mt5_data.py
    python tools\\export_mt5_data.py --tick-days 30 --years 3

Writes gzip CSVs under marketdata\\ (one file per day for ticks, so each stays far below
GitHub's 100 MB limit). Then: git add marketdata && git commit -m "Add gold history" && git push
"""
import argparse
import csv
import gzip
import os
import sys
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

ap = argparse.ArgumentParser()
ap.add_argument("--terminal", default=r"C:\Program Files\MetaTrader 5 - 14\terminal64.exe")
ap.add_argument("--symbol", default="XAUUSD.pc")
ap.add_argument("--years", type=float, default=3, help="years of M1 bars")
ap.add_argument("--tick-days", type=int, default=20, help="most recent calendar days of ticks")
ap.add_argument("--out", default="marketdata")
args = ap.parse_args()

if not mt5.initialize(path=args.terminal):
    sys.exit(f"initialize failed: {mt5.last_error()}")
if not mt5.symbol_select(args.symbol, True):
    sys.exit(f"symbol {args.symbol} not available: {mt5.last_error()}")
os.makedirs(os.path.join(args.out, "ticks"), exist_ok=True)
now = datetime.now(timezone.utc)

# M1 bars, fetched month by month so no single request is too large.
bars_path = os.path.join(args.out, f"{args.symbol}_M1.csv.gz")
start = now - timedelta(days=365 * args.years)
total = 0
with gzip.open(bars_path, "wt", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "open", "high", "low", "close", "tick_volume", "spread_points"])
    t0 = start
    while t0 < now:
        t1 = min(t0 + timedelta(days=30), now)
        rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M1, t0, t1)
        if rates is not None:
            for r in rates:
                w.writerow([int(r["time"]), r["open"], r["high"], r["low"], r["close"],
                            int(r["tick_volume"]), int(r["spread"])])
            total += len(rates)
        t0 = t1
print(f"M1 bars: {total} rows -> {bars_path} ({os.path.getsize(bars_path) / 1e6:.1f} MB)")

# Ticks, one file per day.
for k in range(args.tick_days, 0, -1):
    d0 = (now - timedelta(days=k)).replace(hour=0, minute=0, second=0, microsecond=0)
    ticks = mt5.copy_ticks_range(args.symbol, d0, d0 + timedelta(days=1), mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        continue
    p = os.path.join(args.out, "ticks", f"{args.symbol}_{d0:%Y-%m-%d}.csv.gz")
    with gzip.open(p, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_msc", "bid", "ask", "flags"])
        for t in ticks:
            w.writerow([int(t["time_msc"]), t["bid"], t["ask"], int(t["flags"])])
    print(f"ticks {d0:%Y-%m-%d}: {len(ticks)} -> {p} ({os.path.getsize(p) / 1e6:.1f} MB)")

info = mt5.symbol_info(args.symbol)
print(f"symbol: digits={info.digits} point={info.point} tick_value={info.trade_tick_value} "
      f"contract={info.trade_contract_size} stops_level={info.trade_stops_level}")
mt5.shutdown()
