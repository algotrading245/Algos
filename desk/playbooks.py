"""Living playbooks (DESIGN.md section 3c): desk/playbooks/<pod>.md, one per pod, edited only as versions.

The debrief writes lessons daily (memory.add_lesson); every Saturday the head trader folds the lessons that held into
the playbook with edit(). Each edit keeps the old text as versions/<pod>/vN.md and logs {v, t, by, why} in
versions/<pod>/log.jsonl. The scorekeeper's check() rolls a version back when it did worse than the one before it
over 4 weeks of closed trades.
"""
import datetime as dt

from desk import clocks, journal, paths, tickets

MIN_TRADES = 10  # a version needs this many closed trades before it can be judged
WINDOW = dt.timedelta(weeks=4)


def file(pod):
    return paths.PLAYBOOKS / f"{pod}.md"


def _dir(pod):
    return paths.PLAYBOOKS / "versions" / pod


def log(pod):
    return paths.read_jsonl(_dir(pod) / "log.jsonl")


def version(pod):
    rows = log(pod)
    return rows[-1]["v"] if rows else 0


def show(pod):
    f = file(pod)
    return f.read_text(encoding="utf-8") if f.exists() else ""


def edit(pod, text, why, by="head-trader"):
    """Save text as the pod's next version. Returns the new version number."""
    if not why:
        raise ValueError("a playbook edit needs a reason")
    v = version(pod) + 1
    d = _dir(pod)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"v{v}.md").write_text(text, encoding="utf-8")
    file(pod).parent.mkdir(parents=True, exist_ok=True)
    file(pod).write_text(text, encoding="utf-8")
    paths.append_jsonl(d / "log.jsonl", {"v": v, "t": clocks.now().isoformat(timespec="seconds"), "by": by, "why": why})
    journal.log("playbook_edit", pod=pod, v=v, by=by, why=why)
    return v


def rollback(pod, to, why, by="owner"):
    """Restore version `to` as a new version (the history is never rewritten)."""
    src = _dir(pod) / f"v{int(to)}.md"
    if not src.exists():
        raise ValueError(f"{pod} has no playbook version {to}")
    return edit(pod, src.read_text(encoding="utf-8"), f"rollback to v{to}: {why}", by=by)


def _r_per_trade(pod, start, end, state):
    rs = [float(v["R"]) for v in tickets.by_status("closed", state) if v.get("pod") == pod and v.get("R") is not None
          and start <= v.get("updated", "") < end]
    return len(rs), (sum(rs) / len(rs) if rs else 0.0)


def check(pod, state=None, t=None):
    """Roll back the current version when, 4 weeks after it began, it made less R per trade than the one before.
    Returns the rollback's version number, or None."""
    t = t or clocks.now()
    rows = log(pod)
    if len(rows) < 2 or rows[-1].get("judged"):
        return None
    cur, prev = rows[-1], rows[-2]
    t = t if t.tzinfo else t.replace(tzinfo=clocks.UTC)
    began = dt.datetime.fromisoformat(cur["t"])
    if t - (began if began.tzinfo else began.replace(tzinfo=clocks.UTC)) < WINDOW:
        return None
    state = state or tickets.fold()
    n_cur, r_cur = _r_per_trade(pod, cur["t"], t.isoformat(), state)
    n_prev, r_prev = _r_per_trade(pod, prev["t"], cur["t"], state)
    if n_cur < MIN_TRADES or n_prev < MIN_TRADES:
        return None
    paths.append_jsonl(_dir(pod) / "log.jsonl", dict(cur, judged=t.isoformat(timespec="seconds"),
                                                     r_cur=round(r_cur, 3), r_prev=round(r_prev, 3)))
    if r_cur < r_prev:
        return rollback(pod, prev["v"], f"v{cur['v']} made {r_cur:.2f}R a trade against {r_prev:.2f}R",
                        by="scorekeeper")
    return None
