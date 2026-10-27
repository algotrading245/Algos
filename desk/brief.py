"""What an agent reads when it wakes (DESIGN.md sections 3c, 4 and 6): the desk's state, gathered by code, so an agent
spends its turns on judgment instead of on looking things up.

build(role, job) returns markdown. A pod sees the board, the calendar, its tickets and triggers, its lessons, its
playbook and its calibration; the head trader also sees every proposed ticket with its 20 most similar past setups; the
debrief sees the day's closed tickets; the monitor sees the issues the code found.
"""
import json

from desk import cli, journal, memory, news, paths, playbooks, systematic, tickets, triggers

HEAD = cli.HEAD


def _j(obj):
    return "```json\n" + json.dumps(obj, indent=1, default=str) + "\n```"


def _section(title, obj):
    if obj in (None, [], {}, ""):
        return f"## {title}\n(none)\n"
    return f"## {title}\n{obj if isinstance(obj, str) else _j(obj)}\n"


def _shadow():
    s = paths.read_json(systematic.SHADOW, {})
    if not s:
        return {}
    return {"since": s.get("since"), "total_r": s.get("total_r"),
            "edges": {e: {m: {k: v.get(k) for k in ("trades", "pf", "total_r")} for m, v in ms.items()}
                      for e, ms in (s.get("edges") or {}).items()}}


def _closed_today(state, t):
    day = t.date().isoformat()
    return [cli._ticket_brief(v) | {"thesis": v.get("thesis"), "invalidation": v.get("invalidation"),
                                    "evidence": v.get("evidence"), "cites": v.get("cites")}
            for v in tickets.by_status("closed", state) if v.get("updated", "")[:10] == day]


def proposed(state=None):
    return [v for v in tickets.live(state).values() if v.get("status") == "proposed"]


def build(role, job=None):
    """The brief for one agent run, as markdown."""
    from desk import clocks
    job = job or {}
    t = clocks.now()
    state = tickets.fold()
    st = cli.status()
    out = [f"# Desk brief for {role} ({job.get('kind', 'run')}{' ' + job['name'] if job.get('name') else ''}), "
           f"{st['now']}\n"]
    out.append(_section("Status", {k: st[k] for k in ("phase", "phase_day", "pods_active", "profile", "risk_scale",
                                                      "halt", "account")}))
    out.append(_section("Live tickets", st["live_tickets"]))
    if role in paths.config().get("pods", {}):
        out.append(_section("The board (last 30 posts)", memory.board(30)))
        out.append(_section("Calendar, next 24 hours", [{k: v for k, v in e.items() if k != "time"}
                                                       for e in news.upcoming(24, t)]))
        out.append(_section(f"Your triggers ({role})", triggers.active(role)))
        out.append(_section(f"Your playbook (v{playbooks.version(role)})", playbooks.show(role)))
        out.append(_section("Your lessons", memory.lessons(role)))
        out.append(_section("Your calibration (confidence -> trades, hit rate, avg R)",
                            memory.calibration(role, state)))
        armed = systematic.state()["armed"]
        out.append(_section("Armed legs" if role == systematic.POD else "Your armed legs",
                            armed if role == systematic.POD else [a for a in armed if a.get("pod") == role]))
        if role == systematic.POD:
            out.append(_section("Shadow benchmark (the tested edges on paper since day 0)", _shadow()))
    elif role == HEAD:
        rows = []
        for v in proposed(state):
            rows.append({"ticket": cli._ticket_brief(v) | {"thesis": v.get("thesis"),
                                                         "invalidation": v.get("invalidation"),
                                                         "evidence": v.get("evidence"), "cites": v.get("cites")},
                         "similar": memory.similar(v, 20, state),
                         "calibration": memory.calibration(v.get("pod"), state)})
        out.append(_section("Proposed tickets, each with its 20 most similar past setups", rows))
        out.append(_section("The board (last 30 posts)", memory.board(30)))
        out.append(_section("Shadow benchmark", _shadow()))
        scores = paths.read_json(paths.STATE / "scores.json", {})
        if scores:
            out.append(_section("Scores (4 weeks)", scores))
        alloc = paths.read_json(paths.STATE / "alloc.json", {})
        if alloc:
            out.append(_section("Pod allocation", alloc))
    elif role == "debrief":
        out.append(_section("Closed today", _closed_today(state, t)))
        out.append(_section("The board today", [r for r in memory.board(60) if r["t"][:10] == t.date().isoformat()]))
        out.append(_section("Lessons so far (last 40)", memory.lessons(None, 40)))
    elif role == "monitor":
        out.append(_section("Monitor state", paths.read_json(paths.STATE / "monitor.json", {})))
        out.append(_section("Journal, last day (errors and refusals)",
                            [r for r in journal.recent(None, 1) if any(w in r.get("kind", "") for w in
                                                                     ("error", "refused", "block", "fail", "alert",
                                                                      "timeout", "breach"))][-60:]))
    elif role == "scorekeeper":
        out.append(_section("Scores", paths.read_json(paths.STATE / "scores.json", {})))
        out.append(_section("Shadow benchmark", _shadow()))
    data = {k: v for k, v in job.items() if k not in ("id", "kind", "queued", "status", "started")}
    if data:
        out.append(_section("Why you were woken", data))
    if job.get("triggers"):
        fired = [r for r in journal.recent(["trigger_fired"], 1) if r.get("id") in job["triggers"]]
        out.append(_section("Triggers that fired", fired))
    return "\n".join(out)
