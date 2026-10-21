"""Read-only data for the Aurum Research Control page (tools/research_page.html), served by tools/live_server.py.

Every function here only reads files in the repository; nothing is written, moved or deleted.  Text that looks like a
login, account number, password or key is redacted before it leaves this module, and only files under docs/ plus the
backtests' result.json / summary.md can be fetched by path (logs/ stays local: only derived figures are served).

    python tools/research_api.py          # prints a short self-check of every source
"""
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LOGS = ROOT / "logs" / "autopilot"
EVENTS = LOGS / "events"
AGENTS_DIR = ROOT / ".claude" / "agents"
RUN_AGENT = ROOT / "tools" / "autopilot" / "run-agent.ps1"
MAX_DOC = 400_000

# Redaction: "login: 123", "password=...", "account 12345678".  Narrow on purpose so "no login yet" stays readable.
SECRET_KV = re.compile(r"(?i)\b(login|account|password|passwd|pwd|api[_-]?key|token|secret)\b(\s*(?:no\.?|number|#|id)?\s*[:=]\s*)(\S+)")
SECRET_NUM = re.compile(r"(?i)\b(login|account|acct)(\s+(?:no\.?|number|#|id)?\s*)(\d{5,})")
SCAN_KV = re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+]{6,}")
SCAN_NUM = re.compile(r"(?i)\b(login|account|acct)\s*(?:no\.?|number|#|id)?\s*[:=]?\s*\d{6,}")


def redact(s):
    if not isinstance(s, str):
        return s
    s = SECRET_KV.sub(lambda m: m.group(1) + m.group(2) + "[hidden]", s)
    return SECRET_NUM.sub(lambda m: m.group(1) + m.group(2) + "[hidden]", s)


def scrub(o):
    """Redact every string inside a JSON-like value."""
    if isinstance(o, str):
        return redact(o)
    if isinstance(o, list):
        return [scrub(x) for x in o]
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items()}
    return o


def rtext(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None


def rjson(p, default=None):
    t = rtext(p)
    if t is None:
        return default
    try:
        return json.loads(t)
    except ValueError:
        return default


def jsonl(p):
    out = []
    t = rtext(p)
    if t is None:
        return None
    for i, ln in enumerate(t.splitlines(), 1):
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
            if isinstance(d, dict):
                d["_line"] = i
                out.append(d)
        except ValueError:
            out.append({"bad_line": i})
    return out


def mtime(p):
    try:
        return datetime.fromtimestamp(Path(p).stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def rel(p):
    return Path(p).relative_to(ROOT).as_posix()


# ---------------------------------------------------------------------------------------------------------------- holdout
def holdout_limits():
    """(first holdout day 'YYYY-MM-DD', last month agents may test 'YYYY.MM') from tools/holdout.py."""
    t = rtext(ROOT / "tools" / "holdout.py") or ""
    s = re.search(r'START = pd.Timestamp\("([0-9-]+)"\)', t)
    e = re.search(r'END_MONTH = "([0-9.]+)"', t)
    return (s.group(1) if s else None), (e.group(1) if e else None)


# ----------------------------------------------------------------------------------------------------------------- agents
def frontmatter(p):
    t = rtext(p) or ""
    m = re.match(r"---\s*\n(.*?)\n---", t, re.S)
    out = {}
    for ln in (m.group(1).splitlines() if m else []):
        if ":" in ln:
            k, v = ln.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def run_agent_cfg():
    """role -> ('model'|'agent', value) as tools/autopilot/run-agent.ps1 starts it."""
    t = rtext(RUN_AGENT) or ""
    return {m.group(1): (m.group(2), m.group(3))
            for m in re.finditer(r'(\w+)\s*=\s*@\{\s*Args\s*=\s*@\("--(model|agent)",\s*"([\w-]+)"\)', t)}


def tail_done(path, n=20000):
    try:
        with open(path, "rb") as f:
            f.seek(max(0, path.stat().st_size - n))
            return b'"duration_ms"' in f.read()
    except OSError:
        return False


ROSTER = [  # role, label, agent file, what it writes (from the project brief)
    ("orchestrator", "Orchestrator", None, "queue.json, candidates.json, HANDOFF.md, lessons.md"),
    ("tester", "Tester", "tester-operator", "backtests/<job>, queue.json, runs.md"),
    ("researcher", "Researcher", "researcher", "docs/ideas"),
    ("miner", "Miner", "miner", "docs/ideas/specs, docs/ideas/sources.jsonl"),
    ("scanner", "Scanner", "scanner", "docs/gates"),
    ("fidelity", "Fidelity", "fidelity", "docs/fidelity"),
    ("worker", "Worker", "worker", "research/, mql5/, marketdata/candidates, worker_queue.md, queue.json"),
    ("monitor", "Monitor", "monitor", "docs/demo_log.md"),
    ("reviewer", "Reviewer", "reviewer", "its verdict, recorded by the orchestrator"),
]


def agents():
    cfg = run_agent_cfg()
    now = time.time()
    out = []
    for role, label, afile, writes in ROSTER:
        fm = frontmatter(AGENTS_DIR / f"{afile}.md") if afile else {}
        kind, val = cfg.get(role, (None, None))
        if kind == "model":
            model, source = val, "tools/autopilot/run-agent.ps1"
        elif kind == "agent":
            model, source = frontmatter(AGENTS_DIR / f"{val}.md").get("model"), f".claude/agents/{val}.md"
        else:
            model, source = fm.get("model"), (f".claude/agents/{afile}.md" if afile else None)
        files = sorted(EVENTS.glob(f"*_{role}.jsonl")) if EVENTS.exists() else []
        live = bool(files) and now - files[-1].stat().st_mtime < 20 and not tail_done(files[-1])
        out.append({
            "role": role, "label": label, "model": model, "model_source": source,
            "relay": role in cfg, "kind": "relay run" if role in cfg else "subagent (fresh context)",
            "description": redact(fm.get("description", "")), "writes": writes,
            "last": rjson(LOGS / f"last-{role}.json"), "runs": len(files),
            "latest": files[-1].stem if files else None, "live": live,
        })
    return out


# ------------------------------------------------------------------------------------------------------------------- jobs
def result_summary(folder):
    """Headline figures of one tester run folder, or None."""
    if not folder:
        return None
    d = ROOT / folder.replace("\\", "/")
    r = rjson(d / "result.json")
    out = {"folder": rel(d) if d.exists() else folder.replace("\\", "/"), "exists": d.exists()}
    if (d / "summary.md").exists():
        out["summary"] = rel(d / "summary.md")
        out["months"] = month_rows(rtext(d / "summary.md"))
    if r:
        dep = r.get("deposit") or 0
        ret = r.get("return_pct")
        if ret is None and dep and r.get("net") is not None:
            ret = round(100 * r["net"] / dep, 2)
        out.update({"return_pct": ret, "eq_dd_pct": r.get("eq_dd_max_pct"), "pf": r.get("profit_factor"),
                    "trades": r.get("trades"), "win_rate": r.get("win_rate"), "period": r.get("period"),
                    "sharpe": r.get("sharpe"), "worst_day": r.get("worst_day"), "deposit": dep,
                    "months_positive": r.get("months_positive"), "months_n": r.get("months"),
                    "history_quality": r.get("history_quality"), "has_curve": bool(r.get("curve"))})
    return out


def month_rows(md):
    """'| 2025.01 | 1.67x | 60 | 18.9 |' rows of a months-series summary.md."""
    rows = []
    for m in re.finditer(r"^\|\s*(\d{4}\.\d{2})\s*\|\s*([\d.]+)x\s*\|\s*(\d+)?\s*\|\s*([\d.]+)?", md or "", re.M):
        rows.append({"month": m.group(1), "mult": float(m.group(2)),
                     "trades": int(m.group(3)) if m.group(3) else None,
                     "dd": float(m.group(4)) if m.group(4) else None})
    return rows or None


def month_end(ym):
    y, m = map(int, ym.split("."))
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).isoformat()


def job_window(j, results):
    """(start, end, how) of the data a job covers; end from 'to', 'months.to' or the run's own report."""
    if j.get("months"):
        return j["months"]["from"].replace(".", "-") + "-01", month_end(j["months"]["to"]), "months"
    start = (j.get("from") or "").replace(".", "-") or None
    if j.get("to"):
        return start, j["to"].replace(".", "-"), "to"
    for r in results:
        m = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})", (r or {}).get("period") or "")
        if m:
            return start, m.group(2).replace(".", "-"), "report"
    return start, None, "open"


def folder_time(folder):
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})", folder or "")
    return f"{m.group(1)}T{m.group(2)}:{m.group(3)}" if m else None


def jobs(candidates):
    q = rjson(DOCS / "autopilot" / "queue.json", {}) or {}
    expert_cand = {"AurumBreakout": "breakout", "AurumNoise": "noise"}
    exp_by = {c["id"]: c.get("expected_tester") for c in candidates if c.get("expected_tester")}
    out = []
    for j in q.get("jobs", []):
        res = [result_summary(j.get("folder")), result_summary(j.get("folder_on"))]
        start, end, how = job_window(j, [r for r in res if r])
        exp = None
        cid = expert_cand.get(j.get("expert"))
        if cid and exp_by.get(cid):
            e = exp_by[cid]
            e = e if isinstance(e, list) else [e]
            exp = next((x for x in e if x.get("symbol") == j.get("symbol")), None)
        verdict, vsrc = j.get("verdict"), "queue.json" if j.get("verdict") else None
        if not verdict:  # the candidate ledger records a verdict per tester run folder
            folders = {(r or {}).get("folder") for r in res if r}
            for c in candidates:
                for t in c.get("tester") or []:
                    if t.get("verdict") and str(t.get("run", "")).replace("\\", "/") in folders:
                        verdict, vsrc = t["verdict"], f"candidates.json ({c['id']})"
        out.append(scrub({
            "id": j.get("id"), "status": j.get("status"), "expert": j.get("expert"), "symbol": j.get("symbol"),
            "period": j.get("period"), "preset": j.get("preset"), "deposit": j.get("deposit"),
            "leverage": j.get("leverage"), "tag": j.get("tag"), "set": j.get("set"), "compare_set": j.get("compare_set"),
            "from": j.get("from"), "to": j.get("to"), "months": j.get("months"), "window": [start, end, how],
            "expect": j.get("expect"), "note": j.get("note"), "note_run": j.get("note_run"),
            "verdict": verdict, "verdict_source": vsrc, "needs": j.get("needs"), "candidate": cid,
            "expected": exp, "started": folder_time(j.get("folder")),
            "result": res[0], "result_on": res[1],
        }))
    return {"about": redact(q.get("about")), "jobs": out}


def job_detail(jid):
    data = jobs((rjson(DOCS / "candidates.json", {}) or {}).get("candidates", []))
    j = next((x for x in data["jobs"] if x["id"] == jid), None)
    if not j:
        return None
    for key in ("result", "result_on"):
        r = j.get(key)
        if not r:
            continue
        full = rjson(ROOT / r["folder"] / "result.json") or {}
        curve = full.get("curve") or []
        step = max(1, len(curve) // 300)
        r["curve"] = curve[::step] + (curve[-1:] if curve and (len(curve) - 1) % step else [])
        r["by_month"] = full.get("by_month")
        r["by_symbol"] = full.get("by_symbol")
        if r.get("summary"):
            r["summary_text"] = redact(rtext(ROOT / r["summary"]) or "")[:MAX_DOC]
    return j


# --------------------------------------------------------------------------------------------------------- memory, docs
def lessons():
    t = rtext(DOCS / "memory" / "lessons.md")
    if t is None:
        return None
    items, section = [], None
    for block in re.split(r"(?m)^(?=## |\d+\.\s)", t):
        if block.startswith("## "):
            section = block[3:].splitlines()[0].strip()
            continue
        m = re.match(r"(\d+)\.\s+(.*)", block, re.S)
        if not m or section is None:
            continue
        body = " ".join(m.group(2).split())
        title = re.match(r"\*\*(.+?)\*\*", body)
        ev = re.search(r"Evidence:\s*(.*?)(?:\(\d{4}-\d{2}-\d{2}\)\s*$|$)", body)
        dt = re.findall(r"\((\d{4}-\d{2}-\d{2})\)", body)
        items.append({"n": int(m.group(1)), "section": section, "title": title.group(1) if title else body[:90],
                      "body": redact(body), "evidence": redact(ev.group(1).strip()) if ev else None,
                      "date": dt[-1] if dt else None})
    limit = re.search(r"At most (\d+)", t)
    return {"items": items, "limit": int(limit.group(1)) if limit else None}


def demo_log():
    t = rtext(DOCS / "demo_log.md")
    if t is None:
        return None
    days = []
    for m in re.finditer(r"(?ms)^## (\d{4}-\d{2}-\d{2})([^\n]*)\n(.*?)(?=^## |\Z)", t):
        lines = [redact(x[2:].strip()) for x in m.group(3).splitlines() if x.startswith("- ")]
        eq = None
        for ln in lines:
            e = re.search(r"(?i)\bequity\b[^0-9\-\n]{0,30}(-?\d[\d,]*\.?\d*)", ln)
            if e:
                eq = float(e.group(1).replace(",", ""))
        days.append({"date": m.group(1), "label": m.group(2).strip(" ()"), "lines": lines, "equity": eq})
    return {"days": days, "structured_equity": any(d["equity"] is not None for d in days)}


def doc_list(sub):
    d = DOCS / sub
    out = []
    for p in sorted(d.glob("*")) if d.exists() else []:
        if p.suffix not in (".md", ".json"):
            continue
        title = p.stem
        if p.suffix == ".md":
            h = re.search(r"(?m)^#\s+(.+)", rtext(p) or "")
            title = h.group(1).strip() if h else title
            heads = re.findall(r"(?m)^##\s+(.+)", rtext(p) or "")
        else:
            heads = []
        out.append({"path": rel(p), "title": redact(title), "mtime": mtime(p), "sections": [redact(h) for h in heads][:20]})
    return out


def runs_md():
    t = rtext(DOCS / "autopilot" / "runs.md") or ""
    rows = []
    for ln in t.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 4 and re.match(r"\d{4}-\d{2}-\d{2}", c[0]):
            rows.append({"when": c[0], "agent": c[1], "task": redact(c[2]), "result": redact(c[3])})
    return rows


def trials():
    rows = jsonl(DOCS / "trials.jsonl")
    if rows is None:
        return None
    return {"entries": len(rows), "counted": sum(int(r.get("count") or 1) for r in rows if "bad_line" not in r),
            "latest": scrub(rows[-1]) if rows else None}


# ------------------------------------------------------------------------------------------------------------ rule checks
_ev_cache = {"key": None, "val": None}


def protected_edits():
    """Edit/Write tool calls in the local agent event logs that touched tools/, .claude/ or .gitignore."""
    if not EVENTS.exists():
        return None
    files = sorted(EVENTS.glob("*.jsonl"))
    key = (len(files), max((f.stat().st_mtime for f in files), default=0), sum(f.stat().st_size for f in files))
    if _ev_cache["key"] == key:
        return _ev_cache["val"]
    pat = re.compile(r"(^|[\\/])(tools[\\/]|\.claude[\\/]|\.gitignore$)")
    hits = []
    for f in files:
        try:
            for ln in f.open(encoding="utf-8", errors="replace"):
                if '"tool_use"' not in ln or ('"Edit"' not in ln and '"Write"' not in ln and '"MultiEdit"' not in ln
                                              and '"NotebookEdit"' not in ln):
                    continue
                try:
                    ev = json.loads(ln)
                except ValueError:
                    continue
                for c in ev.get("message", {}).get("content", []) or []:
                    if c.get("type") == "tool_use" and c.get("name") in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        fp = str((c.get("input") or {}).get("file_path") or (c.get("input") or {}).get("notebook_path") or "")
                        tail = re.split(r"(?i)[\\/]Algo[\\/]", fp)[-1]
                        if pat.search(tail):
                            hits.append({"run": f.stem, "tool": c["name"], "path": tail.replace("\\", "/")})
        except OSError:
            continue
    val = {"files": len(files), "hits": hits}
    _ev_cache.update(key=key, val=val)
    return val


def secret_scan():
    paths = [p for p in DOCS.rglob("*") if p.is_file() and p.suffix in (".md", ".json", ".jsonl", ".txt")]
    paths += list((ROOT / "backtests").glob("*/summary.md"))
    hits = []
    for p in paths:
        for i, ln in enumerate((rtext(p) or "").splitlines(), 1):
            if SCAN_KV.search(ln) or SCAN_NUM.search(ln):
                hits.append({"path": rel(p), "line": i})
    return {"files": len(paths), "hits": hits[:50], "count": len(hits)}


def step_num(c):
    try:
        return int(str(c.get("step")).split("-")[0])
    except (TypeError, ValueError):
        return None


def rules(cands, jobs_list, approvals):
    start, end_month = holdout_limits()
    end_day = month_end(end_month) if end_month else None
    out = []

    def gate_check(gname, gstep, rid, title, detail):
        rows, bad = [], []
        for c in cands:
            n = step_num(c)
            verdict = str((c.get("gates") or {}).get("verdict") or "")
            if c.get("status") == "rejected" or verdict.upper().startswith("FAIL") or n is None or n <= gstep:
                continue  # stopped candidates are not past the gate
            g = next((x for x in ((c.get("gates") or {}).get("gates") or []) if x.get("gate") == gname), None)
            rows.append(c["id"])
            if not g or not g.get("pass"):
                bad.append(f"{c['id']} (step {n}): {'no ' + gname + ' gate recorded' if not g else 'failed ' + gname}")
        st = "violated" if bad else ("verified" if rows else "not_checked")
        ev = bad or ([f"{len(rows)} candidate(s) past step {gstep} all pass the {gname} gate: {', '.join(rows)}"] if rows
                     else ["No active candidate past this gate yet."])
        out.append({"id": rid, "title": title, "detail": detail, "status": st, "evidence": ev,
                    "source": "docs/candidates.json (gates field, written by tools/gates.py)"})

    gate_check("costs", 7, "costs", "Real costs (spread + commission)",
               "Survives realistic costs, re-checked at 1.5x cost (gate at step 7).")
    gate_check("halves", 8, "halves", "Both halves of the data",
               "Makes money to 2017 and from 2018 on (gate at step 8).")

    def window_check(rid, title, detail, limit, why):
        open_bad, hist = [], []
        unknown = []
        for j in jobs_list:
            s, e, how = j["window"]
            if e is None:
                (unknown if j["status"] in ("queued", "running") else hist).append(f"{j['id']}: no end date recorded")
                continue
            if limit and e >= limit:
                msg = f"{j['id']} ({j['status']}): data to {e}" + (" (from the report)" if how == "report" else "")
                (open_bad if j["status"] in ("queued", "running") else hist).append(msg)
        st = "violated" if open_bad else ("unknown" if unknown or not limit else "verified")
        ev = open_bad + unknown or [f"No queued or running job reaches {limit}."]
        out.append({"id": rid, "title": title, "detail": detail, "status": st, "evidence": ev, "history": hist,
                    "history_note": why, "source": "docs/autopilot/queue.json, backtests/*/result.json, tools/holdout.py"})

    window_check("holdout", "Holdout data untouched",
                 f"Every day from {start or '?'} on stays unseen by agent jobs.", start,
                 "Finished or failed jobs whose data window reached the holdout. Shown for review, not judged here.")
    window_check("tester_end", "Tester jobs end by " + (end_day or "?"),
                 f"Agent jobs end by the last day of {end_month or '?'}.",
                 (date.fromisoformat(end_day) + timedelta(days=1)).isoformat() if end_day else None,
                 "Finished or failed jobs that ended after the limit (or ran to the run date).")
    out.append({"id": "no_tune", "title": "No tuning on j8b, j8c or j9", "status": "not_checked",
                "detail": "Agents never fit settings to those months.",
                "evidence": ["Cannot be verified from files; the decision log records 'not tuned on those months'."],
                "source": "docs/memory/mission.md, docs/memory/decisions.jsonl"})
    dl = demo_log() or {"days": []}
    out.append({"id": "clean_demo", "title": "Clean test: FTMO demo from 2026-10-19", "status": "not_checked",
                "detail": "The forward test on the FTMO demo is the clean test.",
                "evidence": [f"Demo log has {len(dl['days'])} day(s), latest {dl['days'][-1]['date'] if dl['days'] else 'none'}."
                             " Whether the clean window has started is not checked automatically."],
                "source": "docs/demo_log.md"})
    a2 = next((a for a in approvals if a.get("id") == "a2"), None)
    if a2 is None:
        st, ev = "unknown", ["No approval a2 found in docs/autopilot/approvals.json."]
    elif a2.get("status") == "pending":
        st, ev = "verified", ["a2 (step 19, buy or go live) is pending: no live step is approved."]
    else:
        st, ev = "unknown", [f"a2 status is '{a2.get('status')}'. This page never changes it; check with the owner."]
    out.append({"id": "live", "title": "Live trading blocked (owner only, a2)", "status": st,
                "detail": "Step 19 belongs to the owner; approvals.json gates every owner step.", "evidence": ev,
                "source": "docs/autopilot/approvals.json"})
    sc = secret_scan()
    out.append({"id": "secrets", "title": "No secrets in docs or summaries",
                "status": "violated" if sc["count"] else "verified",
                "detail": "No account number, login or key in any file, log or page.",
                "evidence": ([f"{h['path']} line {h['line']} looks like a credential" for h in sc["hits"]] if sc["count"]
                             else [f"Pattern scan of {sc['files']} files under docs/ and backtests/*/summary.md: nothing found."
                                   " A pattern scan is a check, not a guarantee."]),
                "source": "docs/**, backtests/*/summary.md"})
    pe = protected_edits()
    if pe is None:
        out.append({"id": "lanes", "title": "Agents stay in their lane", "status": "unknown",
                    "detail": "Never edit tools/, .claude/ or .gitignore.",
                    "evidence": ["Local event logs (logs/autopilot/events) not found on this machine."],
                    "source": "logs/autopilot/events/*.jsonl"})
    else:
        out.append({"id": "lanes", "title": "Agents stay in their lane",
                    "status": "violated" if pe["hits"] else "verified",
                    "detail": "Never edit tools/, .claude/ or .gitignore.",
                    "evidence": ([f"{h['run']}: {h['tool']} {h['path']}" for h in pe["hits"][:20]] if pe["hits"] else
                                 [f"No Edit/Write call on a protected path in {pe['files']} agent run logs."
                                  " Shell commands are not inspected."]),
                    "source": "logs/autopilot/events/*.jsonl (local only)"})
    out.append({"id": "legs_off", "title": "New legs ship off", "status": "not_checked",
                "detail": "Every new strategy leg is off by default until the reviewer passes it.",
                "evidence": ["Defaults live in mql5/Include/Aurum/Inputs.mqh and each EA's #defines; not parsed here."],
                "source": "mql5/Include/Aurum/Inputs.mqh"})
    return out


# ------------------------------------------------------------------------------------------------------------- aggregate
SOURCES = ["docs/pipeline.json", "docs/candidates.json", "docs/autopilot/queue.json", "docs/autopilot/runs.md",
           "docs/autopilot/approvals.json", "docs/prop_routes.json", "docs/demo_log.md", "docs/trials.jsonl",
           "docs/memory/decisions.jsonl", "docs/memory/lessons.md", "docs/memory/mission.md",
           "logs/autopilot/relay.json"]
_cache = {"t": 0, "val": None}


def research(max_age=3.0):
    now = time.time()
    if _cache["val"] and now - _cache["t"] < max_age:
        return _cache["val"]
    cj = rjson(DOCS / "candidates.json", {}) or {}
    cands = scrub(cj.get("candidates", []))
    jb = jobs(cands)
    appr = scrub((rjson(DOCS / "autopilot" / "approvals.json", {}) or {}).get("items", []))
    decs = jsonl(DOCS / "memory" / "decisions.jsonl")
    start, end_month = holdout_limits()
    val = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "sources": {s: {"exists": (ROOT / s).exists(), "mtime": mtime(ROOT / s)} for s in SOURCES},
        "holdout": {"start": start, "end_month": end_month},
        "pipeline": rjson(DOCS / "pipeline.json"),
        "candidates": cands, "rejected_families": scrub(cj.get("rejected", [])),
        "jobs": jb["jobs"], "queue_about": jb["about"],
        "approvals": appr,
        "prop_routes": scrub(rjson(DOCS / "prop_routes.json")),
        "decisions": scrub(list(reversed(decs))) if decs is not None else None,
        "lessons": lessons(),
        "mission": redact(rtext(DOCS / "memory" / "mission.md")),
        "demo": demo_log(),
        "trials": trials(),
        "runs": runs_md()[-60:],
        "docs": {"ideas": doc_list("ideas"), "gates": doc_list("gates"), "fidelity": doc_list("fidelity")},
        "agents": agents(),
        "relay": scrub(rjson(LOGS / "relay.json")),
        "local_logs": LOGS.exists(),
    }
    val["rules"] = rules(cands, jb["jobs"], appr)
    _cache.update(t=now, val=val)
    return val


ALLOWED_DOC = re.compile(r"^(docs/[\w./-]+\.(md|json|jsonl|txt)|backtests/[\w.-]+/(summary\.md|result\.json))$")


def doc(path):
    """Text of one allowed file (docs/**, backtests/*/summary.md|result.json), redacted; None when not allowed."""
    path = (path or "").replace("\\", "/").lstrip("/")
    if ".." in path.split("/") or not ALLOWED_DOC.match(path):
        return None
    p = (ROOT / path).resolve()
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        return None
    t = rtext(p)
    if t is None:
        return {"path": path, "missing": True}
    return {"path": path, "mtime": mtime(p), "text": redact(t[:MAX_DOC]), "truncated": len(t) > MAX_DOC}


if __name__ == "__main__":
    r = research()
    for k, v in r["sources"].items():
        print(f"{'ok ' if v['exists'] else 'MISSING'} {k} {v['mtime'] or ''}")
    print(f"{len(r['candidates'])} candidates, {len(r['jobs'])} jobs, {len(r['decisions'] or [])} decisions, "
          f"{len((r['lessons'] or {}).get('items', []))} lessons, {len(r['agents'])} agent roles")
    for x in r["rules"]:
        print(f"rule {x['id']:<11} {x['status']:<12} {x['evidence'][0][:100]}")
