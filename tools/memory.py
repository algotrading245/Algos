"""Shared memory for the autopilot agents.

    python tools/memory.py brief [--last N]
    python tools/memory.py decide --role R --decision TEXT --why TEXT --evidence TEXT [--kind decision|lesson|question]
    python tools/memory.py search WORDS... [--events] [--limit N]
    python tools/memory.py commands [--role R] [--last N]
    python tools/memory.py check

decisions.jsonl is append-only; lessons.md is curated by the orchestrator; mission.md belongs to the owner.
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(REPO, "docs", "memory")
MISSION = os.path.join(MEM, "mission.md")
LESSONS = os.path.join(MEM, "lessons.md")
DECISIONS = os.path.join(MEM, "decisions.jsonl")
EVENTS = os.path.join(REPO, "logs", "autopilot", "events")
KINDS = ("decision", "lesson", "question")
MAX_LESSONS = 40
# never let a secret into the shared log
SECRET = re.compile(r"(password|passwd|api[_-]?key|token|secret)\s*[:=]|(login|account)\s*[:=#]?\s*\d{5,}", re.I)


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def decisions():
    out = []
    for n, line in enumerate(read(DECISIONS).splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                out.append({"bad_line": n, "raw": line})
    return out


def fmt(d):
    if "bad_line" in d:
        return f"[bad line {d['bad_line']}]"
    return f"{d.get('when', '?')} {d.get('role', '?')} {d.get('kind', '?')}: {d.get('decision', '')} | why: {d.get('why', '')} | evidence: {d.get('evidence', '')}"


def cmd_brief(a):
    print(read(MISSION).strip())
    print("\n" + read(LESSONS).strip())
    print(f"\n# Last {a.last} decisions\n")
    for d in decisions()[-a.last:]:
        print("- " + fmt(d))


def cmd_decide(a):
    text = " ".join([a.decision, a.why, a.evidence])
    if SECRET.search(text):
        sys.exit("refused: the text looks like it holds a credential")
    d = {"when": datetime.now().strftime("%Y-%m-%dT%H:%M"), "role": a.role, "kind": a.kind,
         "decision": a.decision.strip(), "why": a.why.strip(), "evidence": a.evidence.strip()}
    with open(DECISIONS, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print("logged: " + fmt(d))


def text_sources():
    docs = os.path.join(REPO, "docs")
    files = [DECISIONS, LESSONS, MISSION, os.path.join(docs, "HANDOFF.md"),
             os.path.join(docs, "autopilot", "runs.md"), os.path.join(docs, "autopilot", "queue.json"),
             os.path.join(docs, "trials.jsonl"), os.path.join(docs, "candidates.json"),
             os.path.join(docs, "demo_log.md")]
    files += sorted(glob.glob(os.path.join(docs, "ideas", "*.md")))
    files += sorted(glob.glob(os.path.join(docs, "gates", "*")))
    return [f for f in files if os.path.isfile(f)]


def tool_uses(path):
    """Yield (tool name, input as text) and assistant text from one stream-json event log."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") != "assistant":
                continue
            for c in ev.get("message", {}).get("content", []) or []:
                if c.get("type") == "tool_use":
                    yield c.get("name", "?"), json.dumps(c.get("input", {}), ensure_ascii=False)
                elif c.get("type") == "text":
                    yield "text", c.get("text", "")


def event_files(role=None):
    files = sorted(glob.glob(os.path.join(EVENTS, "*.jsonl")))
    if role:
        files = [f for f in files if os.path.basename(f).endswith(f"_{role}.jsonl")]
    return files


def cmd_search(a):
    words = [w.lower() for w in a.words]
    hits = 0
    for path in text_sources():
        rel = os.path.relpath(path, REPO)
        for n, line in enumerate(read(path).splitlines(), 1):
            low = line.lower()
            if all(w in low for w in words):
                print(f"{rel}:{n}: {line.strip()[:300]}")
                hits += 1
                if hits >= a.limit:
                    return
    if a.events:
        for path in event_files():
            run = os.path.basename(path)[:-6]
            for name, body in tool_uses(path):
                low = body.lower()
                if all(w in low for w in words):
                    print(f"[{run}] {name}: {body.strip()[:300]}")
                    hits += 1
                    if hits >= a.limit:
                        return
    if not hits:
        print("no matches")


def cmd_commands(a):
    for path in event_files(a.role)[-a.last:]:
        print(f"## {os.path.basename(path)[:-6]}")
        for name, body in tool_uses(path):
            if name != "text":
                print(f"  {name}: {body[:200]}")


def cmd_check(a):
    problems = []
    items = re.findall(r"^\d+\.\s.*?(?=^\d+\.\s|^#|\Z)", read(LESSONS), re.M | re.S)
    if len(items) > MAX_LESSONS:
        problems.append(f"{len(items)} lessons, limit {MAX_LESSONS}")
    for it in items:
        if "Evidence:" not in it:
            problems.append("no Evidence: " + it.splitlines()[0][:80])
    for d in decisions():
        if "bad_line" in d:
            problems.append(f"decisions.jsonl line {d['bad_line']} is not JSON")
        elif d.get("kind") not in KINDS or not d.get("decision") or not d.get("evidence"):
            problems.append("incomplete decision: " + fmt(d)[:100])
    print(f"{len(items)} lessons, {len(decisions())} decisions")
    for p in problems:
        print("PROBLEM " + p)
    sys.exit(1 if problems else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    b = s.add_parser("brief"); b.add_argument("--last", type=int, default=15); b.set_defaults(f=cmd_brief)
    d = s.add_parser("decide")
    d.add_argument("--role", required=True); d.add_argument("--kind", choices=KINDS, default="decision")
    d.add_argument("--decision", required=True); d.add_argument("--why", required=True)
    d.add_argument("--evidence", required=True); d.set_defaults(f=cmd_decide)
    q = s.add_parser("search"); q.add_argument("words", nargs="+"); q.add_argument("--events", action="store_true")
    q.add_argument("--limit", type=int, default=40); q.set_defaults(f=cmd_search)
    c = s.add_parser("commands"); c.add_argument("--role"); c.add_argument("--last", type=int, default=1)
    c.set_defaults(f=cmd_commands)
    k = s.add_parser("check"); k.set_defaults(f=cmd_check)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
