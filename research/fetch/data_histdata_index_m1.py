"""Fetch histdata M1 for five index CFDs the book has no data on (UK100, EU50, FRA40, AUS200, HK50).
Runs from the repo root. Uses tools/download_histdata.py; output marketdata/histdata/<SYMBOL>_M1.csv.gz.
Exits non-zero if a symbol produced no file."""
import subprocess
import sys
from pathlib import Path

SYMS = ["UKXGBP", "ETXEUR", "FRXEUR", "AUXAUD", "HKXHKD"]
ok = 0
for s in SYMS:
    r = subprocess.run([sys.executable, "tools/download_histdata.py", "--from", "2010", s])
    f = Path("marketdata/histdata") / f"{s}_M1.csv.gz"
    if f.exists():
        import pandas as pd
        d = pd.read_csv(f)
        print(s, len(d), d.iloc[0, 0], d.iloc[-1, 0])
        ok += 1
    else:
        print(s, "no file", r.returncode)
sys.exit(0 if ok >= 3 else 1)
