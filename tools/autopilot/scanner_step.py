# One scanner step without Claude (owner 2026-10-18): work through the pending scan requests in
# docs/autopilot/scan_requests.json — run tools/edge_scan.py for each family, tools/gates.py for every survivor,
# record the outcome in docs/autopilot/scans.md, commit, and mark the request done. The scanner agent only runs
# when this script raises its flag (logs/autopilot/scanner-flag.json): a survivor passed every gate, or a scan broke.
# Called by the keeper (every minute; the script throttles itself to one attempt per $MIN_MINUTES) and by hand.
#
#   python tools/autopilot/scanner_step.py [--dry-run] [--force]
#
# - Its own lock (mutex Local\AurumScanner), so the agents (Local\AurumAgent) work while a scan runs.
# - Requests: {"id": "s1", "family": "slot|own|cal|vol|all", "why": "...", "status": "pending|done|failed"}.
#   The orchestrator appends them (Write on docs/** is allowed to it); a family already scanned is refused here
#   (docs/trials.jsonl remembers every scan: a repeat only raises the DSR bar for everyone).
# - Never touches a terminal, the queue or an EA.
import ctypes
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUESTS = REPO / "docs" / "autopilot" / "scan_requests.json"
SCANS = REPO / "docs" / "autopilot" / "scans.md"
TRIALS = REPO / "docs" / "trials.jsonl"
LOGDIR = REPO / "logs" / "autopilot"
FLAG = LOGDIR / "scanner-flag.json"
PAUSE = LOGDIR / "PAUSE"
STATE = LOGDIR / "scanner-state.json"
GATES = REPO / "docs" / "gates"
FAMILIES = ("slot", "own", "cal", "vol")
MIN_MINUTES = 10          # at most one scan attempt this often (a scan itself takes many minutes)
DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateMutexW.restype = ctypes.c_void_p


def agent_free():
    """True when no Claude agent run holds Local\\AurumAgent (run-agent.ps1). The script shares files with the
    agents (docs/candidates.json, commits), so it waits for a busy agent before a scan and skips a step otherwise;
    an abandoned mutex (a killed run-agent) counts as free."""
    h = k32.CreateMutexW(None, False, "Local\\AurumAgent")
    if not h:
        return True
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) in (0, 0x80)
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def wait_for_agent():
    import time
    while not agent_free():
        log("an agent run is busy (Local\\AurumAgent); waiting a minute before the next scan step")
        time.sleep(60)


def now():
    return dt.datetime.now()


def log(text):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    line = f"{now():%Y-%m-%d %H:%M:%S}  {text}\n"
    with open(LOGDIR / f"{now():%Y-%m-%d}_scanner-step.log", "a", encoding="utf-8") as f:
        f.write(line)
    if DRY:
        print(text)


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(p, obj):
    if DRY:
        return
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def py(script, *args, timeout=7200):
    cmd = [sys.executable, str(REPO / "tools" / script), *args]
    if DRY:
        print("would run:", " ".join(cmd))
        return 0, ""
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def commit(paths, message):
    if DRY:
        print("would commit:", message, paths)
        return
    paths = [p for p in dict.fromkeys(paths) if (REPO / p).exists()]
    if not paths:
        return
    a = git("add", "--", *paths)
    c = git("commit", "-m", message + "\n\nCommitted by tools/autopilot/scanner_step.py", "--", *paths)
    if a.returncode or c.returncode:
        log(f"commit failed: {(a.stderr + c.stderr + c.stdout).strip()[:300]}")
        return
    p = git("push", "origin", "HEAD")
    if p.returncode:
        log(f"push failed (left for the next push): {p.stderr.strip()[:200]}")


def flag(reason, request=None, passed=()):
    log(f"scanner agent needed: {reason}")
    if not DRY:
        save_json(FLAG, {"work": True, "reason": reason, "request": request, "passed": list(passed),
                         "at": now().isoformat(timespec="seconds")})


def already_scanned(family):
    """A family this script or the scanner agent ran before (edge_scan logs 'edge_scan:<families>' in trials.jsonl)."""
    if not TRIALS.exists():
        return False
    with TRIALS.open(encoding="utf-8") as f:
        for line in f:
            try:
                t = json.loads(line)
            except Exception:
                continue
            if str(t.get("id", "")).startswith("edge_scan:"):
                fams = str(t["id"]).split(":", 1)[1].split("+")
                if family in fams or "all" in fams:
                    return True
    return False


def run_request(req):
    """Returns (status, result line)."""
    rid = req.get("id") or "?"
    fam = (req.get("family") or "all").lower()
    if fam != "all":
        if fam not in FAMILIES:
            return "failed", f"{rid}: unknown family '{fam}'"
        if already_scanned(fam):
            return "failed", (f"{rid}: family {fam} was scanned before (docs/trials.jsonl); a repeat only raises "
                              f"the DSR bar — refused")
    else:
        fams = [f for f in FAMILIES if not already_scanned(f)]
        if not fams:
            return "failed", f"{rid}: every family was scanned before — refused"
        fam = fams  # run the unscanned families one by one below

    survivors, lines = [], []
    for f in (fam if isinstance(fam, list) else [fam]):
        wait_for_agent()
        code, out = py("edge_scan.py", "--family", f)
        wrote = re.findall(r"wrote marketdata/candidates/([\w.-]+?)\.csv", out)
        m = re.search(r"rules tried (\d+).*?: (\d+)", out)
        tried, found = (m.group(1), m.group(2)) if m else ("?", "?")
        lines.append(f"{f}: {tried} rules tried, {found} survivors, wrote {', '.join(wrote) or 'none'}")
        if code != 0:
            flag(f"scan {f} failed (exit {code}): {out.strip()[-300:]}", rid)
            return "failed", f"{rid} {f}: edge_scan.py exit {code}" + (" (" + "; ".join(lines) + ")" if lines else "")
        survivors += wrote

    passed = []
    for cid in survivors:
        wait_for_agent()
        code, out = py("gates.py", cid)
        verdict = (read_json(GATES / f"{cid}.json") or {}).get("verdict") or f"gates.py exit {code}"
        lines.append(f"gates {cid}: {verdict}")
        if code != 0 and not (GATES / f"{cid}.json").exists():
            flag(f"gates.py failed for {cid} (exit {code}): {out.strip()[-300:]}", rid)
            return "failed", f"{rid}: gates.py {cid} exit {code}"
        if str(verdict).startswith("PASS"):
            passed.append(cid)

    result = f"{rid} ({req.get('why') or 'no reason given'}): " + "; ".join(lines)
    if passed:
        flag(f"{', '.join(passed)} passed every gate", rid, passed)
    return "done", result


def main():
    if PAUSE.exists():
        return
    if not REQUESTS.exists():
        return
    st = read_json(STATE, {}) or {}
    try:
        last = dt.datetime.fromisoformat(st.get("last", ""))
    except ValueError:
        last = None
    if not FORCE and last and (now() - last).total_seconds() < MIN_MINUTES * 60:
        return
    h = k32.CreateMutexW(None, False, "Local\\AurumScanner")
    if not h or k32.WaitForSingleObject(ctypes.c_void_p(h), 0) not in (0, 0x80):
        return
    try:
        data = read_json(REQUESTS, {}) or {}
        reqs = data.get("requests") if isinstance(data, dict) else data
        if not isinstance(reqs, list):
            return
        save_json(STATE, {"last": now().isoformat(timespec="seconds")})
        changed = False
        for req in reqs:
            if not isinstance(req, dict) or req.get("status") != "pending":
                continue
            log(f"scan request {req.get('id')}: family {req.get('family')}")
            status, result = run_request(req)
            req["status"] = status
            req["result"] = result
            req["when"] = now().isoformat(timespec="seconds")
            changed = True
            with SCANS.open("a", encoding="utf-8", newline="") as f:
                f.write(f"| {now():%Y-%m-%d %H:%M} | {result} |\n")
            log(result)
        if changed:
            wait_for_agent()
            save_json(REQUESTS, data if isinstance(data, dict) else reqs)
            commit([str(REQUESTS.relative_to(REPO)), str(SCANS.relative_to(REPO)),
                    str(TRIALS.relative_to(REPO)), "docs/candidates.json"] +
                   [f"docs/gates/{p.name}" for p in sorted(GATES.glob("scan_*.json"))],
                   "Scanner: script scan run")
    except subprocess.TimeoutExpired as e:
        flag(f"a scan timed out: {e}", None)
    except Exception as e:
        flag(f"{type(e).__name__}: {e}", None)
    finally:
        k32.ReleaseMutex(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
