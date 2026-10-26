"""The desk clock, run every minute by the \\AurumDesk\\Clock task (DESIGN.md section 4). Plain code, no model:

1. connect to the desk terminal and run the executor (stops, targets, trails, approved tickets, the loss lines);
2. check the pods' triggers and queue wakes;
3. run what the schedule says is due: queue briefs, debriefs and reviews, refresh the calendar, run the code check,
   commit the desk record;
4. start the runner when agent jobs wait, and write the heartbeat the watchdog reads.

python -m desk.tick           one pass (what the task runs)
"""
import datetime as dt
import subprocess
import traceback

from desk import broker, clocks, executor, jobs, journal, monitor, mutex, news, paths, phase, tickets, triggers

SCHEDULE = paths.STATE / "schedule.json"
HEARTBEAT = paths.STATE / "heartbeat.json"
TICK_MUTEX = "Local\\AurumDeskTick"
RETRY = dt.timedelta(minutes=30)  # a failed calendar fetch or commit tries again after this
AGENT_KINDS = ("brief", "debrief", "weekly", "scorekeeper")
COMMIT_PATHS = ["desk/journal", "desk/memory", "desk/playbooks", "desk/board.jsonl", "desk/tickets.jsonl",
                "desk/reports"]


def _due(ev, t, sched):
    last = sched.get(ev["name"], {})
    if last.get("failed") and t - dt.datetime.fromisoformat(last["failed"]) < RETRY:
        return False
    ran = dt.datetime.fromisoformat(last["ran"]) if last.get("ran") else None
    if ev.get("every_min"):
        return ran is None or t - ran >= dt.timedelta(minutes=ev["every_min"])
    return clocks.due(ev, t, ran)


def commit(t):
    """Commit the desk record by path and push. A failure is logged and tried again later."""
    root = str(paths.ROOT)
    have = [p for p in COMMIT_PATHS if (paths.ROOT / p).exists()]
    if not have:
        return True
    def git(*a):
        return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=120)
    git("add", "--", *have)
    if not git("diff", "--cached", "--name-only", "--", *have).stdout.strip():
        return True
    r = git("commit", "-m", f"Desk record {clocks.trading_day(t).isoformat()}", "--", *have)
    if r.returncode != 0:
        journal.log("commit_error", why=(r.stderr or r.stdout)[-400:])
        return False
    p = git("push")
    if p.returncode != 0:
        journal.log("push_failed", why=(p.stderr or p.stdout)[-400:])
    return True


def schedule(b, cfg, summary, t):
    """Run or queue what is due. Returns the names that ran."""
    sched = paths.read_json(SCHEDULE, {})
    ph = phase.current()
    active = phase.pods_active(cfg, ph)
    ran = []
    for ev in cfg.get("schedule", []):
        if not _due(ev, t, sched):
            continue
        k, ok = ev["kind"], True
        try:
            if k == "brief":
                pods = [p for p in active if p in ev.get("pods", active)]
                if pods and not jobs.has_pending("brief", name=ev["name"]):
                    jobs.queue("brief", t, name=ev["name"], pods=pods)
            elif k in AGENT_KINDS:
                if active and not jobs.has_pending(k):
                    jobs.queue(k, t, name=ev["name"])
            elif k == "calendar":
                ok = news.fetch(cfg) is not None
            elif k == "monitor":
                monitor.run(b, cfg, summary, t)
            elif k == "commit":
                jobs.compact()
                ok = commit(t)
        except Exception as e:
            ok = False
            journal.log("schedule_error", event=ev["name"], why=f"{type(e).__name__}: {e}")
        if ok:
            sched[ev["name"]] = {"ran": t.isoformat(timespec="seconds")}
            ran.append(ev["name"])
        else:
            sched[ev["name"]] = dict(sched.get(ev["name"], {}), failed=t.isoformat(timespec="seconds"))
    paths.write_json(SCHEDULE, sched)
    return ran


def wake_pods(b, cfg, t):
    fired = triggers.check(b, cfg, tickets.fold(), t)
    by_pod = {}
    for g in fired:
        by_pod.setdefault(g["pod"], []).append(g["id"])
    active = phase.pods_active(cfg)
    for pod, ids in by_pod.items():
        if pod in active:
            jobs.wake(pod, ids, cfg, t)
    return by_pod


def once():
    """One clock pass. Returns the heartbeat, or None when another pass still holds the clock."""
    with mutex.hold(TICK_MUTEX) as mine:
        if not mine:
            return None
        cfg = paths.config()
        t = clocks.now()
        b = broker.connect(cfg)
        summary, ran, woke = {"ok": False, "why": getattr(b, "why", "")}, [], {}
        try:
            if b.mode != "dry":
                try:
                    summary = executor.run(b, cfg, t)
                except Exception as e:
                    summary = {"ok": False, "why": f"{type(e).__name__}: {e}"}
                    journal.log("tick_error", where="executor", why=summary["why"], tb=traceback.format_exc()[-1500:])
                try:
                    woke = wake_pods(b, cfg, t)
                except Exception as e:
                    journal.log("tick_error", where="triggers", why=f"{type(e).__name__}: {e}")
            ran = schedule(b, cfg, summary, t)
            jobs.expire_stale(t)
            jobs.launch()
        finally:
            b.shutdown()
        hb = {"t": t.isoformat(timespec="seconds"), "ok": bool(summary.get("ok")), "broker": b.mode,
              "why": getattr(b, "why", "") or summary.get("why"), "summary": summary, "ran": ran,
              "woke": woke, "phase": phase.current()}
        paths.write_json(HEARTBEAT, hb)
        return hb


if __name__ == "__main__":
    hb = once()
    if hb is None:
        print("another clock pass is running")
    else:
        s = hb["summary"]
        print(f"{hb['t']} broker={hb['broker']} phase={hb['phase']} ok={hb['ok']} "
              f"{'equity=%.2f' % s['equity'] if s.get('equity') is not None else hb.get('why') or ''} ran={hb['ran']}")
