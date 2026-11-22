"""The link between the desk pods and the research loop (owner 2026-11-01), both ways:

- ideas() and gaps(): the finder's open ideas, recent results and the book's gaps, shown in every pod brief, so a pod
  that trades a market the book lacks can say so on the board;
- desk_notes(): what the pods shared and asked in the last week, written to docs/ideas/desk_notes.md, which the
  finder reads beside steer.md (tools/autopilot/prompts/finder.md step 2).

Plain code, no model. Paths are built from paths.ROOT at call time so tests can point it at a temp dir.
"""
import datetime as dt
import json
from collections import Counter

from desk import clocks, memory, paths

WAITING = ("new", "queued", "testing", "tester", "building")
DAYS = 7


def _docs():
    return paths.ROOT / "docs"


def _jsonl(p):
    try:
        return paths.read_jsonl(p)
    except Exception:
        return []


def _since(days=DAYS):
    return (clocks.now() - dt.timedelta(days=days)).date().isoformat()


def ideas(n=8):
    """The finder's queue: what waits to be built, what finished in the last week, and the open leads."""
    q = _jsonl(_docs() / "ideas" / "queue.jsonl")
    since = _since()
    waiting = [{"id": r.get("id"), "title": r.get("title"), "status": r.get("status")}
               for r in q if r.get("status") in WAITING]
    recent = [{"id": r.get("id"), "title": r.get("title"), "status": r.get("status"),
               "result": str(r.get("result") or "")[:200]}
              for r in q if r.get("status") not in WAITING and str(r.get("added", "")) >= since]
    leads = [{"title": r.get("title"), "gap": r.get("gap"), "kind": r.get("kind")}
             for r in _jsonl(_docs() / "ideas" / "backlog.jsonl") if r.get("status") == "open"]
    return {"waiting": waiting[-n:], "recent_results": recent[-n:], "open_leads": leads[-n:]}


def gaps():
    """What the book lacks (docs/gaps.json) and the steer's current status lines (docs/ideas/steer.md)."""
    g = paths.read_json(_docs() / "gaps.json", {}) or {}
    out = {"gaps": g.get("gaps", {}), "aim": g.get("aim"), "when": g.get("when")}
    try:
        lines = (_docs() / "ideas" / "steer.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    status = [ln.lstrip("> ").strip() for ln in lines if ln.startswith(">")]
    out["steer_status"] = " ".join(s for s in status if s)[:900]
    return out


def desk_notes(days=DAYS):
    """Write docs/ideas/desk_notes.md from the last week of desk knowledge and board posts. Returns the path."""
    since = (clocks.now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
    know = [e for e in memory.knowledge() if e.get("share") == "desk" and e.get("t", "") >= since]
    know.sort(key=lambda e: (len(e["endorsed_by"]), e.get("t", "")), reverse=True)
    posts = [r for r in memory.board(500) if r.get("t", "") >= since]
    asks = [r for r in posts if r.get("kind") == "ask"]
    book = [r for r in posts if r.get("pod") == "head-trader"]
    raised = Counter(r.get("instrument") for r in know + posts if r.get("instrument"))

    out = [f"# Desk notes, last {days} days (written {clocks.now().isoformat(timespec='minutes')})", "",
           "What the trading pods shared and asked on the desk (desk/memory/knowledge.jsonl, desk/board.jsonl).",
           "For the finder: a market or pattern the pods keep raising that no leg covers is a lead (source \"desk\").",
           "These are discretionary notes, not tested edges: test them like any other idea.", ""]
    out.append("## Markets raised most")
    out += [f"- {k}: {v}" for k, v in raised.most_common(10)] or ["- (none)"]
    out += ["", "## Knowledge shared (most endorsed first)"]
    out += [f"- {e.get('pod')} {e.get('instrument') or ''} [{len(e['endorsed_by'])} endorsed]: {e.get('text')}"
            for e in know[:20]] or ["- (none)"]
    out += ["", "## Open questions between pods"]
    out += [f"- {r.get('pod')} -> {r.get('to')}: {r.get('text')}" for r in asks[-10:]] or ["- (none)"]
    out += ["", "## Head trader book notes"]
    out += [f"- {r.get('t', '')[:10]}: {r.get('text')}" for r in book[-5:]] or ["- (none)"]
    p = _docs() / "ideas" / "desk_notes.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return p


if __name__ == "__main__":
    print(desk_notes())
    print(json.dumps(ideas(), indent=1)[:1500])
