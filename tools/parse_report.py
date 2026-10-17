"""Reads an MT5 Strategy Tester report (.htm, UTF-16) in a backtests/<run>/ folder and writes result.json next to it:
the report's summary figures, the balance after each closing deal (one point per day), net by year and by month,
and the worst day as a % of that day's starting balance.  The dashboard (tools/dashboard.py) reads result.json.

    python tools/parse_report.py backtests/2026-10-17_0056_AurumBreakout_USDJPY

No account number or login is copied: the report's header lines are not read, only the result table and the deals.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LABELS = {
    "expert": "Expert:", "symbol": "Symbol:", "period": "Period:", "deposit": "Initial Deposit:",
    "net": "Total Net Profit:", "gross_profit": "Gross Profit:", "gross_loss": "Gross Loss:",
    "profit_factor": "Profit Factor:", "recovery": "Recovery Factor:", "sharpe": "Sharpe Ratio:",
    "trades": "Total Trades:", "won": "Profit Trades (% of total):", "eq_dd_max": "Equity Drawdown Maximal:",
    "eq_dd_rel": "Equity Drawdown Relative:", "bal_dd_max": "Balance Drawdown Maximal:", "ticks": "Ticks:",
    "history_quality": "History Quality:",
}


def num(s):
    m = re.search(r"-?[\d ]+(?:\.\d+)?", s.replace(" ", " "))
    return float(m.group(0).replace(" ", "")) if m else None


def read(path):
    raw = path.read_bytes()
    return raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")


def parse(text):
    out = {}
    for key, label in LABELS.items():
        m = re.search(re.escape(label) + r"</td>\s*<td[^>]*><b>([^<]*)</b>", text)
        if m:
            out[key] = m.group(1).strip()
    for key in ("deposit", "net", "gross_profit", "gross_loss", "profit_factor", "recovery", "sharpe", "trades",
                "ticks"):
        if key in out:
            out[key] = num(out[key])
    if "won" in out:
        m = re.search(r"\(([\d.]+)%\)", out["won"])
        out["win_rate"] = float(m.group(1)) if m else None
    for key in ("eq_dd_max", "bal_dd_max"):
        if key in out:
            m = re.search(r"([\d.]+)%", out[key])
            out[key + "_pct"] = float(m.group(1)) if m else None

    deals = []
    start = text.find(">Deals<")
    if start >= 0:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text[start:], re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(cells) == 13 and re.match(r"\d{4}\.\d\d\.\d\d", cells[0]):
                deals.append({"time": cells[0], "symbol": cells[2], "type": cells[3], "dir": cells[4],
                              "commission": num(cells[8]) or 0.0, "swap": num(cells[9]) or 0.0,
                              "profit": num(cells[10]) or 0.0, "balance": num(cells[11]), "comment": cells[12]})
    curve, day_start, by_year, by_month, by_symbol = {}, {}, defaultdict(float), defaultdict(float), defaultdict(float)
    prev = None
    for d in deals:
        day = d["time"][:10].replace(".", "-")
        if d["type"] == "balance":
            prev = d["balance"]
            continue
        if day not in day_start:
            day_start[day] = prev
        pl = d["profit"] + d["commission"] + d["swap"]
        by_year[day[:4]] += pl
        by_month[day[:7]] += pl
        if d["symbol"]:
            by_symbol[d["symbol"]] += pl
        curve[day] = d["balance"]
        prev = d["balance"]
    worst = None
    for day, bal in curve.items():
        s = day_start.get(day)
        if s and s > 0:
            r = (bal / s - 1) * 100
            if worst is None or r < worst[1]:
                worst = (day, r)
    months = list(by_month.values())
    out.update({
        "deals": len(deals),
        "curve": [[d, round(b, 2)] for d, b in curve.items()],
        "by_year": {k: round(v, 2) for k, v in by_year.items()},
        "by_month": {k: round(v, 2) for k, v in by_month.items()},
        "by_symbol": {k: round(v, 2) for k, v in by_symbol.items()},
        "worst_day": {"day": worst[0], "pct": round(worst[1], 2)} if worst else None,
        "months_positive": sum(v > 0 for v in months), "months": len(months),
    })
    if out.get("deposit") and out.get("net") is not None:
        out["return_pct"] = round(out["net"] / out["deposit"] * 100, 2)
    return out


def main(folder):
    folder = Path(folder)
    reports = sorted(folder.glob("*.htm*"), key=lambda p: p.stat().st_size, reverse=True)
    if not reports:
        print(f"no report in {folder}")
        return 1
    res = parse(read(reports[0]))
    res["report"] = reports[0].name
    (folder / "result.json").write_text(json.dumps(res, indent=1))
    keys = ("expert", "symbol", "net", "return_pct", "trades", "win_rate", "profit_factor", "eq_dd_max_pct")
    print(", ".join(f"{k} {res.get(k)}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
