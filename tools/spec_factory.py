"""Spec factory (owner 2026-10-22: "make the free rule tests in step 2 fast"): writes rule specs with no LLM.

The miner's specs come from papers and code it read; this adds a fixed grid on top: every standard daily rule
family the engine knows x every symbol we have x a few market-state filters, with the engine's default parameters
(tools/idea_engine.py RULE_PARAMS), so nothing is tuned here. tools/idea_engine.py calls top_up() before each run:
when fewer than BATCH specs are pending it writes the next BATCH from the grid, at most DAILY_CAP a day.
Every variant the engine tries is logged as a DSR trial, so the cap is what keeps the luck bar from rising fast.

    python tools/spec_factory.py            # write the next batch now (same limits)
    python tools/spec_factory.py --list     # how many grid specs are left, write nothing
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "ideas" / "specs"
BATCH = 10
DAILY_CAP = 120

FTMO = ["XAUUSD", "USDJPY", "EURUSD", "AUDCAD", "SPXUSD"]          # the funded EA's markets go first
OTHER = ["GBPUSD", "XAGUSD", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
         "EURGBP", "EURCHF", "EURAUD", "GBPCHF", "AUDNZD", "NZDCAD", "GRXEUR", "JPXJPY", "WTIUSD"]
SYMBOLS = FTMO + OTHER
GROUPS = {                                                          # cross-sectional momentum baskets
    "majors": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"],
    "yen": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY"],
    "assets": ["XAUUSD", "XAGUSD", "SPXUSD", "GRXEUR", "JPXJPY", "WTIUSD"],
    "all": SYMBOLS,
}
RULES = {                                                           # family -> where the rule is from
    "tsmom": "time-series momentum (Moskowitz, Ooi & Pedersen 2012)",
    "donchian": "Donchian channel breakout (Turtle rules)",
    "ma_cross": "moving-average crossover (Brock, Lakonishok & LeBaron 1992)",
    "meanrev": "z-score mean reversion",
    "rsi": "RSI extremes (Wilder 1978; Connors RSI-2)",
    "reversal": "short-term reversal (Jegadeesh 1990)",
}
FILTERS = [                                                         # (suffix, when): plain first
    ("", {}),
    ("vh", {"vol": "high"}),
    ("vl", {"vol": "low"}),
    ("tu", {"trend": "up"}),
    ("td", {"trend": "down"}),
]


def grid():
    """Every factory spec in the order it is written: filter, then rule, then symbol (FTMO markets first)."""
    for suf, when in FILTERS:
        tag = f"_{suf}" if suf else ""
        for rule, src in RULES.items():
            for sym in SYMBOLS:
                yield _spec(f"f_{rule}_{sym.lower()}{tag}", rule, [sym], when, src)
        for name, syms in GROUPS.items():
            if not when.get("trend"):                               # a basket has no single trend
                yield _spec(f"f_xsmom_{name}{tag}", "xsmom", syms, when,
                            "cross-sectional momentum (Menkhoff, Sarno, Schmeling & Schrimpf 2012)")


def _spec(sid, rule, syms, when, src):
    s = {"id": sid,
         "title": f"{rule} on {'+'.join(syms) if len(syms) < 4 else str(len(syms)) + ' symbols'}"
                  + (f" when {', '.join(f'{k} {v}' for k, v in when.items())}" if when else ""),
         "source": f"spec factory grid: {src}, the engine's default parameters",
         "link": "", "read": "n/a",
         "why": "Standard rule tested on every market we have; the grid is fixed, so nothing is tuned here",
         "rule": rule, "symbols": syms, "side": "both", "status": "pending", "made_by": "spec_factory"}
    if when:
        s["when"] = when
    return s


def _key(spec):
    keep = ("rule", "params", "symbols", "entry", "hold", "side", "when")
    return json.dumps({k: spec.get(k) for k in keep}, sort_keys=True)


def _existing():
    ids, keys, pending, today = set(), set(), 0, 0
    d = dt.date.today().isoformat()
    for p in SPECS.glob("*.json"):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(s, dict):
            continue
        ids.add(p.stem)
        keys.add(_key(s))
        pending += s.get("status", "pending") == "pending"
        today += s.get("made_by") == "spec_factory" and s.get("made") == d
    return ids, keys, pending, today


def top_up(dry=False):
    """Write the next batch when the queue is low. Returns the ids written."""
    ids, keys, pending, today = _existing()
    if pending >= BATCH or today >= DAILY_CAP:
        return []
    n = min(BATCH, DAILY_CAP - today)
    out = []
    for s in grid():
        if len(out) >= n:
            break
        if s["id"] in ids or _key(s) in keys:                       # already made, or the miner had the same test
            continue
        s["made"] = dt.date.today().isoformat()
        if not dry:
            (SPECS / f"{s['id']}.json").write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
        out.append(s["id"])
    return out


if __name__ == "__main__":
    if "--list" in sys.argv:
        ids, keys, pending, today = _existing()
        left = [s["id"] for s in grid() if s["id"] not in ids and _key(s) not in keys]
        print(f"grid {sum(1 for _ in grid())}, left {len(left)}, pending now {pending}, made today {today}/{DAILY_CAP}")
    else:
        print(top_up())
