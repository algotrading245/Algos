"""Spec factory (owner 2026-10-22: "make the free rule tests in step 2 fast"): writes rule specs with no LLM.

The miner's specs come from papers and code it read; this adds a fixed grid on top: every standard daily rule
family the engine knows x every symbol we have x a few market-state filters, with the engine's default parameters
(tools/idea_engine.py RULE_PARAMS), so nothing is tuned here. A second grid follows it: the papers' own parameters
(12-month tsmom, 50/200 and 1/200 MA, RSI-2 at 5, 1-month reversal, 12-month xsmom), turn of the month, and session
opens (Asia, London, NY, US cash open; held 1, 2 or 4 hours) by weekday. When both are used up it logs it once a day.
tools/idea_engine.py calls top_up() before each run: when fewer than BATCH specs are pending it writes the next BATCH,
at most (hour + 1) * PER_HOUR by the end of each hour and DAILY_CAP a day. Every variant the engine tries is logged
as a DSR trial, so the pacing is what keeps the luck bar from rising fast. Families the portfolio manager's
docs/ideas/steer.md lists under "## Stop bringing" are skipped (STOPS), so the grid follows the weekly steer.

    python tools/spec_factory.py            # write the next batch now (same limits)
    python tools/spec_factory.py --list     # how many grid specs are left, write nothing
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "ideas" / "specs"
LOGDIR = ROOT / "logs" / "autopilot"
EXHAUSTED = LOGDIR / "spec-factory-exhausted"                       # date of the last "grids used up" log line
BATCH = 10
DAILY_CAP = 120
PER_HOUR = 5                                                        # pacing: (hour + 1) * 5 by the end of each hour

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


# Second grid, written once the first is used up. One value per parameter, as the paper states it, so each spec is
# one variant. (tag, rule, params, source)
PAPER = [
    ("252", "tsmom", {"lookback": [252]}, "12-month time-series momentum (Moskowitz, Ooi & Pedersen 2012)"),
    ("50_200", "ma_cross", {"fast": [50], "slow": [200]}, "50/200-day crossover (Brock, Lakonishok & LeBaron 1992)"),
    ("1_200", "ma_cross", {"fast": [1], "slow": [200]}, "price vs its 200-day mean (Brock, Lakonishok & LeBaron 1992)"),
    ("2_5", "rsi", {"period": [2], "level": [5]}, "RSI-2 below 5 / above 95 (Connors & Alvarez 2009)"),
    ("21", "reversal", {"lookback": [21]}, "1-month reversal (Jegadeesh 1990)"),
]
TOM = {"month_day": [-1, 1, 2, 3]}                                  # turn of the month (Lakonishok & Smidt 1988)
FILTERS2 = [("", {}), ("tom", TOM), ("vh", {"vol": "high"}), ("vl", {"vol": "low"})]
# Session moves: entry at the session open (New York time), held 1, 2 or 4 hours. The rule engine is daily only, so
# these use the entry/hold form of a spec.
SESSIONS = {"asia": "19:00", "london": "03:00", "ny": "08:00", "usopen": "09:30"}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]


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
    yield from grid2()


def grid2():
    """Paper parameters, turn of the month on the default rules, then session opens by weekday."""
    for suf, when in FILTERS2:
        tag = f"_{suf}" if suf else ""
        for ptag, rule, params, src in PAPER:
            for sym in SYMBOLS:
                yield _spec(f"f2_{rule}{ptag}_{sym.lower()}{tag}", rule, [sym], when, src, params)
        for name, syms in GROUPS.items():
            yield _spec(f"f2_xsmom252_{name}{tag}", "xsmom", syms, when,
                        "12-month cross-sectional momentum (Asness, Moskowitz & Pedersen 2013)", {"lookback": [252]})
    for rule, src in RULES.items():
        for sym in SYMBOLS:
            yield _spec(f"f2_{rule}_{sym.lower()}_tom", rule, [sym], TOM, src + ", turn of the month")
    for day in [None] + WEEKDAYS:
        for sess, hhmm in SESSIONS.items():
            for sym in SYMBOLS:
                sid = f"f2_{sess}_{sym.lower()}" + (f"_{day}" if day else "")
                s = _spec(sid, None, [sym], {"weekday": [day]} if day else {},
                          f"session open drift ({sess} {hhmm} New York)")
                s.update(entry=[hhmm], hold=[2, 4, 8], title=f"{sess} open on {sym}" + (f" on {day}" if day else ""))
                yield s


def _spec(sid, rule, syms, when, src, params=None):
    s = {"id": sid,
         "title": f"{rule} on {'+'.join(syms) if len(syms) < 4 else str(len(syms)) + ' symbols'}"
                  + (f" {json.dumps(params)}" if params else "")
                  + (f" when {', '.join(f'{k} {v}' for k, v in when.items())}" if when else ""),
         "source": f"spec factory grid: {src}, " + ("the paper's parameters" if params else "the engine's defaults"),
         "link": "", "read": "n/a",
         "why": "Standard rule tested on every market we have; the grid is fixed, so nothing is tuned here",
         "symbols": syms, "side": "both", "status": "pending", "made_by": "spec_factory"}
    if rule:
        s["rule"] = rule
    if params:
        s["params"] = params
    if when:
        s["when"] = when
    return s


STEER = ROOT / "docs" / "ideas" / "steer.md"
FX = {"USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "NZD"}
TREND = {"tsmom", "xsmom", "donchian", "ma_cross"}


def _fx(spec):
    return all(len(s) == 6 and s[:3] in FX and s[3:] in FX for s in spec["symbols"])


# What the portfolio manager's "## Stop bringing" list can switch off here (owner 2026-10-24: the factory wrote 15
# batches of f_tsmom_* and xsmom specs the steer had already stopped, all failing). (words in the list, spec test)
STOPS = [
    (("tsmom", "trend"), lambda s: s.get("rule") in TREND),
    (("fx calendar", "time-of-day", "short reversal"),
     lambda s: _fx(s) and (s.get("rule") == "reversal" or "entry" in s or "month_day" in s.get("when", {}))),
]


def stopped():
    """The spec tests that docs/ideas/steer.md's "## Stop bringing" section turns off (re-read each call)."""
    try:
        text = STEER.read_text(encoding="utf-8")
    except OSError:
        return []
    sec = text.split("## Stop bringing", 1)[1].split("\n## ", 1)[0].lower() if "## Stop bringing" in text else ""
    return [test for words, test in STOPS if any(w in sec for w in words)]


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


def allowed_now(now=None):
    """Specs the factory may have made by this hour: PER_HOUR for each hour started, so the cap spreads over the day."""
    now = now or dt.datetime.now()
    return min(DAILY_CAP, (now.hour + 1) * PER_HOUR)


def _log_exhausted():
    """One line a day in the idea engine's log once both grids are used up."""
    LOGDIR.mkdir(parents=True, exist_ok=True)
    d = dt.date.today().isoformat()
    if EXHAUSTED.exists() and EXHAUSTED.read_text(encoding="utf-8").strip() == d:
        return
    EXHAUSTED.write_text(d, encoding="utf-8")
    with open(LOGDIR / f"{d}_idea-engine.log", "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} [spec_factory] both grids used up: no factory specs left; "
                "new specs come from the miner only. Add a grid to tools/spec_factory.py for more.\n")


def top_up(dry=False):
    """Write the next batch when the queue is low. Returns the ids written."""
    ids, keys, pending, today = _existing()
    allowed = allowed_now()
    if pending >= BATCH or today >= allowed:
        return []
    n = min(BATCH, allowed - today)
    out = []
    stops = stopped()
    for s in grid():
        if len(out) >= n:
            break
        if s["id"] in ids or _key(s) in keys:                       # already made, or the miner had the same test
            continue
        if any(t(s) for t in stops):                                # the steer stopped this family
            continue
        s["made"] = dt.date.today().isoformat()
        if not dry:
            (SPECS / f"{s['id']}.json").write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
        out.append(s["id"])
    if not out and not dry:
        _log_exhausted()
    return out


if __name__ == "__main__":
    if "--list" in sys.argv:
        ids, keys, pending, today = _existing()
        stops = stopped()
        new = [s for s in grid() if s["id"] not in ids and _key(s) not in keys]
        left = [s["id"] for s in new if not any(t(s) for t in stops)]
        g1 = sum(1 for _ in grid()) - sum(1 for _ in grid2())
        print(f"grid {g1} + {sum(1 for _ in grid2())}, left {len(left)} ({len(new) - len(left)} more stopped by "
              f"steer.md), next {left[:3]}, pending now {pending}, "
              f"made today {today}, allowed by now {allowed_now()}/{DAILY_CAP}")
    else:
        print(top_up())
