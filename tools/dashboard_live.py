"""Live feed for the dashboard (owner 2026-10-22: "watch what each agent is doing, updated every second").

Writes dashboard/live.js every second: per role agent its state (logs/autopilot/last-<role>.json), the tool it is
running now and its last actions (read as they arrive from logs/autopilot/events/<start>_<role>.jsonl, which
run-agent.ps1 appends), and the tail of its run log; plus the relay and the script steps' logs. Every 60 s it also
rebuilds dashboard/data.js with tools/dashboard.py, so the other tabs follow within a minute. The page reloads
live.js each second (a script tag, so it works from a file:// page) and data.js when it changes.

    python tools/dashboard_live.py           # run until stopped; a second copy exits at once
    python tools/dashboard_live.py --once    # write live.js once and exit

The keeper (tools/autopilot/keeper.ps1) starts it every minute; the lock keeps one copy.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "autopilot"
EVENTS = LOG / "events"
OUT = ROOT / "dashboard"
LIVE = OUT / "live.js"
DATA = OUT / "data.js"
LOCK = LOG / "dashboard-live.lock"
ROLES = ["orchestrator", "miner", "researcher", "worker", "scanner", "tester", "fidelity", "monitor"]
STEPS = ["relay", "keeper-steps", "idea-engine", "dispatch", "tester-step", "scanner-step", "keeper"]
REBUILD_S = 60
KEEP_ACTIONS = 40
ROOTS = (str(ROOT) + "\\", str(ROOT).replace("\\", "/") + "/")


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def rel(p):
    p = str(p or "")
    for r in ROOTS:
        if p.lower().startswith(r.lower()):
            return p[len(r):]
    return p


def describe(name, inp):
    """One line for a tool call: the command, file or query it was given."""
    if name == "Bash":
        return clip(inp.get("command", ""), 220)
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        extra = f" @{inp['offset']}" if inp.get("offset") else ""
        return rel(inp.get("file_path", "")) + extra
    if name == "Grep":
        return clip(f"{inp.get('pattern', '')}  in {rel(inp.get('path', '.'))}", 220)
    if name == "Glob":
        return clip(inp.get("pattern", ""), 220)
    if name == "WebFetch":
        return clip(inp.get("url", ""), 220)
    if name == "WebSearch":
        return clip(inp.get("query", ""), 220)
    if name in ("Agent", "Task"):
        return clip(inp.get("description") or inp.get("prompt", ""), 220)
    if name == "PowerShell":
        return clip(inp.get("command", ""), 220)
    return clip(json.dumps(inp, ensure_ascii=False), 220)


def result_text(c):
    if isinstance(c, list):
        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return clip(c or "", 260)


class Stream:
    """Reads one events file incrementally and keeps the agent's recent actions."""

    def __init__(self, path):
        self.path, self.pos, self.rest = path, 0, b""
        self.actions, self.pending, self.progress = [], {}, None
        self.result, self.model, self.n_tools = None, None, 0

    def update(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size <= self.pos:
            return
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            chunk = f.read(size - self.pos)
        self.pos = size
        lines = (self.rest + chunk).split(b"\n")
        self.rest = lines.pop()
        for ln in lines:
            if b'"stream_event"' in ln[:60] or not ln.strip():
                continue
            try:
                self.event(json.loads(ln))
            except ValueError:
                continue
        if len(self.actions) > KEEP_ACTIONS * 3:
            self.actions = self.actions[-KEEP_ACTIONS:]

    def event(self, e):
        t = e.get("type")
        if t == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                bt = b.get("type")
                if bt == "tool_use":
                    a = {"k": "tool", "name": b.get("name", "?"), "what": describe(b.get("name"), b.get("input") or {}),
                         "open": True}
                    self.actions.append(a)
                    self.pending[b.get("id")] = a
                    self.n_tools += 1
                elif bt == "text" and (b.get("text") or "").strip():
                    self.actions.append({"k": "text", "what": clip(b["text"], 400)})
        elif t == "user":
            content = (e.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        a = self.pending.pop(b.get("tool_use_id"), None)
                        if a is not None:
                            a["open"] = False
                            a["result"] = result_text(b.get("content"))
                            a["err"] = bool(b.get("is_error"))
        elif t == "tool_progress":
            self.progress = {"tool": e.get("tool_name"), "secs": e.get("elapsed_time_seconds")}
        elif t == "system" and e.get("subtype") == "init":
            self.model = e.get("model")
        elif t == "system" and e.get("subtype") == "task_started":
            self.actions.append({"k": "task", "what": clip(e.get("description", "sub-task"), 220)})
        elif t == "result":
            self.result = {"text": clip(e.get("result", ""), 600), "cost": e.get("total_cost_usd"),
                           "turns": e.get("num_turns"), "error": bool(e.get("is_error"))}
            for a in self.pending.values():
                a["open"] = False
            self.pending.clear()

    def view(self):
        cur = None
        for a in reversed(self.actions):
            if a.get("open"):
                cur = {"name": a["name"], "what": a["what"]}
                if self.progress and self.progress.get("tool") == a["name"]:
                    cur["secs"] = self.progress.get("secs")
                break
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        return {"file": self.path.name, "mtime": mtime, "model": self.model, "tools": self.n_tools, "current": cur,
                "actions": self.actions[-KEEP_ACTIONS:], "result": self.result}


_tails = {}


def tail(path, n, nbytes=24000):
    """Last n lines of a text file, cached by (mtime, size)."""
    try:
        st = path.stat()
    except OSError:
        return []
    key = (st.st_mtime, st.st_size)
    hit = _tails.get(path)
    if hit and hit[0] == key:
        return hit[1]
    with open(path, "rb") as f:
        f.seek(max(0, st.st_size - nbytes))
        data = f.read().decode("utf-8", "replace")
    lines = data.splitlines()
    if st.st_size > nbytes:
        lines = lines[1:]
    out = [clip(l, 400) if len(l) > 400 else l for l in lines[-n:]]
    _tails[path] = (key, out)
    return out


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def newest_log(pattern):
    files = sorted(LOG.glob(pattern))
    return files[-1] if files else None


_streams = {}


def snapshot(rebuilding):
    newest = {}
    try:
        for e in os.scandir(EVENTS):
            if e.name.endswith(".jsonl") and "_" in e.name:
                role = e.name[:-6].split("_", 1)[1]
                if e.name > newest.get(role, ""):
                    newest[role] = e.name
    except OSError:
        pass
    roles = {}
    for role in ROLES + sorted(set(newest) - set(ROLES)):
        st = read_json(LOG / f"last-{role}.json") or {}
        started, ended = st.get("started"), st.get("ended")
        running = bool(started) and (not ended or started > ended)
        act = None
        if role in newest:
            path = EVENTS / newest[role]
            s = _streams.get(role)
            if s is None or s.path != path:
                s = _streams[role] = Stream(path)
            s.update()
            act = s.view()
        log = newest_log(f"*_agent-{role}.log")
        roles[role] = {
            "running": running,
            "state": {k: st.get(k) for k in ("started", "ended", "model", "tier", "provider", "exit", "reason",
                                             "runs_today", "next", "idle", "failed", "timed_out")},
            "activity": act,
            "log": tail(log, 40) if log else [],
            "log_file": log.name if log else None,
        }
    today = dt.date.today().isoformat()
    steps = {}
    for name in STEPS:
        p = LOG / f"{today}_{name}.log"
        if p.exists():
            steps[name] = tail(p, 14)
    try:
        data_mtime = None if rebuilding else DATA.stat().st_mtime
    except OSError:
        data_mtime = None
    return {"generated": time.time(), "generated_iso": dt.datetime.now().isoformat(timespec="seconds"),
            "data_mtime": data_mtime, "relay": read_json(LOG / "relay.json"),
            "paused": (LOG / "PAUSE").exists(), "roles": roles, "steps": steps}


def write(snap):
    OUT.mkdir(exist_ok=True)
    tmp = LIVE.with_suffix(".js.tmp")
    tmp.write_text("window.AURUM_LIVE = " + json.dumps(snap, ensure_ascii=False) + ";\n", encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, LIVE)
            return
        except PermissionError:                                         # the browser may hold the file for a moment
            time.sleep(0.05)


def lock():
    """Hold an OS lock on LOCK for the life of the process; None when another copy has it."""
    LOG.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def rebuild():
    flags = 0x08000000 if os.name == "nt" else 0                        # CREATE_NO_WINDOW
    return subprocess.Popen([sys.executable, str(ROOT / "tools" / "dashboard.py")], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def main():
    if "--once" in sys.argv:
        write(snapshot(False))
        return
    held = lock()
    if held is None:
        return
    proc, last_build = None, 0.0
    while True:
        t0 = time.time()
        if proc is not None and proc.poll() is not None:
            proc = None
        if proc is None and t0 - last_build >= REBUILD_S:
            try:
                proc, last_build = rebuild(), t0
            except OSError:
                last_build = t0
        try:
            write(snapshot(proc is not None))
        except Exception as ex:                                         # keep the loop alive; say why on the page
            try:
                write({"generated": time.time(), "error": f"{type(ex).__name__}: {ex}"})
            except Exception:
                pass
        time.sleep(max(0.05, 1.0 - (time.time() - t0)))


if __name__ == "__main__":
    main()
