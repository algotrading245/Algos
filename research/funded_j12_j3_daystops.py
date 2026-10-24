"""Why j12 (AurumFunded on the shared leg library) hit 3 day stops that j3 legs on (v1.00) did not.

j12's summary lists three extra day stops: 2024-05-01, 2024-08-05, 2025-02-28. This reads both runs' deal lists and
prints, for each of those days (and the five shared ones as a control), the closed P&L by symbol and by the EA's
deal comment (the leg tag), in % of the balance at the day's first deal, plus each run's lots on that day.

It ends with the implied margin leverage of every 23:00 XAUUSD (bell) entry, lots x price x 100 / (50% of the
balance): RiskLots clips an order to InpMarginPct 50 of the free margin, so where a run's bell entries pile up is the
gold margin its terminal charged. j3 ran on Terminal 16, j12 on the tester install, both with Leverage=33.

    python research/funded_j12_j3_daystops.py
"""
import statistics
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import parse_report  # noqa: E402

RUNS = {
    "j3 on": "backtests/2026-10-17_0535_AurumFunded_funded_on",
    "j12": "backtests/2026-10-18_0155_AurumFunded_funded_lib",
}
EXTRA = ["2024.05.01", "2024.08.05", "2025.02.28"]
SHARED = ["2024.07.25", "2024.11.06", "2025.05.01", "2025.05.30", "2025.10.03"]


def deals_of(folder):
    report = max((ROOT / folder).glob("*.htm"), key=lambda p: p.stat().st_size)
    text = parse_report.read(report)
    start = text.find(">Deals<")
    deals = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text[start:], re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) == 13 and re.match(r"\d{4}\.\d\d\.\d\d", cells[0]) and cells[3] != "balance":
            deals.append({"time": cells[0], "symbol": cells[2], "type": cells[3], "dir": cells[4],
                          "volume": parse_report.num(cells[5]) or 0.0, "price": parse_report.num(cells[6]) or 0.0,
                          "pl": (parse_report.num(cells[8]) or 0.0) + (parse_report.num(cells[9]) or 0.0)
                          + (parse_report.num(cells[10]) or 0.0),
                          "balance": parse_report.num(cells[11]), "comment": cells[12]})
    return deals


def tag(comment):
    """The leg part of a deal comment: drop numbers and stop-out details, keep the words."""
    words = re.sub(r"[\d.%\[\]]+", " ", comment).split()
    return " ".join(words[:2]) or "-"


def day_table(deals, day):
    rows = [d for d in deals if d["time"][:10] == day]
    if not rows:
        return None, {}, []
    opening = rows[0]["balance"] - rows[0]["pl"]
    net = defaultdict(float)
    for d in rows:
        if d["dir"] in ("out", "in/out", "out by"):
            net[(d["symbol"], tag(d["comment"]))] += d["pl"]
    entries = [(d["time"][11:16], d["symbol"], d["type"], d["volume"], d["comment"]) for d in rows if d["dir"] == "in"]
    return opening, net, entries


def main():
    data = {name: deals_of(folder) for name, folder in RUNS.items()}
    for day in EXTRA + SHARED:
        print(f"\n=== {day} ({'extra j12 stop' if day in EXTRA else 'stop in both'})")
        tables = {}
        for name, deals in data.items():
            opening, net, entries = day_table(deals, day)
            if opening is None:
                print(f"  {name}: no deals")
                continue
            total = sum(net.values())
            print(f"  {name}: day-open balance {opening:,.2f}, closed P&L {total:+,.2f} ({total / opening:+.2%})")
            tables[name] = {k: v / opening for k, v in net.items()}
            for t, s, ty, v, c in entries:
                print(f"      in  {t} {s:10s} {ty:4s} {v:6.2f}  {c}")
        keys = sorted({k for t in tables.values() for k in t}, key=lambda k: min(t.get(k, 0) for t in tables.values()))
        print("  symbol      leg                 " + "".join(f"{n:>9s}" for n in RUNS))
        for k in keys:
            print(f"  {k[0]:11s} {k[1][:19]:19s} " + "".join(f"{tables.get(n, {}).get(k, 0.0):+9.2%}" for n in RUNS))

    print("\n=== bell entries (XAUUSD in at 23:00): implied margin leverage lots x price x 100 / (0.5 x balance)")
    for name, deals in data.items():
        lev = [d["volume"] * d["price"] * 100 / (0.5 * d["balance"]) for d in deals
               if d["symbol"] == "XAUUSD" and d["dir"] == "in" and d["time"][11:16] == "23:00"]
        q = statistics.quantiles(lev, n=10)
        print(f"  {name:6s} {len(lev):3d} entries  p10 {q[0]:5.1f}  median {statistics.median(lev):5.1f}  "
              f"p90 {q[-1]:5.1f}  max {max(lev):5.1f}")


if __name__ == "__main__":
    main()
