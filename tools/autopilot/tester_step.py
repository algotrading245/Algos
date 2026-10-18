# One tester step without Claude (owner 2026-10-18): collect a finished job, write its summary.md, start the next
# queued job, record it in docs/autopilot/runs.md and commit. Called by the keeper (every 2 minutes) and the relay
# (each tick). The tester agent runs only when this script cannot go on: it writes logs/autopilot/tester-help.json.
#
#   python tools/autopilot/tester_step.py [--dry-run]
#
# - Its own lock (mutex Local\AurumTester), so the agents (Local\AurumAgent) work while MT5 runs.
# - A collected job's id goes to logs/autopilot/to-judge.json; the relay then starts the orchestrator to judge it.
# - Never commits .htm, .png, summary.txt, job.json or .ex5; never touches a terminal except through
#   tools/run-tester.ps1 and tools/run-months.ps1, which refuse the holdout (AURUM_AGENT=1 is set for them).
import ctypes
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUEUE = REPO / "docs" / "autopilot" / "queue.json"
APPROVALS = REPO / "docs" / "autopilot" / "approvals.json"
RUNS = REPO / "docs" / "autopilot" / "runs.md"
LOGDIR = REPO / "logs" / "autopilot"
TO_JUDGE = LOGDIR / "to-judge.json"
HELP = LOGDIR / "tester-help.json"
PAUSE = LOGDIR / "PAUSE"
TESTER = r"C:\MetaTrader 5 - Tester"
DRY = "--dry-run" in sys.argv
PROBLEMS = re.compile(r"not found|cannot|failed|not enough money|no money|margin|invalid|error", re.I)
SECRET = re.compile(r"login|account|password|authoriz", re.I)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateMutexW.restype = ctypes.c_void_p
k32.OpenProcess.restype = ctypes.c_void_p

AGENT_MUTEX = "Local\\AurumAgent"


def agent_free():
    """True when no Claude agent run holds Local\\AurumAgent (run-agent.ps1 holds it for the whole run). The step
    scripts write queue.json, runs.md and commits, so they skip a step while an agent is busy rather than race its
    writes; the keeper calls again every minute, so a job is collected within a minute of the agent run ending.
    An abandoned mutex (WAIT_ABANDONED, a killed run-agent) counts as free."""
    h = k32.CreateMutexW(None, False, AGENT_MUTEX)
    if not h:
        return True
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) in (0, 0x80)
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def now():
    return dt.datetime.now()


def log(text):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    line = f"{now():%Y-%m-%d %H:%M:%S}  {text}\n"
    with open(LOGDIR / f"{now():%Y-%m-%d}_tester-step.log", "a", encoding="utf-8") as f:
        f.write(line)
    if DRY:
        print(text)


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_queue(q):
    # Same layout as the file the agents edit: 2-space indent, UTF-8, CRLF.
    if DRY:
        return
    text = json.dumps(q, indent=2, ensure_ascii=False).replace("\n", "\r\n") + "\r\n"
    QUEUE.write_bytes(text.encode("utf-8"))


def exe_alive(pid, exe=None, name=None):
    """True when process pid lives and its image is exe (full path) or has file name name."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        if k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code)) and code.value != 259:  # STILL_ACTIVE
            return False
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if not k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(size)):
            return False
        path = buf.value
        if exe:
            return os.path.normcase(path) == os.path.normcase(exe)
        if name:
            return Path(path).name.lower() == name.lower()
        return True
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def ps(script, args):
    env = dict(os.environ, AURUM_AGENT="1")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "tools" / script)] + args
    if DRY:
        print("would run:", " ".join(cmd))
        return 0, ""
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
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
    c = git("commit", "-m", message + "\n\nCommitted by tools/autopilot/tester_step.py", "--", *paths)
    if a.returncode or c.returncode:
        log(f"commit failed: {(a.stderr + c.stderr + c.stdout).strip()[:300]}")
        return
    p = git("push", "origin", "HEAD")
    if p.returncode:
        log(f"push failed (left for the next push): {p.stderr.strip()[:200]}")


def add_run(what, result):
    if DRY:
        print("runs.md:", what, "|", result)
        return
    with open(RUNS, "a", encoding="utf-8", newline="") as f:
        f.write(f"| {now():%Y-%m-%d %H:%M} | tester | {what} | {result} |\r\n")


def ask_help(job, error):
    log(f"help needed for {job}: {error}")
    if not DRY:
        HELP.write_text(json.dumps({"job": job, "error": error, "at": now().isoformat(timespec="seconds")},
                                   ensure_ascii=False, indent=2), encoding="utf-8")


def to_judge(job_id, match=None):
    """Queues a collected job for the orchestrator. match: True/False from the fixed expect check below, None when
    the expect text has no figures to check; the relay judges matches on Sonnet, everything else on Opus."""
    if DRY:
        return
    entries = read_json(TO_JUDGE, []) or []
    entries = [e if isinstance(e, dict) else {"id": e, "match": None} for e in entries]
    if any(e.get("id") == job_id for e in entries):
        return
    entries.append({"id": job_id, "match": match, "at": now().isoformat(timespec="seconds")})
    TO_JUDGE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%")
GOALX = re.compile(r"\d+(?:\.\d+)?x(?![\w.])")


def expect_figures(job, r, goal_share_pct=None):
    """The figures of a result to compare with the expect text: return / drawdown of a plain run, the share of
    months at the goal of a month series."""
    figs = {}
    if r:
        if r.get("return_pct") is not None:
            figs["return"] = float(r["return_pct"])
        if r.get("eq_dd_max_pct") is not None:
            figs["dd"] = float(r["eq_dd_max_pct"])
    if goal_share_pct is not None:
        figs["return"] = float(goal_share_pct)
    return figs


def expect_nums(expect):
    """The %-figures of an expect text: "22-32%" is a band (both ends), "-0.68%" is negative (the sign is the
    character right before the number), a goal multiple ("5x", "P(4x)") is dropped (the month series' goal share
    covers it)."""
    text = GOALX.sub(" ", expect or "")
    nums = []
    chunks = []
    pos = 0
    for m in RANGE.finditer(text):
        nums += [float(m.group(1)), float(m.group(2))]
        chunks.append(text[pos:m.start()])
        pos = m.end()
    chunks.append(text[pos:])
    for chunk in chunks:
        for m in PCT.finditer(chunk):
            before = chunk[m.start() - 1:m.start()] if m.start() else ""
            nums.append(float(m.group(1)) * (-1 if before in ("-", "\u2212") else 1))
    return nums


def expect_check(job, figs):
    """The owner's fixed tolerance (the orchestrator's hold-release rule): return within 15 percentage points of the
    expected one, drawdown no more than 5 points above it. Every %-figure in the expect text must be matched by the
    result's return (or a month series' goal share) within +-15, or by its equity drawdown within +5/-15. True when
    every figure matches; False when one does not; None when there is nothing to check (then the relay routes the
    judge to Opus). Deliberately mechanical: a wrong None/False only costs an Opus run."""
    if not figs:
        return None
    checked = False
    for x in expect_nums(job.get("expect") or ""):
        ok = (("return" in figs and abs(figs["return"] - x) <= 15)
              or ("dd" in figs and -15 <= figs["dd"] - x <= 5))
        if not ok:
            return False
        checked = True
    return True if checked else None


def rel(p):
    return str(Path(p)).replace("/", "\\")


def note_add(job, text):
    job["note"] = f"{text} {job.get('note') or ''}".strip()


def goal_of(job):
    if job.get("goal"):
        return float(job["goal"])
    try:
        m = re.search(r"^InpTarget\s*=\s*([\d.]+)", (REPO / job["preset"]).read_text(encoding="utf-8", errors="ignore"),
                      re.M)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return 5.0


# ---------------------------------------------------------------- summaries (figures only; the orchestrator judges)

def log_problems(folder):
    f = REPO / folder / "summary.txt"
    if not f.exists():
        return []
    seen, out = set(), []
    with open(f, "rb") as fh:  # the journal grows to 100 MB; this run's lines are at the end
        fh.seek(max(0, f.stat().st_size - 2_000_000))
        tail = fh.read().decode("utf-8", errors="replace")
    for line in tail.splitlines()[1:]:
        if PROBLEMS.search(line) and not SECRET.search(line):
            key = re.sub(r"\d", "", line)[-120:]
            if key not in seen:
                seen.add(key)
                out.append(line.strip()[:200])
    return out


def run_lines(r):
    by_year = ", ".join(f"{y} {v:+,.0f}" for y, v in (r.get("by_year") or {}).items())
    wd = r.get("worst_day") or {}
    dd = r.get("eq_dd_max_pct") or 0
    ret = r.get("return_pct")
    return [
        f"| Net profit | {r.get('net', 0):+,.2f} ({ret:+.1f}%) |" if ret is not None else f"| Net profit | {r.get('net')} |",
        f"| Trades / win rate | {r.get('trades')} / {r.get('win_rate')}% |",
        f"| Profit factor | {r.get('profit_factor')} |",
        f"| Max equity drawdown | {dd}% |",
        f"| Worst day | {wd.get('day', '?')} {wd.get('pct', '?')}% |",
        f"| Return per unit of drawdown | {ret / dd:.1f} |" if ret is not None and dd else "| Return per unit of drawdown | n/a |",
        f"| By year | {by_year} |",
        f"| History quality | {r.get('history_quality')} |",
    ]


def problems_section(folders):
    lines = ["", "## Log lines worth a look", ""]
    found = False
    for fo in folders:
        for p in log_problems(fo)[:12]:
            lines.append(f"- `{Path(fo).name}`: {p}")
            found = True
    if not found:
        lines.append("- None matched (not found, cannot, failed, margin, invalid, error).")
    return lines


def write_run_summary(job, folders):
    """folders: [folder] or [off, on] for a compare_set job."""
    out = [f"# {job['id']}: {job['expert']} {job.get('tag', '')} on {job['symbol']} {job.get('period', '')}", "",
           f"Written by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: figures only, the orchestrator judges.",
           f"Preset `{job.get('preset')}`, deposit {job.get('deposit')}, leverage 1:{job.get('leverage')}, "
           f"{job.get('from')} to {job.get('to') or 'the start day'}, set {job.get('set') or 'none'}"
           + (f", compare_set {job['compare_set']}" if job.get("compare_set") else "") + ".", ""]
    results = []
    for fo in folders:
        r = read_json(REPO / fo / "result.json")
        results.append(r)
        label = "legs on" if fo == job.get("folder_on") else ("legs off" if job.get("compare_set") else "Result")
        out += [f"## {label} (`{Path(fo).name}`)", "", "| Measure | Value |", "|---|---|"]
        out += run_lines(r) if r else ["| result.json | missing |"]
        out.append("")
    if len(results) == 2 and all(results):
        a, b = results
        rd = [(x.get("return_pct") or 0) / x["eq_dd_max_pct"] if x.get("eq_dd_max_pct") else None for x in results]
        if None not in rd:
            out += ["## On against off", "",
                    f"Return per unit of equity drawdown: off {rd[0]:.1f}, on {rd[1]:.1f} "
                    f"({'higher' if rd[1] > rd[0] else 'not higher'} with the legs on).", ""]
    out += ["## Expected (from the job)", "", job.get("expect") or "(no expect text)"]
    out += problems_section(folders)
    target = REPO / folders[-1] / "summary.md"
    if not DRY:
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
    return results


def write_months_summary(job, folder):
    r = read_json(REPO / folder / "months_result.json")
    if not r:
        return None
    goal = float(r.get("goal") or goal_of(job))
    months = r.get("months") or []
    mult = [(m["month"], m.get("multiple")) for m in months if m.get("multiple") is not None]
    n = len(mult)

    def count(x):  # counted from the multiples (months_summary.py's p_3x/p_5x come from the round field)
        return [mo for mo, v in mult if round(v, 2) >= x]

    out = [f"# {job['id']}: {job['expert']} {job.get('tag', '')}, {n} fresh-deposit months "
           f"({(job.get('months') or {}).get('from')}-{(job.get('months') or {}).get('to')})", "",
           f"Written by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: figures only, the orchestrator judges.",
           f"Preset `{job.get('preset')}`, {job['symbol']} {job.get('period')}, deposit {job.get('deposit')}, "
           f"leverage 1:{job.get('leverage')}, set {job.get('set') or 'none'}, goal {goal:g}x.", "",
           "## Result (counted from the month multiples, 2 decimals)", "", "| Measure | Value |", "|---|---|"]
    for x in sorted({3.0, 4.0, 5.0, goal}):
        c = count(x)
        out.append(f"| Months at {x:g}x or more | {len(c)} of {n} ({100 * len(c) / max(n, 1):.0f}%)"
                   + (f": {', '.join(c)}" if c and len(c) <= 8 else "") + " |")
    near = [f"{mo} ({v:.3f})" for mo, v in mult if goal * 0.97 <= v < goal - 0.005]
    out += [f"| Just short of the goal (within 3%) | {', '.join(near) or 'none'} |",
            f"| Median multiple | {r.get('median_multiple')} |",
            f"| Months below 0.5x | {len([1 for _, v in mult if v < 0.5])} of {n} |",
            f"| P(ruin) (script) | {100 * (r.get('p_ruin') or 0):.0f}% |",
            f"| Months with margin refusals | {r.get('months_with_margin_refusals')} |",
            f"| Months not run | {r.get('months_planned', n) - r.get('months_run', n)} |", "",
            "| Month | Multiple | Trades | Equity DD % | Margin refusals | Status |", "|---|---|---|---|---|---|"]
    for m in months:
        out.append(f"| {m['month']} | {m.get('multiple')} | {m.get('trades')} | {m.get('eq_dd_pct')} | "
                   f"{m.get('margin_refusals')} | {m.get('status')} |")
    out += ["", "## Expected (from the job)", "", job.get("expect") or "(no expect text)"]
    st = read_json(REPO / folder / "months.json", {}) or {}
    out += problems_section([d["Folder"] for d in st.get("Done") or [] if d.get("Folder")][-3:])
    if not DRY:
        (REPO / folder / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    headline = (f"{len(count(goal))} of {n} at {goal:g}x, median {r.get('median_multiple')}x, "
                f"{len([1 for _, v in mult if v < 0.5])} below 0.5x, ruin {100 * (r.get('p_ruin') or 0):.0f}%")
    share = 100 * len(count(goal)) / max(n, 1)
    return headline, share


def run_files(folder):
    return [f"{folder}/{n}".replace("\\", "/") for n in ("summary.md", "result.json", "tester.ini")]


def months_files(folder):
    files = [f"{folder}/{n}".replace("\\", "/") for n in ("months.json", "months_result.json", "summary.md")]
    st = read_json(REPO / folder / "months.json", {}) or {}
    for d in st.get("Done") or []:
        if d.get("Folder"):
            files += [f"{d['Folder']}/{n}".replace("\\", "/") for n in ("result.json", "tester.ini")]
    return files


# ---------------------------------------------------------------- collect

def busy(folder):
    if not folder:
        return False
    jf, mf = REPO / folder / "job.json", REPO / folder / "months.json"
    if jf.exists():
        j = read_json(jf, {}) or {}
        return exe_alive(j.get("Pid"), exe=j.get("Exe"))
    if mf.exists():
        m = read_json(mf, {}) or {}
        return exe_alive(m.get("Pid"), name="powershell.exe")
    return False


def collect(q, job):
    """Returns True when the queue changed."""
    jid = job["id"]
    folder = job.get("folder_on") or job.get("folder")
    if not folder:
        ask_help(jid, "running job without a folder")
        return False
    if busy(folder):
        return False
    is_months = bool(job.get("months"))
    code, out = ps("run-months.ps1" if is_months else "run-tester.ps1", ["-Collect", folder])
    if "running:" in out:
        return False
    if is_months:
        got = write_months_summary(job, folder)
        headline, share = got if got else (None, None)
        if headline is None:
            job["status"] = "failed"
            note_add(job, f"Collected by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: no months_result.json "
                          f"(collect output: {out.strip()[-200:]}).")
            add_run(f"Collected {jid}: no months_result.json", f"{jid} failed")
            ask_help(jid, f"months collect gave no months_result.json: {out.strip()[-300:]}")
            files = [str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))]
        else:
            job["status"] = "done"
            note_add(job, f"Collected by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: {headline}; "
                          "summary.md written.")
            add_run(f"Collected {jid} ({job['expert']} {job.get('tag')}, months): {headline}", f"{jid} done, needs judging")
            to_judge(jid, expect_check(job, expect_figures(job, None, goal_share_pct=share)))
            files = [str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))] + months_files(folder)
        save_queue(q)
        commit(files, f"Tester: {jid} collected ({job['status']})")
        return True

    result = REPO / folder / "result.json"
    if not result.exists():
        job["status"] = "failed"
        note_add(job, f"Collected by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: no report "
                      f"(collect output: {out.strip()[-200:]}).")
        add_run(f"Collected {jid}: no report in {Path(folder).name}", f"{jid} failed")
        ask_help(jid, f"collect gave no result.json: {out.strip()[-300:]}")
        save_queue(q)
        commit([str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))], f"Tester: {jid} failed, no report")
        return True

    if job.get("compare_set") and not job.get("folder_on"):
        # The off run is in: start the on run (set + compare_set) in the same job.
        started = start_run(job, list(job.get("set") or []) + list(job["compare_set"]), f"{job.get('tag')}_on")
        if started:
            job["folder_on"] = started
            note_add(job, f"Off run collected, on run started by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}.")
            add_run(f"Collected {jid} off run, started the on run", f"{jid} running")
            save_queue(q)
            commit([str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))] + run_files(folder),
                   f"Tester: {jid} off run collected, on run started")
        return True

    folders = [job["folder"], job["folder_on"]] if job.get("folder_on") else [folder]
    results = write_run_summary(job, folders)
    r = results[-1] or {}
    head = (f"net {r.get('net', 0):+,.0f} ({r.get('return_pct', 0):+.0f}%), {r.get('trades')} trades, "
            f"PF {r.get('profit_factor')}, equity DD {r.get('eq_dd_max_pct')}%")
    job["status"] = "done"
    note_add(job, f"Collected by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: {head}; summary.md written.")
    add_run(f"Collected {jid} ({job['expert']} {job.get('tag')}): {head}", f"{jid} done, needs judging")
    to_judge(jid, expect_check(job, expect_figures(job, r)))
    save_queue(q)
    files = [str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))]
    for fo in folders:
        files += run_files(fo)
    commit(files, f"Tester: {jid} collected ({head})")
    return True


# ---------------------------------------------------------------- start

def start_run(job, sets, tag):
    """Starts one detached run; returns its folder (relative) or None (the job is set failed or help is asked)."""
    args = ["-Expert", job["expert"], "-Symbol", job["symbol"], "-Preset", job["preset"],
            "-Period", str(job.get("period") or "M15"), "-Deposit", str(job.get("deposit") or 10000),
            "-Leverage", str(job.get("leverage") or 100), "-Tag", tag]
    if sets:
        args += ["-Set", ",".join(sets)]
    if job.get("months"):
        args += ["-FromMonth", job["months"]["from"], "-ToMonth", job["months"]["to"],
                 "-Goal", f"{goal_of(job):g}", "-Detach"]
        script = "run-months.ps1"
    else:
        args += ["-From", job.get("from") or "2024.01.01", "-To", job.get("to") or f"{now():%Y.%m.%d}", "-Detach"]
        script = "run-tester.ps1"
    code, out = ps(script, args)
    if DRY:
        return "backtests\\(dry-run)"
    if re.search(r"refused:.*holdout", out):
        job["status"] = "failed"
        note_add(job, f"Not started by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}: reaches the holdout.")
        return None
    m = re.search(r"-Collect\s+(.+?)\s*$", out, re.M) if "detached:" in out else None
    if not m:
        ask_help(job["id"], f"{script} did not detach (exit {code}): {out.strip()[-400:]}")
        return None
    folder = Path(m.group(1).strip())
    try:
        folder = folder.relative_to(REPO)
    except ValueError:
        pass
    return rel(folder)


def approved(item_id):
    a = read_json(APPROVALS, {}) or {}
    return any(i.get("id") == item_id and i.get("status") in ("approved", "applied") for i in a.get("items") or [])


def tester_ready():
    # The tester install needs one login by the owner (config\accounts.dat) before a job can start.
    base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    for d in base.glob("*") if base.exists() else []:
        o = d / "origin.txt"
        try:
            if o.exists() and o.read_text(encoding="utf-16", errors="ignore").strip().rstrip("\\").lower() == TESTER.lower():
                return (d / "config" / "accounts.dat").exists()
            if o.exists() and o.read_text(encoding="utf-8", errors="ignore").strip().strip("\ufeff").rstrip("\\").lower() == TESTER.lower():
                return (d / "config" / "accounts.dat").exists()
        except Exception:
            continue
    return False


def start_next(q):
    for job in q["jobs"]:
        if job.get("status") != "queued":
            continue
        if job.get("needs") and not approved(job["needs"]):
            continue
        if not tester_ready():
            log("queued job waits: the tester install has no login (config\\accounts.dat)")
            return False
        tag = f"{job.get('tag')}_off" if job.get("compare_set") else (job.get("tag") or job["id"])
        folder = start_run(job, list(job.get("set") or []), tag)
        if folder:
            job["status"] = "running"
            job["folder"] = folder
            note_add(job, f"Started by tools/autopilot/tester_step.py {now():%Y-%m-%d %H:%M}.")
            add_run(f"Started {job['id']} ({job['expert']} {tag}{', months' if job.get('months') else ''})",
                    f"{job['id']} running in {Path(folder).name}")
        elif job.get("status") == "failed":
            add_run(f"Did not start {job['id']}: reaches the holdout", f"{job['id']} failed")
        else:
            return False  # help asked; leave the job queued
        save_queue(q)
        commit([str(QUEUE.relative_to(REPO)), str(RUNS.relative_to(REPO))], f"Tester: {job['id']} {job['status']}")
        if job["status"] == "running":
            return True
    return False


def main():
    if PAUSE.exists():
        return
    if HELP.exists():
        return  # the tester agent has to look first; it deletes the file when done
    if not agent_free():
        log("skipped: an agent run is busy (Local\\AurumAgent); the next call tries again")
        return
    h = k32.CreateMutexW(None, False, "Local\\AurumTester")
    if not h or k32.WaitForSingleObject(ctypes.c_void_p(h), 0) not in (0, 0x80):
        return
    try:
        q = read_json(QUEUE)
        if not q:
            ask_help(None, "docs/autopilot/queue.json is unreadable")
            return
        for job in q["jobs"]:
            if job.get("status") == "running":
                collect(q, job)
                if job.get("status") == "running":
                    return  # one MT5 run at a time
        start_next(q)
    except Exception as e:  # anything unexpected goes to the tester agent
        ask_help(None, f"{type(e).__name__}: {e}")
    finally:
        k32.ReleaseMutex(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
