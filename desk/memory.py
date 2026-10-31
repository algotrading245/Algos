"""The desk's shared memory (DESIGN.md sections 9-10): the board, lessons, similar past setups and calibration.

board.jsonl      pods post what they see and cite each other; a cite on a winning ticket splits the credit. A post
                 with kind "ask" is a question to one pod (or "all"); a "reply" answers one ask (owner 2026-10-31)
lessons.jsonl    the debrief's lessons, one per row {t, pod, lesson, ticket}
knowledge.jsonl  what a pod learned and shares with the desk {t, id, pod, text, instrument, share}, and the other
                 pods' endorsements of it {t, kind: "endorse", id, pod}
All are append-only, like the journal.
"""
import datetime as dt
import os
import uuid
from pathlib import Path

from desk import clocks, journal, paths, tickets

BOARD = Path(os.environ.get("AURUM_DESK_BOARD", paths.DESK / "board.jsonl"))
LESSONS = paths.MEMORY / "lessons.jsonl"
KNOWLEDGE = paths.MEMORY / "knowledge.jsonl"
ASK_DAYS = 3  # an ask older than this is no longer open


def post(pod, text, instrument=None, cites=None, kind=None, to=None, reply_to=None):
    row = {"t": clocks.now().isoformat(timespec="seconds"), "id": "b" + uuid.uuid4().hex[:8], "pod": pod,
           "text": text, "instrument": instrument, "cites": cites or []}
    row.update({k: v for k, v in (("kind", kind), ("to", to), ("reply_to", reply_to)) if v})
    paths.append_jsonl(BOARD, row)
    journal.log("board_post", id=row["id"], pod=pod, instrument=instrument, **({"post": kind, "to": to} if kind else {}))
    return row


def board(n=30, pod=None):
    rows = [r for r in paths.read_jsonl(BOARD) if pod in (None, r.get("pod"))]
    return rows[-n:]


# ---- pods talk: asks and replies ---------------------------------------------------------------------------------

def _recent(rows, days):
    since = (clocks.now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
    return [r for r in rows if r.get("t", "") >= since]


def ask(pod, to, text, instrument=None):
    """A question to one pod, or to "all"; it shows in that pod's brief until answered or ASK_DAYS old."""
    if to == pod:
        raise ValueError("a pod does not ask itself")
    return post(pod, text, instrument, kind="ask", to=to)


def reply(pod, ask_id, text):
    q = next((r for r in paths.read_jsonl(BOARD) if r.get("id") == ask_id and r.get("kind") == "ask"), None)
    if q is None:
        raise ValueError(f"no ask {ask_id}")
    if q.get("pod") == pod:
        raise ValueError("a pod does not answer its own ask")
    return post(pod, text, q.get("instrument"), kind="reply", to=q.get("pod"), reply_to=ask_id)


def open_asks(pod, days=ASK_DAYS):
    """Asks to this pod (or to all) it has not answered; an ask to all closes once any pod answers it."""
    rows = paths.read_jsonl(BOARD)
    by = {}
    for r in rows:
        if r.get("kind") == "reply":
            by.setdefault(r.get("reply_to"), set()).add(r.get("pod"))
    return [r for r in _recent(rows, days) if r.get("kind") == "ask" and r.get("pod") != pod
            and ((r.get("to") == pod and pod not in by.get(r["id"], ()))
                 or (r.get("to") == "all" and not by.get(r["id"])))]


def replies_for(pod, days=ASK_DAYS):
    """The replies to this pod's asks, each with the question it answers."""
    rows = paths.read_jsonl(BOARD)
    mine = {r["id"]: r for r in rows if r.get("kind") == "ask" and r.get("pod") == pod}
    return [{"ask": mine[r["reply_to"]]["text"], "from": r.get("pod"), "reply": r.get("text"), "id": r.get("id"),
             "instrument": r.get("instrument")}
            for r in _recent(rows, days) if r.get("kind") == "reply" and r.get("reply_to") in mine]


def talk(n=40):
    """The latest asks and replies on the board, for the dashboards."""
    return [r for r in paths.read_jsonl(BOARD) if r.get("kind") in ("ask", "reply")][-n:]


# ---- pods share knowledge ----------------------------------------------------------------------------------------

def learn(pod, text, instrument=None, share="desk"):
    """Something a pod learned: share "desk" puts it in every other pod's brief, "pod" keeps it to itself."""
    if share not in ("desk", "pod"):
        raise ValueError("share is desk or pod")
    row = {"t": clocks.now().isoformat(timespec="seconds"), "id": "k" + uuid.uuid4().hex[:8], "pod": pod,
           "text": text, "instrument": instrument, "share": share}
    paths.append_jsonl(KNOWLEDGE, row)
    journal.log("knowledge", id=row["id"], pod=pod, instrument=instrument, share=share)
    return row


def knowledge(pod=None):
    """Every entry, each with the pods that endorsed it, oldest first; pod= only that pod's."""
    entries, ends = {}, {}
    for r in paths.read_jsonl(KNOWLEDGE):
        if r.get("kind") == "endorse":
            ends.setdefault(r.get("id"), []).append(r.get("pod"))
        elif r.get("id"):
            entries[r["id"]] = dict(r)
    out = [e | {"endorsed_by": sorted(set(ends.get(k, [])))} for k, e in entries.items()]
    return [e for e in out if pod in (None, e.get("pod"))]


def endorse(pod, kid):
    """One pod vouches for another pod's entry: it worked, or it changed a trade. Once per pod per entry."""
    e = next((e for e in knowledge() if e["id"] == kid), None)
    if e is None:
        raise ValueError(f"no knowledge entry {kid}")
    if e.get("pod") == pod:
        raise ValueError("a pod does not endorse its own entry")
    if pod in e["endorsed_by"]:
        raise ValueError(f"{pod} already endorsed {kid}")
    row = {"t": clocks.now().isoformat(timespec="seconds"), "kind": "endorse", "id": kid, "pod": pod}
    paths.append_jsonl(KNOWLEDGE, row)
    journal.log("endorse", id=kid, pod=pod, author=e.get("pod"))
    return row


def shared_with(pod, owns=(), n=12):
    """What the other pods shared with the desk, most endorsed first; entries on this pod's markets rank ahead."""
    rows = [e for e in knowledge() if e.get("pod") != pod and e.get("share") == "desk"]
    rows.sort(key=lambda e: (e.get("instrument") in owns, len(e["endorsed_by"]), e.get("t", "")), reverse=True)
    return rows[:n]


def add_lesson(pod, lesson, ticket=None):
    row = {"t": clocks.now().isoformat(timespec="seconds"), "pod": pod, "lesson": lesson, "ticket": ticket}
    paths.append_jsonl(LESSONS, row)
    journal.log("lesson", pod=pod, ticket=ticket)
    return row


def lessons(pod=None, n=20):
    return [r for r in paths.read_jsonl(LESSONS) if pod in (None, r.get("pod"))][-n:]


def _closed(state=None):
    return [v for v in tickets.by_status("closed", state) if v.get("R") is not None]


def similar(tk, n=20, state=None):
    """The n closed tickets most like tk: same instrument 3, same edge 2, same pod 1, same side 1."""
    def score(v):
        return (3 * (v.get("instrument") == tk.get("instrument")) + 2 * (v.get("edge") == tk.get("edge"))
                + (v.get("pod") == tk.get("pod")) + (v.get("side") == tk.get("side")))
    rows = sorted(_closed(state), key=lambda v: (score(v), v.get("updated", "")), reverse=True)
    return [{k: v.get(k) for k in ("id", "pod", "instrument", "side", "edge", "confidence", "R", "reason", "thesis")}
            for v in rows[:n] if score(v) > 0]


def calibration(pod=None, state=None):
    """confidence -> {trades, hit, avg_R}: does a 4 or a 5 really win more than a 3?"""
    out = {}
    for v in _closed(state):
        if pod and v.get("pod") != pod:
            continue
        c = out.setdefault(int(v.get("confidence") or 3), {"trades": 0, "wins": 0, "sum_r": 0.0})
        c["trades"] += 1
        c["wins"] += float(v["R"]) > 0
        c["sum_r"] += float(v["R"])
    return {k: {"trades": c["trades"], "hit": round(c["wins"] / c["trades"], 2), "avg_R": round(c["sum_r"] / c["trades"], 2)}
            for k, c in sorted(out.items())}


def edge_score(edge, backtest_r=0.0, prior=20, state=None):
    """Live R per trade shrunk toward the backtest's: (n * live + prior * backtest) / (n + prior)."""
    rs = [float(v["R"]) for v in _closed(state) if v.get("edge") == edge]
    n = len(rs)
    live = sum(rs) / n if n else 0.0
    return {"trades": n, "live_R": round(live, 3), "score": round((n * live + prior * backtest_r) / (n + prior), 3)}
