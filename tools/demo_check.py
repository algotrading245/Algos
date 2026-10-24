"""Daily check-in on the demo forward test (pipeline step 17): reads the terminal's experts log and journal for a day
and prints what the Aurum EAs did - orders per leg, failures, skipped trades, day stops, final stops, phase events -
plus the trade lines of the journal.  The monitor agent turns this into an entry in docs/demo_log.md.

    python tools/demo_check.py                       # today, Terminal 16 (the FTMO demo)
    python tools/demo_check.py --day 2026-10-20 --json

Read-only: it opens log files and nothing else.  Lines that could hold the login or an account number (any run of
six or more digits, "login", "authoriz", "account") are dropped before anything is printed or stored.
"""
import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

DATA = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "66FB7F5B174F9C3B2A690C49FF012FEB"
PRIVATE = re.compile(r"\d{6,}|login|authoriz|account", re.I)
LEGS = ("session", "dip", "bell", "Tokyo", "midday", "fast", "grid", "hold", "fix", "stock-fall", "Tokyo-morning",
        "after-holiday", "breakout", "noise")
ALERTS = {
    "day_stop": re.compile(r"closing everything until the firm's next day"),
    "final_stop": re.compile(r"at the final stop|halting"),
    "failed": re.compile(r"failed|retcode|no money|not enough money|invalid stops", re.I),
}
EVENTS = {
    "phase": re.compile(r"phase \d+ started|reached the target|the phase is passed|final stop moves"),
    "skipped": re.compile(r"no .*trade|no breakout|too small for the minimum lot"),
    "clock": re.compile(r"clock", re.I),
}


def read(path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
    return [l for l in text.splitlines() if l.strip() and not PRIVATE.search(l)]


def leg_of(line):
    for leg in sorted(LEGS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(leg)}\b", line):
            return leg
    return "other"


def check(day):
    stamp = day.strftime("%Y%m%d")
    experts = [l for l in read(DATA / "MQL5" / "Logs" / f"{stamp}.log") if "Aurum" in l]
    journal = read(DATA / "logs" / f"{stamp}.log")
    orders = Counter()
    found = {k: [] for k in (*ALERTS, *EVENTS)}
    for l in experts:
        msg = l.split("\t")[-1]
        for k, rx in {**ALERTS, **EVENTS}.items():
            if rx.search(msg):
                found[k].append(msg)
        if re.search(r" (bought|sold|buy|sell) [\d.]+ ", msg) or re.search(r"leg \S+ (buy|sell)", msg):
            orders[leg_of(msg)] += 1
    deals = [l.split("\t")[-1] for l in journal if re.search(r"deal #|order #", l)]
    alert = any(found[k] for k in ALERTS)
    return {"day": day.isoformat(), "alert": alert, "experts_lines": len(experts), "orders_by_leg": dict(orders),
            "journal_trade_lines": len(deals), **{k: v[-10:] for k, v in found.items()},
            "last_lines": [l.split("\t")[-1] for l in experts[-5:]],
            "logs_found": [p.name for p in (DATA / "MQL5" / "Logs" / f"{stamp}.log", DATA / "logs" / f"{stamp}.log")
                           if p.exists()]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=date.fromisoformat, default=date.today())
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = check(a.day)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        print(f"{res['day']}: {'ALERT' if res['alert'] else 'ok'}; logs {res['logs_found'] or 'none'}; "
              f"{res['experts_lines']} EA lines, orders {res['orders_by_leg'] or 'none'}, "
              f"{res['journal_trade_lines']} journal trade lines")
        for k in (*ALERTS, *EVENTS):
            for m in res[k]:
                print(f"  {k}: {m}")
