"""Export FTMO M1 bars with spread (points) for the fix/cross/after instruments. Read-only.
Writes marketdata/ftmo_spread/<symbol>_M1.csv.gz. Run from the repo root.
Tries the installed MT5 terminals until one initialises; exits non-zero if no symbol gives rows."""
import csv
import glob
import gzip
import os
import sys
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

SYMS = ["XAUUSD", "USDJPY", "EURUSD", "AUDCAD", "GBPUSD", "AUDUSD", "EURJPY", "GBPJPY",
        "AUDJPY", "CADJPY", "US500.cash", "US100.cash"]
YEARS = 8
OUT = os.path.join("marketdata", "ftmo_spread")
os.makedirs(OUT, exist_ok=True)

paths = sorted(glob.glob(r"C:\Program Files\MetaTrader 5*\terminal64.exe"))
ok = False
for p in paths:
    if mt5.initialize(path=p):
        print("terminal:", os.path.basename(os.path.dirname(p)))
        ok = True
        break
if not ok:
    sys.exit(f"no terminal initialised: {mt5.last_error()}")

now = datetime.now(timezone.utc)
end = min(now, datetime(2025, 10, 12, tzinfo=timezone.utc))  # holdout: nothing after 2025-10-12
start = end - timedelta(days=365 * YEARS)
grand = 0
for s in SYMS:
    if not mt5.symbol_select(s, True):
        print("skip", s, mt5.last_error())
        continue
    path = os.path.join(OUT, f"{s}_M1.csv.gz")
    n = 0
    first = last = None
    with gzip.open(path, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "tick_volume", "spread_points"])
        t0 = start
        while t0 < end:
            t1 = min(t0 + timedelta(days=30), end)
            rates = mt5.copy_rates_range(s, mt5.TIMEFRAME_M1, t0, t1)
            if rates is not None:
                for r in rates:
                    w.writerow([int(r["time"]), r["open"], r["high"], r["low"], r["close"],
                                int(r["tick_volume"]), int(r["spread"])])
                    if first is None:
                        first = int(r["time"])
                    last = int(r["time"])
                n += len(rates)
            t0 = t1
    grand += n
    rng = (datetime.fromtimestamp(first, timezone.utc).date(), datetime.fromtimestamp(last, timezone.utc).date()) if n else None
    print(f"{s}: {n} rows {rng}")
mt5.shutdown()
print("total rows", grand)
sys.exit(0 if grand > 0 else 1)
