"""Runs long data fetches outside agent sessions (owner 2026-10-24, token change 5).

2026-10-24: a finder spent 29 minutes of a Sonnet session waiting on a Binance download. Now the finder writes the
fetch as a script under research/fetch/ and names it in the data item (`"fetch": "research/fetch/<id>.py"`, status
stays "new"). The relay calls `fetch_runner.py step` every pass: it starts one waiting fetch as a detached process
and the relay skips that item while it runs. When it ends, the item is due again and a short finder run checks the
file and closes the item (done with file, range and rows, or rejected).

  python tools/autopilot/fetch_runner.py step          start the next waiting fetch (one at a time); prints a line
  python tools/autopilot/fetch_runner.py running       ids whose fetch is running (one per line)
  python tools/autopilot/fetch_runner.py run <id>      (internal) run the script, write its state file

State: logs/autopilot/fetch/<id>.json {"id", "script", "state": running|done|failed, "rc", "started", "ended", "log"}.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUEUE = REPO / "docs" / "ideas" / "queue.jsonl"
STATE = REPO / "logs" / "autopilot" / "fetch"
FETCH_DIR = (REPO / "research" / "fetch").resolve()
TIMEOUT_S = 4 * 3600


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def items():
    if not QUEUE.exists():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def state(i):
    f = STATE / f"{i}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(i, d):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{i}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")


def alive(pid):
    if not pid:
        return False
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def script_path(it):
    s = it.get("fetch")
    if not s:
        return None
    p = (REPO / s).resolve()
    # Only scripts under research/fetch/ run, so a queue line cannot point the runner anywhere else.
    if FETCH_DIR not in p.parents or p.suffix != ".py" or not p.exists():
        return None
    return p


def running():
    out = []
    for it in items():
        st = state(it.get("id", ""))
        if st and st.get("state") == "running":
            if alive(st.get("pid")):
                out.append(it["id"])
            else:
                st.update(state="failed", rc=None, ended=now(), note="runner process gone")
                write_state(it["id"], st)
    return out


def step():
    busy = running()
    if busy:
        print(f"fetch running: {', '.join(busy)}")
        return
    for it in items():
        if it.get("source") != "data" or it.get("status") != "new":
            continue
        if not it.get("fetch"):
            continue
        p = script_path(it)
        st = state(it["id"])
        if not p:
            # A bad path would leave the item waiting for ever: mark it failed so the finder gets it back.
            if not (st and st.get("script") == it["fetch"] and st.get("state") == "failed"):
                write_state(it["id"], {"id": it["id"], "script": it["fetch"], "state": "failed", "rc": None,
                                       "ended": now(), "note": "script missing or not under research/fetch/"})
            continue
        if st and st.get("script") == it["fetch"] and st.get("state") in ("done", "failed"):
            continue
        log = STATE / f"{it['id']}.log"
        STATE.mkdir(parents=True, exist_ok=True)
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS, NEW_PROCESS_GROUP, NO_WINDOW
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", it["id"]], cwd=REPO,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=flags, close_fds=True)
        write_state(it["id"], {"id": it["id"], "script": it["fetch"], "state": "running",
                               "pid": proc.pid, "started": now(), "log": str(log.relative_to(REPO))})
        print(f"fetch started: {it['id']} ({p.relative_to(REPO)})")
        return


def run(i):
    it = next((x for x in items() if x.get("id") == i), None)
    p = script_path(it) if it else None
    if not p:
        return
    st = state(i) or {"id": i, "script": it["fetch"], "started": now()}
    st.update(state="running", pid=os.getpid())
    write_state(i, st)
    log = STATE / f"{i}.log"
    with open(log, "w", encoding="utf-8") as fh:
        try:
            rc = subprocess.run([sys.executable, str(p)], cwd=REPO, stdout=fh, stderr=subprocess.STDOUT,
                                timeout=TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    st.update(state="done" if rc == 0 else "failed", rc=rc, ended=now())
    write_state(i, st)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "step"
    if cmd == "step":
        step()
    elif cmd == "running":
        print("\n".join(running()))
    elif cmd == "run" and len(sys.argv) > 2:
        run(sys.argv[2])
