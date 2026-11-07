"""Write the FTMO symbol specs (swaps, spread, contract size, digits) to docs/ftmo_specs.json (owner 2026-10-22).

Read-only, like export_mt5_bars.py: it reads symbol properties from a running MT5 terminal and never reads or writes
account fields, orders or positions.  The finder uses the file to know which markets FTMO offers and what carry
(swap) each one pays; the builder uses it for costs.  History: tools/export_mt5_bars.py.

    python tools/export_mt5_specs.py
    python tools/export_mt5_specs.py --terminal "C:\\MetaTrader 5 - Tester\\terminal64.exe"
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["path", "description", "digits", "point", "trade_contract_size", "volume_min", "volume_step", "volume_max",
          "spread", "spread_float", "swap_mode", "swap_long", "swap_short", "swap_rollover3days", "currency_base",
          "currency_profit", "currency_margin", "trade_tick_value", "trade_tick_size", "trade_mode"]
SWAP_MODES = {0: "disabled", 1: "points", 2: "base currency", 3: "margin currency", 4: "deposit currency",
              5: "percent current", 6: "percent open", 7: "reopen current", 8: "reopen bid"}

ap = argparse.ArgumentParser()
ap.add_argument("--terminal", default=r"C:\MetaTrader 5 - Tester\terminal64.exe")
ap.add_argument("--out", default=str(ROOT / "docs" / "ftmo_specs.json"))
a = ap.parse_args()

if not mt5.initialize(path=a.terminal):
    sys.exit(f"initialize failed: {mt5.last_error()}")
try:
    syms = mt5.symbols_get() or []
    out = {}
    for s in syms:
        d = s._asdict()
        row = {k: d.get(k) for k in FIELDS}
        row["swap_mode_name"] = SWAP_MODES.get(row["swap_mode"], str(row["swap_mode"]))
        out[s.name] = row
finally:
    mt5.shutdown()

groups = {}
for name, r in out.items():
    g = (r["path"] or "").split("\\")[0] or "other"
    groups.setdefault(g, []).append(name)
doc = {"when": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "source": "MT5 symbol properties, read-only",
       "about": "spread is in points at export time; swap_long/short are per lot per night in swap_mode units; "
                "swap_rollover3days is the weekday charged triple (0 = Sunday).",
       "groups": {g: sorted(v) for g, v in sorted(groups.items())}, "symbols": dict(sorted(out.items()))}
Path(a.out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
print(f"{len(out)} symbols in {len(groups)} groups -> {a.out}")
for g, v in sorted(groups.items()):
    print(f"  {g}: {len(v)}")
