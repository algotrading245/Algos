"""Compare AurumHydra's Strategy Tester runs j6 off, j6 on and j5 (legs on + month-end boost 2, no halt).

Reads the daily balance curves in each run's result.json and prints, per run: growth, the share of the
model's log growth kept (research/hydra_tester_expect.py: off +1184%, on +1574%), the deepest drawdown on the
daily curve with its dates, and each month's return in percent.

    python research/hydra_j6_compare.py
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import parse_report  # noqa: E402
RUNS = {
    "j6 off": ("backtests/2026-10-17_1010_AurumHydra_size1b_off", 11.84),
    "j6 on": ("backtests/2026-10-17_1116_AurumHydra_size1b_on", 15.74),
    "j5 boost": ("backtests/2026-10-17_0825_AurumHydra_size1_on", 15.74),
}


def load(folder):
    res = json.loads((ROOT / folder / "result.json").read_text())
    return res["deposit"], [(d, float(v)) for d, v in res["curve"]]


def main():
    months = {}
    for name, (folder, model) in RUNS.items():
        dep, curve = load(folder)
        end = curve[-1][1]
        kept = math.log(end / dep) / math.log(1 + model)
        peak, pdate, worst, wfrom, wto = dep, curve[0][0], 0.0, "", ""
        for d, v in curve:
            if v > peak:
                peak, pdate = v, d
            dd = 1 - v / peak
            if dd > worst:
                worst, wfrom, wto = dd, pdate, d
        print(f"{name:9s} end {end:11,.0f}  growth {end / dep - 1:+8.1%}  model log growth kept {kept:4.0%}  "
              f"daily-close DD {worst:5.1%} ({wfrom} -> {wto})")
        last = {}
        for d, v in curve:
            last[d[:7]] = v
        prev = dep
        for m in sorted(last):
            months.setdefault(m, {})[name] = last[m] / prev - 1
            prev = last[m]
    print("\nmonth     " + "".join(f"{n:>10s}" for n in RUNS))
    for m in sorted(months):
        print(f"{m}   " + "".join(f"{months[m].get(n, float('nan')):+10.1%}" for n in RUNS))

    # Where the legs-on run's deepest month (2026-01) came from: net by symbol in that month, in % of the
    # month's opening balance, off against on.
    for month in ("2026-01", "2024-07"):
        print(f"\n{month} by symbol, % of the month's opening balance")
        tables = {}
        for name, (folder, _) in RUNS.items():
            deals = deals_of(folder)
            opening = next(d["balance"] - pl(d) for d in deals if d["time"][:7].replace(".", "-") == month)
            net = defaultdict(float)
            for d in deals:
                if d["time"][:7].replace(".", "-") == month and d["symbol"]:
                    net[d["symbol"]] += pl(d)
            tables[name] = {s: v / opening for s, v in net.items()}
        symbols = sorted({s for t in tables.values() for s in t})
        print("symbol    " + "".join(f"{n:>10s}" for n in RUNS))
        for s in symbols:
            print(f"{s:10s}" + "".join(f"{tables[n].get(s, 0.0):+10.2%}" for n in RUNS))


def deals_of(folder):
    report = max((ROOT / folder).glob("*.htm"), key=lambda p: p.stat().st_size)
    text = parse_report.read(report)
    start = text.find(">Deals<")
    deals = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text[start:], re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) == 13 and re.match(r"\d{4}\.\d\d\.\d\d", cells[0]) and cells[3] != "balance":
            deals.append({"time": cells[0], "symbol": cells[2], "commission": parse_report.num(cells[8]) or 0.0,
                          "swap": parse_report.num(cells[9]) or 0.0, "profit": parse_report.num(cells[10]) or 0.0,
                          "balance": parse_report.num(cells[11])})
    return deals


def pl(d):
    return d["profit"] + d["commission"] + d["swap"]


if __name__ == "__main__":
    main()
