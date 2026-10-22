# Dispatch watcher (owner 2026-10-21): wakes the relay within a minute of something new, so an agent does not wait
# for the relay's 5-minute tick. Started by the keeper every minute; quiet and fast when nothing changed.
#
#   python tools/autopilot/dispatch.py [--dry-run]      (--dry-run: say what it sees, write and start nothing)
#
# What counts as new:
# - A demo ORDER or ALERT line of AurumFunded in Terminal 16's MQL5 log (MQL5/Logs/YYYYMMDD.log). It is written to
#   logs/autopilot/demo-event.json ({at, kind, line}); relay.ps1 starts the judge for it (at the judge tier
#   for an ALERT) when the judge has not started since.
# - A work file the scripts wrote or rewrote: logs/autopilot/to-judge.json, tester-help.json.
# Then, when PAUSE is absent and no agent holds Local\AurumAgent, it starts relay.ps1 hidden; the relay decides who
# runs. The first run only notes where the log stands, so old lines never fire.
import ctypes
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOGDIR = REPO / "logs" / "autopilot"
STATE = LOGDIR / "dispatch-state.json"
EVENT = LOGDIR / "demo-event.json"
PAUSE = LOGDIR / "PAUSE"
WORK = ("to-judge.json", "tester-help.json")
MQL_LOGS = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "66FB7F5B174F9C3B2A690C49FF012FEB" / "MQL5" / "Logs"
ORDER = re.compile(r"\b(sold|bought|broke its range)\b")
ALERT = re.compile(r"closing everything until|at the final stop|halting|failed|retcode|no money|invalid stops", re.I)
DRY = "--dry-run" in sys.argv


def log(text):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {text}"
    if DRY:
        print(line)
        return
    with open(LOGDIR / f"{dt.date.today():%Y-%m-%d}_dispatch.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def agent_free():
    """True when no agent run holds Local\\AurumAgent (run-agent.ps1 holds it for the whole run)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, False, "Local\\AurumAgent")
    if not h:
        return True
    try:
        if k32.WaitForSingleObject(ctypes.c_void_p(h), 0) in (0, 0x80):
            k32.ReleaseMutex(ctypes.c_void_p(h))
            return True
        return False
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def read_log(path):
    raw = path.read_bytes()
    return raw.decode("utf-16") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", "replace")


def demo_events(state):
    """New AurumFunded ORDER/ALERT lines since the last call: [(at, kind, text)]. Updates state in place."""
    files = sorted(MQL_LOGS.glob("*.log")) if MQL_LOGS.exists() else []
    if not files:
        return []
    path = files[-1]
    lines = read_log(path).splitlines()
    first = "log" not in state
    if state.get("log") != path.name:
        state["log"], state["lines"] = path.name, 0
    start = len(lines) if first else state.get("lines", 0)
    if start > len(lines):          # the file was replaced: read it again
        start = 0
    state["lines"] = len(lines)
    out = []
    for line in lines[start:]:
        p = line.split("\t")
        if len(p) < 5 or "AurumFunded" not in p[3]:
            continue
        msg = p[4]
        kind = "ALERT" if ALERT.search(msg) else "order" if ORDER.search(msg) else None
        if kind:
            try:
                at = dt.datetime.strptime(path.stem + p[2][:8], "%Y%m%d%H:%M:%S")
            except ValueError:
                at = dt.datetime.now()
            out.append((at, kind, msg.strip()[:200]))
    return out


def new_work(state):
    """Work files written or rewritten since the last call."""
    seen = state.setdefault("work", {})
    out = []
    for name in WORK:
        f = LOGDIR / name
        m = f.stat().st_mtime if f.exists() else None
        if m and seen.get(name) != m:
            out.append(name)
        seen[name] = m
    return out


def main():
    state = load(STATE, {})
    first = "log" not in state
    events = demo_events(state)
    work = new_work(state)
    if first:
        log(f"dispatch: first run, watching {state.get('log')} from line {state.get('lines')}")
        work = []
    if events:
        # An ALERT outranks orders; the newest line of that kind is the one the relay reports.
        kind = "ALERT" if any(k == "ALERT" for _, k, _ in events) else "order"
        at, _, text = [e for e in events if e[1] == kind][-1]
        prev = load(EVENT, {})
        started = str(load(LOGDIR / "last-judge.json", {}).get("started", ""))
        # An ALERT the judge has not seen yet is not overwritten by a later order (the time moves on, so the
        # judge still wakes for both).
        if prev.get("kind") == "ALERT" and kind == "order" and prev.get("at", "") > started:
            kind, text = "ALERT", prev["line"]
        log(f"demo {kind}: {text}")
        if not DRY:
            EVENT.write_text(json.dumps({"at": at.isoformat(timespec="seconds"), "kind": kind, "line": text,
                                         "count": len(events)}, indent=1), encoding="utf-8")
    pending = load(EVENT, {}) if EVENT.exists() else {}
    last = load(LOGDIR / "last-judge.json", {})
    unhandled = bool(pending) and pending.get("at", "") > str(last.get("started", ""))
    # An event the relay could not act on yet (code-only mode, a limit) is retried every 5 minutes, not every minute.
    woke = state.get("woke", "")
    retry = unhandled and not first and (not woke or dt.datetime.now() - dt.datetime.fromisoformat(woke) >= dt.timedelta(minutes=5))
    if not (events or work or retry):
        if DRY:
            print("nothing new")
        if not DRY:
            STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
        return
    why = ", ".join([f"demo {pending.get('kind')}" for _ in [0] if unhandled] + work)
    if not why:
        why = "demo event (already handled)"
    if PAUSE.exists():
        log(f"dispatch: {why}; PAUSE set, not waking the relay")
    elif not agent_free():
        # Retried next minute: the work files stay new until the relay ran (state is kept unchanged for them).
        log(f"dispatch: {why}; an agent is busy, retry next minute")
        for name in work:
            state["work"][name] = None
    elif unhandled or work:
        log(f"dispatch: {why}; waking the relay")
        state["woke"] = dt.datetime.now().isoformat(timespec="seconds")
        if not DRY:
            ps = ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                  "-File", str(REPO / "tools" / "autopilot" / "relay.ps1")]
            subprocess.Popen(ps, cwd=REPO, creationflags=0x08000000)   # CREATE_NO_WINDOW
    if not DRY:
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:   # never let the keeper's minute loop see a crash dialog
        log(f"dispatch error: {type(e).__name__}: {e}")
