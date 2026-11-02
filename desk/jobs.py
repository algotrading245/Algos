"""The desk's job queue (STATE/jobs.jsonl): the clock queues agent work, the runner drains it one job at a time.

A row is either a job {"id", "kind", "queued", ...data} or an event {"job", "event": started|done|failed|skipped, "t"}.
Kinds the runner knows: brief (pods, name), wake (pod, triggers), debrief, weekly, scorekeeper, monitor (issues).
"""
import datetime as dt
import json
import os
import subprocess
import sys
import uuid

from desk import clocks, journal, mutex, paths

FILE = paths.STATE / "jobs.jsonl"
RUNNER = paths.STATE / "runner.json"
RUNNER_MUTEX = "Local\\AurumDesk"
PRIORITY = {"monitor": 0, "wake": 1, "brief": 2, "debrief": 3, "scorekeeper": 4, "weekly": 5}
STALE = dt.timedelta(hours=6)  # a job still waiting after this is skipped, its moment has passed


def queue(kind, t=None, **data):
    t = t or clocks.now()
    j = {"id": "j" + uuid.uuid4().hex[:8], "kind": kind, "queued": t.isoformat(timespec="seconds")}
    j.update(data)
    paths.append_jsonl(FILE, j)
    journal.log("job_queued", id=j["id"], job=kind, **{k: v for k, v in data.items() if k in ("pod", "pods", "name")})
    return j["id"]


def mark(jid, event, **data):
    paths.append_jsonl(FILE, dict({"job": jid, "event": event, "t": clocks.now().isoformat(timespec="seconds")}, **data))


def fold():
    """{id: job with its last event as 'status'}, in queue order."""
    out = {}
    for r in paths.read_jsonl(FILE):
        if "kind" in r:
            out[r["id"]] = dict(r, status="pending")
        elif r.get("job") in out:
            out[r["job"]]["status"] = r["event"]
            out[r["job"]][r["event"]] = r["t"]
            if r.get("why"):
                out[r["job"]]["why"] = r["why"]
    return out


def pending():
    """Waiting jobs, most urgent first (then oldest)."""
    rows = [j for j in fold().values() if j["status"] == "pending"]
    return sorted(rows, key=lambda j: (PRIORITY.get(j["kind"], 9), j["queued"]))


def has_pending(kind, **match):
    return any(j["kind"] == kind and all(j.get(k) == v for k, v in match.items()) for j in pending())


def weekend_closed(t=None, pod=None, cfg=None):
    """True while the active risk profile is flat over the weekend, between its Friday cutoff and Sunday reopen: its
    tickets are refused then (risk_gate.weekend_cutoff), so a pod's wake or brief would spend its tokens on tickets that
    cannot pass (11-01: the crypto pod spent 58k tokens against a 39k slice on weekend tickets all blocked).
    With weekend_crypto on the profile, a pod that owns crypto stays open: its crypto tickets can pass."""
    from desk import risk_gate
    try:
        _, prof = risk_gate.profile()
    except Exception:
        return False
    t = t or clocks.now()
    if pod and risk_gate.weekend_cutoff(prof, t, "crypto") is False:
        cfg = cfg or paths.config()
        owns = cfg.get("pods", {}).get(pod, {}).get("owns", [])
        if any(cfg["instruments"].get(i, {}).get("class") == "crypto" for i in owns):
            return False
    return risk_gate.weekend_cutoff(prof, t)


def wake(pod, trigger_ids, cfg, t=None, **data):
    """Queue a wake for a pod, unless it used its wake cap today (which follows its token share, allowance.wake_cap)
    or its token slice is spent. data (the watcher's `watch` rows) goes into the job, so the brief says why the pod
    was woken. Returns the job id or None."""
    from desk import allowance, triggers
    cap = allowance.wake_cap(pod, cfg)
    why = None
    if weekend_closed(t, pod, cfg):
        why = "past the weekend cutoff: the profile is flat over the weekend, so no ticket can pass"
    elif triggers.wakes_today(pod, t) >= cap:
        why = f"{cap} wakes already today (the cap follows the token share)"
    elif allowance.slice_spent(pod, cfg, t):
        why = "token slice spent for today"
    if why:
        journal.log("wake_refused", pod=pod, triggers=trigger_ids, why=why, **data)
        return None
    triggers.count_wake(pod, t)
    return queue("wake", t, pod=pod, triggers=trigger_ids, **data)


def compact(keep_days=14):
    """Drop finished jobs older than keep_days so the file stays small."""
    cutoff = (clocks.now() - dt.timedelta(days=keep_days)).isoformat()
    jobs = fold()
    keep = {i for i, j in jobs.items() if j["status"] in ("pending", "started") or j["queued"] >= cutoff}
    rows = [r for r in paths.read_jsonl(FILE) if (r.get("id") if "kind" in r else r.get("job")) in keep]
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, FILE)


def runner_busy():
    return not mutex.free(RUNNER_MUTEX)


def launch():
    """Start the runner (detached) when jobs wait and no runner holds the mutex. Returns the pid, or None."""
    if not pending() or runner_busy():
        return None
    exe = sys.executable
    w = exe.replace("python.exe", "pythonw.exe")
    if os.path.exists(w):
        exe = w
    if os.environ.get("AURUM_DESK_NOLAUNCH"):
        journal.log("runner_launch", pid=None, note="AURUM_DESK_NOLAUNCH set")
        return None
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    p = subprocess.Popen([exe, "-m", "desk.runner", "drain"], cwd=str(paths.ROOT), creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    paths.write_json(RUNNER, {"pid": p.pid, "started": clocks.now().isoformat(timespec="seconds")})
    journal.log("runner_launch", pid=p.pid)
    return p.pid


def expire_stale(t=None):
    t = t or clocks.now()
    for j in pending():
        if j["kind"] != "monitor" and t - dt.datetime.fromisoformat(j["queued"]) > STALE:
            mark(j["id"], "skipped", why="stale")
