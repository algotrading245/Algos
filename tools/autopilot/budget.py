"""Token budget for the autopilot: what each agent run costs, and whether the week's use leaves room for the runs that
are nice to have (the finder's runs when the queue is empty).

    python tools/autopilot/budget.py record --role builder --provider claude --model sonnet --events <events.jsonl>
    python tools/autopilot/budget.py backfill      # rebuild logs/autopilot/usage.jsonl from every events file
    python tools/autopilot/budget.py status        # JSON: this week's use, fraction of the budget, skip, today by role

run-agent.ps1 calls `record` after every run; relay.ps1 calls `status` and, when "skip" is true, does not start the
finder (unless a data item waits).  The figures come from the "result" line Claude writes at the end of
a stream-json run (total_cost_usd and the token counts); a run with no result line (killed, other provider) counts as
one run at zero cost.  tools/autopilot/budget.json holds the weekly budget (in the same notional dollars Claude
reports), the week's reset (the weekday and hour the plan's weekly limit resets) and the skip threshold.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs" / "autopilot"
EVENTS = LOGS / "events"
USAGE = LOGS / "usage.jsonl"
CONFIG = Path(__file__).with_name("budget.json")
DEFAULTS = {"weekly_usd": 150.0, "reset_weekday": 4, "reset_hour": 18, "skip_above": 0.7}


def config():
    c = dict(DEFAULTS)
    if CONFIG.exists():
        c.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return c


def parse_events(path):
    """Cost and tokens from the last "result" line of one events file (None when the run wrote none)."""
    res = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"result"' not in line.replace(" ", ""):
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") == "result":
                    res = o
    except OSError:
        return None
    if res is None:
        return None
    u = res.get("usage") or {}
    return {"cost_usd": round(float(res.get("total_cost_usd") or 0), 4),
            "input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0),
            "cache_create": int(u.get("cache_creation_input_tokens") or 0),
            "models": sorted((res.get("modelUsage") or {}).keys())}


def from_name(path):
    m = re.match(r"(\d{8}-\d{6})_(.+)\.jsonl$", Path(path).name)
    if not m:
        return None, None
    return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"), m.group(2)


def row(path, role=None, provider=None, model=None):
    ts, name_role = from_name(path)
    r = {"ts": (ts or datetime.now()).isoformat(timespec="seconds"), "role": role or name_role or "?",
         "provider": provider or "claude", "model": model or "", "events": Path(path).name,
         "cost_usd": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_create": 0, "models": []}
    p = parse_events(path)
    if p:
        r.update(p)
    return r


def load():
    if not USAGE.exists():
        return []
    out = []
    for line in USAGE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def week_start(now, c):
    """The latest reset (weekday c["reset_weekday"], Monday = 0, at c["reset_hour"]) at or before now."""
    d = now.replace(hour=c["reset_hour"], minute=0, second=0, microsecond=0)
    d -= timedelta(days=(now.weekday() - c["reset_weekday"]) % 7)
    return d if d <= now else d - timedelta(days=7)


def status(now=None):
    c = config()
    now = now or datetime.now()
    start = week_start(now, c)
    rows = load()
    week = [r for r in rows if datetime.fromisoformat(r["ts"]) >= start]
    today = [r for r in rows if r["ts"][:10] == now.date().isoformat()]
    used = sum(r["cost_usd"] for r in week)
    frac = used / c["weekly_usd"] if c["weekly_usd"] else 0.0
    roles = {}
    for r in today:
        x = roles.setdefault(r["role"], {"runs": 0, "cost_usd": 0.0, "tokens": 0})
        x["runs"] += 1
        x["cost_usd"] = round(x["cost_usd"] + r["cost_usd"], 3)
        x["tokens"] += r["input"] + r["output"] + r["cache_read"] + r["cache_create"]
    days = {}
    for r in week:
        days[r["ts"][:10]] = round(days.get(r["ts"][:10], 0.0) + r["cost_usd"], 3)
    return {"now": now.isoformat(timespec="minutes"), "week_start": start.isoformat(timespec="minutes"),
            "week_runs": len(week), "week_usd": round(used, 2), "weekly_usd": c["weekly_usd"],
            "fraction": round(frac, 3), "skip_above": c["skip_above"], "skip": frac >= c["skip_above"],
            "today": roles, "week_days": days}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--events", required=True)
    rec.add_argument("--role")
    rec.add_argument("--provider")
    rec.add_argument("--model")
    sub.add_parser("backfill")
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "record":
        r = row(a.events, a.role, a.provider, a.model)
        LOGS.mkdir(parents=True, exist_ok=True)
        with USAGE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        print(f"usage: {r['role']} ${r['cost_usd']:.3f} in {r['input']} out {r['output']} cache {r['cache_read']}")
    elif a.cmd == "backfill":
        rows = [row(p) for p in sorted(EVENTS.glob("*.jsonl"))]
        LOGS.mkdir(parents=True, exist_ok=True)
        USAGE.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        print(f"backfill: {len(rows)} runs, ${sum(r['cost_usd'] for r in rows):.2f} in all -> {USAGE}")
    else:
        print(json.dumps(status()))


if __name__ == "__main__":
    sys.exit(main())
