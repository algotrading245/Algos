"""Model vs reality, measured on fills: pairs each entry the EA made on the FTMO demo (Terminal 16's experts log) with
the entry the Strategy Tester made for the same leg, symbol, side and day, and prints per leg how many entries each
side made, how many paired, the fill gap (demo price minus tester price, in basis points, signed so that positive
means the demo filled worse) and the lot ratio.  Missing and extra entries are the timing/condition gap, the fill gap
is spread plus slippage plus the data feed, the lot ratio is the sizing gap.  Together they are the part of the
tester-vs-reality gap that a backtest cannot show; the tester-vs-Python part is research/tester_fidelity.py's.

    python tools/fill_check.py --tester backtests/<folder> --from 2026-10-19 --to 2026-10-30
    python tools/fill_check.py --tester backtests/<folder> --from 2026-10-19 --json > docs/fidelity/<date>.json

The tester run must cover the same days with the demo's inputs (queue a run with "from"/"to" set to the demo days).
Read-only: it opens log files and the tester folder's summary.txt.  Lines that could hold the login or an account
number are dropped first (demo_check.PRIVATE), and nothing but legs, symbols, prices and lots is printed.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_check import DATA, read  # noqa: E402  (Terminal 16's data folder, private lines dropped)

ROOT = Path(__file__).resolve().parent.parent
FILL = re.compile(r"\b(bought|sold) ([\d.]+) (?:lots )?(?:([A-Z][A-Z0-9.]+) )?(?:lots )?at ([\d.]+)")
STAMP = re.compile(r"(\d{4}\.\d\d\.\d\d) \d\d:\d\d:\d\d\s+Aurum")
# The EAs' entry lines name their leg in different words; first match wins.
LEG = [("noise", re.compile(r"bands")), ("breakout", re.compile(r"broke its range")),
       ("stock-fall", re.compile(r"into the fix")), ("tokyo-morning", re.compile(r"Tokyo morning")),
       ("after-holiday", re.compile(r"after a US holiday")), ("fix", re.compile(r"the fix (bought|sold)")),
       ("leg", re.compile(r"Aurum\w+: (\S+) leg (bought|sold)"))]


def entry(msg, day):
    m = FILL.search(msg)
    if not m:
        return None
    leg = "other"
    for name, rx in LEG:
        hit = rx.search(msg)
        if hit:
            leg = hit.group(1) if name == "leg" else name
            break
    sym = m.group(3)
    if not sym:   # "US100 bought 0.10 lots at" (noise) or "USD/JPY broke its range, bought" (breakout)
        before = re.search(r"Aurum\w+: ([A-Z][A-Z0-9.]+) (bought|sold)", msg)
        sym = before.group(1) if before else ("USDJPY" if "USD/JPY" in msg else "?")
    return {"day": day, "leg": leg, "symbol": sym.split(".")[0], "side": 1 if m.group(1) == "bought" else -1,
            "lots": float(m.group(2)), "price": float(m.group(4))}


def demo_entries(d0, d1):
    out, d = [], d0
    while d <= d1:
        for l in read(DATA / "MQL5" / "Logs" / f"{d:%Y%m%d}.log"):
            e = entry(l.split("\t")[-1], d.isoformat())
            if e:
                out.append(e)
        d += timedelta(days=1)
    return out


def tester_entries(folder, d0, d1):
    f = Path(folder) if Path(folder).is_absolute() else ROOT / folder
    out = []
    for l in read(f / "summary.txt"):
        s = STAMP.search(l)
        if not s:
            continue
        day = s.group(1).replace(".", "-")
        e = entry(l, day)
        if e and d0.isoformat() <= day <= d1.isoformat():
            out.append(e)
    return out


def compare(demo, tester):
    key = lambda e: (e["day"], e["leg"], e["symbol"], e["side"])
    pool = defaultdict(list)
    for e in tester:
        pool[key(e)].append(e)
    legs = defaultdict(lambda: {"demo": 0, "tester": 0, "paired": 0, "gap_bp": [], "lot_ratio": []})
    for e in tester:
        legs[e["leg"]]["tester"] += 1
    for e in demo:
        g = legs[e["leg"]]
        g["demo"] += 1
        if pool[key(e)]:
            t = pool[key(e)].pop(0)
            g["paired"] += 1
            g["gap_bp"].append(1e4 * e["side"] * (e["price"] - t["price"]) / t["price"])
            g["lot_ratio"].append(e["lots"] / t["lots"] if t["lots"] else np.nan)
    rows = {}
    for leg, g in sorted(legs.items()):
        gap = np.array(g["gap_bp"])
        rows[leg] = {"demo": g["demo"], "tester": g["tester"], "paired": g["paired"],
                     "demo_only": g["demo"] - g["paired"], "tester_only": g["tester"] - g["paired"],
                     "gap_bp_median": float(np.median(gap)) if len(gap) else None,
                     "gap_bp_mean": float(gap.mean()) if len(gap) else None,
                     "lot_ratio_median": float(np.nanmedian(g["lot_ratio"])) if g["lot_ratio"] else None}
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tester", required=True, help="backtests/<folder> of a tester run over the demo days")
    ap.add_argument("--from", dest="d0", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="d1", type=date.fromisoformat, default=date.today())
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    demo, tester = demo_entries(a.d0, a.d1), tester_entries(a.tester, a.d0, a.d1)
    rows = compare(demo, tester)
    res = {"from": a.d0.isoformat(), "to": a.d1.isoformat(), "tester": a.tester, "demo_entries": len(demo),
           "tester_entries": len(tester), "legs": rows}
    if a.json:
        print(json.dumps(res, indent=1))
        return
    print(f"{res['from']} to {res['to']}: {len(demo)} demo entries, {len(tester)} tester entries")
    if not demo:
        print("no demo entries in these days yet: nothing to measure (the EAs log 'bought/sold ... at <price>')")
    f = lambda v, p=1: "-" if v is None else f"{v:.{p}f}"
    print(f"{'leg':16}{'demo':>6}{'tester':>8}{'paired':>8}{'demo only':>11}{'tester only':>13}"
          f"{'gap bp med':>12}{'mean':>8}{'lots d/t':>10}")
    for leg, r in rows.items():
        print(f"{leg:16}{r['demo']:>6}{r['tester']:>8}{r['paired']:>8}{r['demo_only']:>11}{r['tester_only']:>13}"
              f"{f(r['gap_bp_median']):>12}{f(r['gap_bp_mean']):>8}{f(r['lot_ratio_median'], 2):>10}")


if __name__ == "__main__":
    main()
