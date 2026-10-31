"""Each pod's intelligence, computed from what it really did (owner 2026-10-31), never a timer.

profile(pod) reads the journal, the board, the knowledge base and the closed tickets:
  work      runs that finished, board notes, markets left without a note
  talk      asks it sent, asks it answered, asks to it still open
  share     knowledge it shared, endorsements it got from other pods, its posts other pods cited
  trading   closed trades, hit rate, R per trade shrunk toward 0 by SHRINK trades, how well confidence ranks R
  where     its best and worst instrument / edge / side (3+ trades each), shrunk the same way
xp is the sum of that work (XP below); level follows LEVELS; iq is 100 plus skill, calibration, reach and coverage,
clamped to 60-160. The pod's brief shows the profile back to it, so the weak spots it reads are its own.

write() keeps state/intel.json for the dashboards, with the latest talk, and journals a level_up when a pod climbs.
"""
import math

from desk import journal, memory, paths, tickets

FILE = paths.STATE / "intel.json"
SHRINK = 10      # prior trades at 0R behind every R per trade
MIN_GROUP = 3    # trades before an instrument, edge or side counts as a strength or a weakness
XP = {"run": 10, "note": 2, "ask": 2, "answer": 6, "share": 5, "endorsed": 8, "cited": 15, "trade": 5, "win_R": 20}
LEVELS = [(0, "Rookie"), (100, "Analyst"), (250, "Associate"), (500, "Trader"), (900, "Senior Trader"),
          (1500, "Lead"), (2400, "Principal"), (3600, "Strategist"), (5200, "Master"), (7500, "Legend")]
JOURNAL_DAYS = 3650


def level(xp):
    i = max(i for i, (lo, _) in enumerate(LEVELS) if xp >= lo)
    nxt = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else None
    return {"n": i + 1, "name": LEVELS[i][1], "floor": LEVELS[i][0], "next": nxt}


def _shrunk(rs):
    return round(sum(rs) / (len(rs) + SHRINK), 3)


def _corr(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    vx, vy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if not vx or not vy:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy), 2)


def _where(trades):
    groups = {}
    for v in trades:
        for key in ("instrument", "edge", "side"):
            if v.get(key):
                groups.setdefault(f"{key} {v[key]}", []).append(float(v["R"]))
    rows = [{"what": k, "trades": len(rs), "avg_R": round(sum(rs) / len(rs), 2), "score": _shrunk(rs)}
            for k, rs in groups.items() if len(rs) >= MIN_GROUP]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return [r for r in rows if r["score"] > 0][:3], [r for r in reversed(rows) if r["score"] < 0][:3]


def _rows(state=None):
    """Everything profile() reads, once, so write() does not read the files six times."""
    return {"journal": journal.recent(["agent_run", "missing_notes"], JOURNAL_DAYS),
            "board": paths.read_jsonl(memory.BOARD), "knowledge": memory.knowledge(),
            "closed": memory._closed(state), "tickets": list((state or tickets.fold()).values())}


def profile(pod, state=None, rows=None):
    r = rows or _rows(state)
    runs = sum(1 for j in r["journal"] if j.get("kind") == "agent_run" and j.get("role") == pod and j.get("ok"))
    missed = sum(len(j.get("markets") or []) for j in r["journal"] if j.get("kind") == "missing_notes"
                 and j.get("pod") == pod)
    posts = [b for b in r["board"] if b.get("pod") == pod]
    mine = {b["id"] for b in posts if b.get("id")}
    notes = sum(1 for b in posts if not b.get("kind"))
    asked = sum(1 for b in posts if b.get("kind") == "ask")
    answered = sum(1 for b in posts if b.get("kind") == "reply")
    cited = (sum(1 for b in r["board"] if b.get("pod") != pod for c in b.get("cites") or [] if c in mine)
             + sum(1 for v in r["tickets"] if v.get("pod") != pod for c in v.get("cites") or [] if c in mine))
    shared = [e for e in r["knowledge"] if e.get("pod") == pod]
    endorsed = sum(len(e["endorsed_by"]) for e in shared)
    trades = [v for v in r["closed"] if v.get("pod") == pod]
    rs = [float(v["R"]) for v in trades]
    wins = sum(1 for x in rs if x > 0)
    skill = _shrunk(rs) if rs else 0.0
    calib = _corr([int(v.get("confidence") or 3) for v in trades], rs)
    strong, weak = _where(trades)
    expected = notes + missed
    coverage = round(notes / expected, 2) if expected else None
    xp = round(XP["run"] * runs + XP["note"] * notes + XP["ask"] * asked + XP["answer"] * answered
               + XP["share"] * len(shared) + XP["endorsed"] * endorsed + XP["cited"] * cited
               + XP["trade"] * len(trades) + XP["win_R"] * max(0.0, sum(rs)))
    iq = 100 + max(-30.0, min(30.0, 60 * skill)) + 10 * (calib or 0) + 10 * min(1.0, (cited + endorsed) / 20)
    if coverage is not None:
        iq -= 10 * (1 - coverage)
    return {"pod": pod, "xp": xp, "level": level(xp), "iq": int(round(max(60, min(160, iq)))),
            "work": {"runs": runs, "notes": notes, "missed_notes": missed, "coverage": coverage},
            "talk": {"asked": asked, "answered": answered, "open_to_it": len(memory.open_asks(pod))},
            "share": {"shared": len(shared), "endorsed": endorsed, "cited": cited},
            "trading": {"trades": len(trades), "hit": round(wins / len(rs), 2) if rs else None,
                        "avg_R": round(sum(rs) / len(rs), 2) if rs else None, "skill_R": skill,
                        "calibration": calib},
            "strengths": strong, "weaknesses": weak}


def all_profiles(cfg=None, state=None):
    cfg = cfg or paths.config()
    rows = _rows(state)
    return {p: profile(p, state, rows) for p in cfg.get("pods", {})}


def write(cfg=None):
    """state/intel.json for the dashboards; a pod whose level rose since the last write gets a level_up entry."""
    from desk import clocks
    old = (paths.read_json(FILE, {}) or {}).get("pods") or {}
    pods = all_profiles(cfg)
    for p, v in pods.items():
        was = ((old.get(p) or {}).get("level") or {}).get("n")
        if was and v["level"]["n"] > was:
            journal.log("level_up", pod=p, level=v["level"]["n"], name=v["level"]["name"], xp=v["xp"], iq=v["iq"])
    out = {"t": clocks.now().isoformat(timespec="seconds"), "pods": pods, "talk": memory.talk(40),
           "knowledge": memory.knowledge()[-40:]}
    paths.write_json(FILE, out)
    return out
