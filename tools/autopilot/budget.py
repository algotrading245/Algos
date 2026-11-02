"""Token budget for the autopilot: what each agent run costs, and whether the week's use leaves room for the runs that
are nice to have (the finder's runs when the queue is empty).

    python tools/autopilot/budget.py record --role builder --provider claude --model sonnet --events <events.jsonl>
    python tools/autopilot/budget.py backfill      # rebuild logs/autopilot/usage.jsonl from every events file
    python tools/autopilot/budget.py status        # JSON: this week's use, fraction of the budget, skip, today by role
                                                   # (week_usd = autopilot_usd + outside_usd: chat and desk sessions)

run-agent.ps1 calls `record` after every run; relay.ps1 calls `status` and, when "skip" is true, does not start the
finder (unless a data item waits).  The figures come from the "result" line Claude writes at the end of
a stream-json run (total_cost_usd and the token counts); a run with no result line (killed, other provider) counts as
one run at zero cost.  tools/autopilot/budget.json holds the weekly budget (in the same notional dollars Claude
reports), the week's reset (the weekday and hour the plan's weekly limit resets) and the skip threshold.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs" / "autopilot"
EVENTS = LOGS / "events"
USAGE = LOGS / "usage.jsonl"
CONFIG = Path(__file__).with_name("budget.json")
DEFAULTS = {"weekly_usd": 150.0, "reset_weekday": 4, "reset_hour": 18, "skip_above": 0.7, "enforce": True}


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


PROJECTS = Path.home() / ".claude" / "projects"
OUTSIDE_CACHE = LOGS / "outside_cache.json"
STATUS = LOGS / "budget_status.json"
WEIGHT = {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_create": 1.25}   # as dashboard_live.Rates
TOK = ("input", "output", "cache_read", "cache_create")
FALLBACK_RATE = 15e-6     # $ per weighted token when usage.jsonl has no run to fit from


def family(model):
    m = (model or "").lower()
    return next((f for f in ("opus", "sonnet", "haiku", "fable") if f in m), "")


def rates(rows):
    """$ per weighted token for each model family, fitted from autopilot runs that used one family only (the same
    fit as dashboard_live.Rates).  "" (an unknown family) takes the dearest rate."""
    cost, tok = {}, {}
    for r in rows:
        fams = {family(m) for m in r.get("models") or []} - {""}
        w = sum(WEIGHT[k] * r.get(k, 0) for k in TOK)
        if len(fams) == 1 and r.get("cost_usd") and w:
            f = fams.pop()
            cost[f] = cost.get(f, 0.0) + r["cost_usd"]
            tok[f] = tok.get(f, 0.0) + w
    out = {f: cost[f] / tok[f] for f in cost}
    out[""] = max(out.values(), default=FALLBACK_RATE)
    return out


def autopilot_sessions():
    """Session ids of the autopilot's own runs (their transcripts are already priced in usage.jsonl)."""
    ids = set()
    for p in EVENTS.glob("*.jsonl"):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for _, line in zip(range(5), f):
                    m = re.search(r'"session_id"\s*:\s*"([^"]+)"', line)
                    if m:
                        ids.add(m.group(1))
                        break
        except OSError:
            pass
    return ids


def _scan(path, entry):
    """Read the new bytes of one transcript into entry["msgs"]: message id -> [ts, family, session, entrypoint,
    input, output, cache_read, cache_create].  A message's later line overwrites its earlier ones (final usage)."""
    msgs = entry.setdefault("msgs", {})
    with open(path, "rb") as f:
        f.seek(entry.get("off", 0))
        data = f.read()
    end = data.rfind(b"\n") + 1            # a half-written last line waits for the next call
    for raw in data[:end].splitlines():
        if b'"usage"' not in raw or b'"assistant"' not in raw:
            continue
        try:
            o = json.loads(raw)
        except ValueError:
            continue
        m = o.get("message") or {}
        u = m.get("usage") or {}
        if o.get("type") != "assistant" or not m.get("id") or not u:
            continue
        msgs[m["id"]] = [o.get("timestamp", ""), family(m.get("model")), o.get("sessionId", ""),
                         o.get("entrypoint", ""), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                         int(u.get("cache_read_input_tokens") or 0), int(u.get("cache_creation_input_tokens") or 0)]
    entry["off"] = entry.get("off", 0) + end


def outside(start, rows, projects=None, cache_path=None, skip_sessions=None):
    """Use outside the autopilot since start (chat sessions, the desk's agents, their subagents): every Claude
    transcript under ~/.claude/projects, less the autopilot's own sessions, priced with rates(rows).  The bytes
    already read are cached per file, so the relay's 5-minute and the dashboard's 30-second calls stay cheap
    (owner 2026-11-02: the throttle only saw the autopilot)."""
    projects = Path(projects or PROJECTS)
    cache_path = Path(cache_path or OUTSIDE_CACHE)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    cut = start.timestamp() - 86400
    fresh = {}
    for dirpath, _, files in os.walk(projects):
        if len(Path(dirpath).relative_to(projects).parts) > 3:
            continue
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_mtime < cut:
                continue
            e = cache.get(p) or {}
            if st.st_size < e.get("off", 0):           # rewritten: read again from the start
                e = {}
            try:
                if st.st_size > e.get("off", 0):
                    _scan(p, e)
            except OSError:
                continue
            fresh[p] = e
    _write_json(cache_path, fresh)
    skip =autopilot_sessions() if skip_sessions is None else skip_sessions
    rate = rates(rows)
    seen, out = set(), {"usd": 0.0, "tokens": 0, "by": {}}
    for e in fresh.values():
        for mid, (ts, fam, sid, entry, *tok) in e.get("msgs", {}).items():
            if mid in seen or sid in skip:
                continue
            seen.add(mid)
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
            except ValueError:
                continue
            if t < start:
                continue
            usd = rate.get(fam, rate[""]) * sum(WEIGHT[k] * n for k, n in zip(TOK, tok))
            who = "chat" if entry == "cli" else "desk/other"
            out["usd"] += usd
            out["tokens"] += sum(tok)
            out["by"][who] = round(out["by"].get(who, 0.0) + usd, 3)
    out["usd"] = round(out["usd"], 2)
    return out


def status(now=None, with_outside=True):
    c = config()
    now = now or datetime.now()
    start = week_start(now, c)
    rows = load()
    week = [r for r in rows if datetime.fromisoformat(r["ts"]) >= start]
    today = [r for r in rows if r["ts"][:10] == now.date().isoformat()]
    auto = sum(r["cost_usd"] for r in week)
    out = outside(start, rows) if with_outside else {"usd": 0.0, "tokens": 0, "by": {}}
    used = auto + out["usd"]
    frac = used / c["weekly_usd"] if c["weekly_usd"] else 0.0
    # The desk's pods own a slice of the week (desk/config.json budgets.pod_weekly_usd; owner 2026-11-02, A7): its
    # unspent part counts as used when the autopilot decides to skip, so the autopilot cannot eat it.
    reserve = desk_reserve_usd()
    left = max(0.0, reserve - float(out["by"].get("desk/other") or 0))
    skip_frac = (used + left) / c["weekly_usd"] if c["weekly_usd"] else 0.0
    roles = {}
    for r in today:
        x = roles.setdefault(r["role"], {"runs": 0, "cost_usd": 0.0, "tokens": 0})
        x["runs"] += 1
        x["cost_usd"] = round(x["cost_usd"] + r["cost_usd"], 3)
        x["tokens"] += r["input"] + r["output"] + r["cache_read"] + r["cache_create"]
    days = {}
    for r in week:
        days[r["ts"][:10]] = round(days.get(r["ts"][:10], 0.0) + r["cost_usd"], 3)
    res = {"now": now.isoformat(timespec="minutes"), "week_start": start.isoformat(timespec="minutes"),
            "week_runs": len(week), "week_usd": round(used, 2), "autopilot_usd": round(auto, 2),
            "outside_usd": out["usd"], "outside_by": out["by"], "weekly_usd": c["weekly_usd"],
            # "enforce": false (owner 2026-11-02, the budget boundary removed): spend is still counted, never skipped
            "fraction": round(frac, 3), "skip_above": c["skip_above"], "enforce": bool(c.get("enforce", True)),
            "skip": bool(c.get("enforce", True)) and skip_frac >= c["skip_above"],
            "desk_reserve_usd": reserve, "desk_reserve_left_usd": round(left, 2), "skip_fraction": round(skip_frac, 3),
            "today": roles, "week_days": days}
    if with_outside:
        _write_json(STATUS, res)      # desk/allowance.py adds the chat share from here (it counts the desk itself)
    return res


def desk_reserve_usd():
    """The pods' weekly dollars from desk/config.json (budgets.pod_weekly_usd), 0 when unset or unreadable."""
    try:
        cfg = json.loads((ROOT / "desk" / "config.json").read_text(encoding="utf-8"))
        return float((cfg.get("budgets") or {}).get("pod_weekly_usd") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0


def _write_json(path, obj):
    """Write whole or not at all (the relay, the dashboard and the desk may call at the same moment)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(obj), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


DESK_JOURNAL = ROOT / "desk" / "journal"


def trend(weeks=4, now=None, journal=None):
    """Tokens and runs per role for this week and the weeks before it, newest first (owner 2026-11-01: item 22).
    Autopilot roles come from usage.jsonl; the desk's agents from its journal's agent_run rows, as "desk:<role>"
    (the desk counts a cache read as 0.1 of a token, desk/runner.py)."""
    c = config()
    now = now or datetime.now()
    starts = [week_start(now, c) - timedelta(days=7 * i) for i in range(weeks)]
    out = [{"week_start": s.isoformat(timespec="minutes"), "roles": {}} for s in starts]

    def add(ts, role, tokens):
        for w, s in zip(out, starts):
            if ts >= s:
                x = w["roles"].setdefault(role, {"runs": 0, "tokens": 0})
                x["runs"] += 1
                x["tokens"] += int(tokens)
                return

    for r in load():
        ts = datetime.fromisoformat(r["ts"])
        if ts <= now:
            add(ts, r["role"], r["input"] + r["output"] + r["cache_read"] + r["cache_create"])
    first = starts[-1].date()
    for p in sorted(Path(journal or DESK_JOURNAL).glob("*.jsonl")):
        try:
            if datetime.fromisoformat(p.stem).date() < first - timedelta(days=1):
                continue
        except ValueError:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("kind") == "agent_run" and j.get("tokens"):
                ts = datetime.fromisoformat(j["t"]).astimezone().replace(tzinfo=None)
                if ts <= now:
                    add(ts, "desk:" + str(j.get("role")), j["tokens"])
    return out


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
    tr = sub.add_parser("trend")
    tr.add_argument("--weeks", type=int, default=4)
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
    elif a.cmd == "trend":
        for w in trend(a.weeks):
            print(w["week_start"], " ".join(f"{k}={v['tokens']:,}/{v['runs']}"
                                            for k, v in sorted(w["roles"].items(), key=lambda x: -x[1]["tokens"])))
    else:
        print(json.dumps(status()))


if __name__ == "__main__":
    sys.exit(main())
