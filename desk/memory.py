"""The desk's shared memory (DESIGN.md sections 9-10): the board, lessons, similar past setups and calibration.

board.jsonl    pods post what they see and cite each other; a cite on a winning ticket splits the credit
lessons.jsonl  the debrief's lessons, one per row {t, pod, lesson, ticket}
Both are append-only, like the journal.
"""
import os
import uuid
from pathlib import Path

from desk import clocks, journal, paths, tickets

BOARD = Path(os.environ.get("AURUM_DESK_BOARD", paths.DESK / "board.jsonl"))
LESSONS = paths.MEMORY / "lessons.jsonl"


def post(pod, text, instrument=None, cites=None):
    row = {"t": clocks.now().isoformat(timespec="seconds"), "id": "b" + uuid.uuid4().hex[:8], "pod": pod,
           "text": text, "instrument": instrument, "cites": cites or []}
    paths.append_jsonl(BOARD, row)
    journal.log("board_post", id=row["id"], pod=pod, instrument=instrument)
    return row


def board(n=30, pod=None):
    rows = [r for r in paths.read_jsonl(BOARD) if pod in (None, r.get("pod"))]
    return rows[-n:]


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
