"""What an agent reads when it wakes (DESIGN.md sections 3c, 4 and 6): the desk's state, gathered by code, so an agent
spends its turns on judgment instead of on looking things up.

build(role, job) returns markdown. A pod sees the board, the asks to it and the replies to its own, what other pods
shared, its intelligence profile (desk/intel.py), the calendar, its tickets and triggers, its lessons, its playbook and
its calibration; the head trader also sees every proposed ticket with its 20 most similar past setups and its pod's
profile; the debrief sees the day's closed tickets; the monitor sees the issues the code found.
"""
import datetime as dt
import json

from desk import (cli, forecasts, intel, journal, market_model, memory, news, paths, playbooks, research, systematic,
                  tickets, triggers)

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


QUIET_RUNS = 3  # owner 2026-11-01: a pod that neither asked, answered, reviewed nor shared in its last 3 runs is nudged


def quiet(pod, n=QUIET_RUNS):
    """True when the pod's last n successful runs left no ask, reply, review or knowledge entry."""
    runs = [r for r in journal.recent(["agent_run"], 14) if r.get("role") == pod and r.get("ok")]
    if len(runs) < n:
        return False
    r = runs[-n]
    since = (dt.datetime.fromisoformat(r["t"]) - dt.timedelta(seconds=r.get("seconds") or 0)).isoformat(
        timespec="seconds")
    talked = any(b.get("pod") == pod and b.get("kind") in ("ask", "reply", "review") and b.get("t", "") >= since
                 for b in memory.board(10 ** 6))
    shared = any(k.get("pod") == pod and k.get("t", "") >= since for k in paths.read_jsonl(memory.KNOWLEDGE))
    return not (talked or shared)


def to_review(pod, owns, state=None):
    """Other pods' proposed tickets this pod has not reviewed yet, those on its own markets first."""
    rows = [v for v in proposed(state) if v.get("pod") != pod
            and all(r["pod"] != pod for r in memory.reviews(v["id"]))]
    rows.sort(key=lambda v: v.get("instrument") not in owns)
    return [cli._ticket_brief(v) | {"thesis": v.get("thesis"), "invalidation": v.get("invalidation"),
                                    "evidence": v.get("evidence"), "reviews": memory.reviews(v["id"])} for v in rows]


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
        owns = paths.config()["pods"][role].get("owns") or []
        if owns:
            out.append(_section("Your home markets (a watchlist, not a fence; every desk market is open): one board note each, with instrument= set", owns))
        out.append(_section("The board (last 30 posts)", memory.board(30)))
        out.append(_section("Questions for you from other pods: answer each with board reply ID",
                            memory.open_asks(role)))
        out.append(_section("Replies to your questions", memory.replies_for(role)))
        out.append(_section("Knowledge other pods shared (most endorsed first; endorse what helped you)",
                            memory.shared_with(role, owns)))
        out.append(_section("Research desk: the book's gaps and the finder's ideas. If a market you own fits a gap, "
                            "or you keep seeing a pattern no leg trades, share it (memory learn, share desk): the "
                            "finder reads the desk's notes each run",
                            {"gaps": research.gaps(), "ideas": research.ideas()}))
        prof = intel.profile(role, state)
        out.append(_section("Your intelligence profile: work on your weaknesses, lean on your strengths",
                            {k: prof[k] for k in ("level", "iq", "xp", "trading", "strengths", "weaknesses",
                                                  "work", "talk", "share")}))
        out.append(_section("Your forecasts: write a call on any market you have a view on (forecast new SYM up|down "
                            "PROB HOURS \"why\"). They are graded daily against the real price; the skill (Brier "
                            "against a coin flip) feeds your score and your token share. Only a calibrated PROB pays: "
                            "a confident wrong call costs more than a confident right one earns",
                            forecasts.brief(role, t)))
        out.append(_section("Your market model: your own view of the markets, kept between runs (model set SYM "
                            "bias=.. regime=.. levels=a,b conviction=1-3 edges=x,y \"drivers\"; model view \"..\"). "
                            "Refresh the stale ones or drop them. The live watcher wakes you only on the levels, "
                            "edges and markets in it, and a brief that leaves it untouched is journaled and costs IQ. "
                            "Put a forecast on each bias you hold: the forecast is what feeds your token share. "
                            "desk_biases is every pod's live bias",
                            market_model.brief(role, t)))
        try:
            from desk import allowance
            st = allowance.status(paths.config(), t)
            mine = st["pods"].get(role, {})
            out.append(_section("Your allowance today: your slice of the pods' token pool (the pool is fitted to "
                                "the pods' weekly dollars and the account's weekly cap) and your wake cap, both "
                                "following your token share. A spent slice or cap means no more wakes today",
                                {"slice": mine.get("slice"), "spent": mine.get("spent"),
                                 "wake_cap": mine.get("wake_cap"), "wakes_today": mine.get("wakes"),
                                 "pool": st.get("pool"), "throttle": st.get("throttle")}))
        except Exception as e:
            out.append(_section("Your allowance today", f"unavailable: {type(e).__name__}: {e}"))
        alloc = paths.read_json(paths.STATE / "alloc.json", {})
        if alloc.get("token_shares"):
            out.append(_section("Your token share this week: how much of the pods' token pool you get to think "
                                "with. It follows your token score = trading (once 20 closed trades) + forecast "
                                "skill + half your contribution (endorsements of what you shared, replies and "
                                "reviews), moving at most 25% a week inside 5-35%",
                                {"share": alloc["token_shares"].get(role), "week": alloc.get("week"),
                                 "score": (alloc.get("token_scores") or {}).get(role)}))
        out.append(_section("Tickets for you to review: one board review ID each, before the head trader judges",
                            to_review(role, owns, state)))
        if not prof["trading"].get("trades") and role != systematic.POD:
            out.append(_section("You have no closed trades yet",
                                "The desk cannot calibrate a pod with no record. Propose your best setup this run if "
                                "one meets confidence 2 or more, at minimum size (risk_pct 0.1): the head trader "
                                "approves a first ticket on its thesis, invalidation and costs alone."))
        if quiet(role):
            out.append(_section(f"Quiet for {QUIET_RUNS} runs",
                                "You have not asked, answered, reviewed or shared in your last "
                                f"{QUIET_RUNS} runs. This run: ask one pod a question (board ask), or share one "
                                "thing you learned (memory learn)."))
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
                         "calibration": memory.calibration(v.get("pod"), state),
                         "reviews": memory.reviews(v["id"]),
                         "pod_intel": {k: intel.profile(v.get("pod"), state)[k]
                                       for k in ("iq", "trading", "strengths", "weaknesses")}})
            rows[-1]["pod_closed_trades"] = rows[-1]["pod_intel"]["trading"].get("trades") or 0
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
