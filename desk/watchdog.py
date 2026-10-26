"""The watchdog, run every 5 minutes and at logon by the \\AurumDesk\\Watchdog task (DESIGN.md section 10).

- the desk terminal is installed but not running: start it (portable), so a reboot needs no one at the PC;
- the heartbeat is older than 5 minutes: the clock has stalled, so run a pass here and write an alert;
- an agent run is past its deadline: kill it (the runner marks the job failed and moves on).
It touches only the desk terminal (C:\\MetaTrader 5 - Desk), never the other MetaTrader installs.

python -m desk.watchdog
"""
import datetime as dt
import subprocess
from pathlib import Path

from desk import clocks, journal, jobs, monitor, paths

STALE = dt.timedelta(minutes=5)
GRACE = dt.timedelta(minutes=5)


def _procs():
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            out.append((p.info["pid"], p.info["name"] or "", p.info["exe"] or ""))
        except Exception:
            continue
    return out


def terminal_running(cfg, procs=None):
    exe = Path(cfg["terminal"]["path"]).resolve()
    for _, name, path in procs if procs is not None else _procs():
        if name.lower() == exe.name.lower() and path and Path(path).resolve() == exe:
            return True
    return False


def start_terminal(cfg):
    exe = cfg["terminal"]["path"]
    if not Path(exe).exists():
        return False
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe, "/portable"], cwd=str(Path(exe).parent), creationflags=flags, close_fds=True)
    journal.log("terminal_started", path=exe)
    return True


def _kill_tree(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        for c in p.children(recursive=True):
            c.kill()
        p.kill()
        return True
    except Exception:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return r.returncode == 0


def check_runner(t):
    r = paths.read_json(jobs.RUNNER, {})
    if not r.get("deadline") or not r.get("agent_pid"):
        return None
    if t < dt.datetime.fromisoformat(r["deadline"]) + GRACE:
        return None
    killed = _kill_tree(r["agent_pid"])
    journal.log("runner_timeout", job=r.get("job"), pid=r["agent_pid"], killed=killed)
    r.pop("agent_pid", None)
    paths.write_json(jobs.RUNNER, r)
    return r.get("job")


def once():
    cfg = paths.config()
    t = clocks.now()
    did = []
    if Path(cfg["terminal"]["path"]).exists() and not terminal_running(cfg):
        if start_terminal(cfg):
            did.append("started the desk terminal")
    hb = paths.read_json(paths.STATE / "heartbeat.json", {})
    last = dt.datetime.fromisoformat(hb["t"]) if hb.get("t") else None
    if last is None or t - last > STALE:
        from desk import tick
        age = "never" if last is None else f"{int((t - last).total_seconds() // 60)} min ago"
        if last is not None:
            monitor.write_alert([{"level": "alert", "what": f"the desk clock stalled (last heartbeat {age}); "
                                  "the watchdog ran a pass. Check the \\AurumDesk\\Clock task."}], t)
        journal.log("clock_stalled", last=hb.get("t"))
        tick.once()
        did.append(f"clock pass (heartbeat {age})")
    job = check_runner(t)
    if job:
        did.append(f"killed the agent run of job {job}")
    journal.log("watchdog", did=did) if did else None
    return did


if __name__ == "__main__":
    print("; ".join(once()) or "all well")
