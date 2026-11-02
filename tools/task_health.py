"""Health of the Windows scheduled tasks that run the system (owner 2026-11-02), for the dashboards.

    python tools/task_health.py        # prints one line per task

health() returns one row per task: name, state, last run, last result, next run, and a verdict: ok, running, late,
failed, disabled or missing. The rows are cached in logs/autopilot/tasks.json for a minute, since asking Task
Scheduler takes a second or two. Read only: it never starts, stops or changes a task.

The Aurum Keeper shows 0x800710E0 as its last result while it runs: its 15-minute re-trigger is refused because a copy
is already up (MultipleInstances IgnoreNew). That counts as ok.
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "logs" / "autopilot" / "tasks.json"
TTL = 60
# What each task does, so a page can say it in words.
TASKS = {
    "Aurum Keeper": "keeps T16 open, starts the script steps, the live feed and the research page",
    "Aurum Relay": "starts the next autopilot role (finder, builder, judge, tester)",
    "Aurum Doctor": "daily system check, 06:00",
    "Aurum Monitor": "demo forward-test check, Mon-Fri 22:15",
    "Aurum Portfolio": "weekly book review, Saturdays",
    "Dashboard": "the desk Command Center on 127.0.0.1:8765",
    "xauusddesk-operator": "old desk operator (switched off)",
}
REFUSED = 0x800710E0          # a new instance refused while one runs
NOT_YET = (0x41303, 0x41300)  # has not run yet / ready
RUNNING = 0x41301

_PS = r"""
$names = @(%s)
$out = foreach ($n in $names) {
  $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
  if (-not $t) { [pscustomobject]@{name=$n; missing=$true}; continue }
  $i = $t | Get-ScheduledTaskInfo
  [pscustomobject]@{name=$n; state="$($t.State)"; last=$i.LastRunTime.ToString('s'); result=[int64]$i.LastTaskResult;
    next=$(if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { $null }); missed=$i.NumberOfMissedRuns}
}
$out | ConvertTo-Json -Compress
"""


def _query():
    names = ",".join("'" + n.replace("'", "''") + "'" for n in TASKS)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS % names],
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    rows = json.loads(r.stdout or "[]")
    return rows if isinstance(rows, list) else [rows]


def _verdict(row, now):
    if row.get("missing"):
        return "missing", "no such task"
    state, res = row.get("state", ""), row.get("result", 0) & 0xFFFFFFFF
    if state == "Disabled":
        return "disabled", "switched off"
    if state == "Running":
        return "running", "running now"
    nxt = row.get("next")
    if nxt and datetime.fromisoformat(nxt) < now and (now - datetime.fromisoformat(nxt)).total_seconds() > 900:
        return "late", f"next run {nxt[5:16].replace('T', ' ')} has passed"
    if res in (0, REFUSED, RUNNING) or res in NOT_YET:
        return "ok", "last run ok"
    return "failed", f"last result 0x{res:08X}"


def health(fresh=False):
    """The task rows (see the module doc), from the cache when it is under a minute old."""
    try:
        if not fresh and CACHE.exists() and time.time() - CACHE.stat().st_mtime < TTL:
            return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    now = datetime.now()
    try:
        rows = _query()
    except Exception as e:
        return {"error": str(e), "rows": []}
    out = []
    for r in rows:
        v, why = _verdict(r, now)
        res = (r.get("result") or 0) & 0xFFFFFFFF
        out.append({"name": r["name"], "does": TASKS.get(r["name"], ""), "state": r.get("state"),
                    "last": r.get("last"), "next": r.get("next"), "result": f"0x{res:08X}", "verdict": v, "why": why})
    data = {"checked": now.isoformat(timespec="seconds"), "rows": out}
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(CACHE)
    except OSError:
        pass
    return data


if __name__ == "__main__":
    d = health(fresh="--cached" not in sys.argv)
    for r in d.get("rows", []):
        print(f"{r['verdict']:<9} {r['name']:<20} last {r['last'] or '-':<19} next {r['next'] or '-':<19} {r['why']}")
    if d.get("error"):
        print("error:", d["error"])
