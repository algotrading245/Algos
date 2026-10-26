"""The runner (DESIGN.md section 6): drains the job queue one job at a time, each job one or more claude runs.

The clock launches it when jobs wait (jobs.launch); it holds Local\\AurumDesk so only one runs, and exits when the
queue is empty. A job becomes agent runs like this:
  brief        each pod named in the job, then the head trader if any ticket is proposed
  wake         the pod, then the head trader if a ticket is proposed
  debrief      the debrief
  weekly       scorekeeper.weekly() (code), then the head trader (Saturday review, playbook fold-in)
  scorekeeper  scorekeeper.daily() (code), then a short scorekeeper note
  monitor      the monitor
Each run's prompt is agents/guide.md + the role's prompt + brief.build(role, job). A role whose daily token budget is
spent is skipped (why "budget"). Transcripts go to logs/desk/runs/<job>_<role>.jsonl.

python -m desk.runner drain
python -m desk.runner once ROLE [KIND]     one run now, for testing a prompt by hand
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from desk import brief, clocks, journal, jobs, mutex, paths

AGENTS = paths.DESK / "agents"
SETTINGS = AGENTS / "settings.json"
BUDGET = paths.STATE / "budget.json"
HEAD = brief.HEAD


def group(role, cfg):
    return "pod" if role in cfg.get("pods", {}) else role


def _cfg_for(key, role, cfg, default):
    return cfg.get(key, {}).get(group(role, cfg), default)


def weighted(usage):
    u = usage or {}
    return int(u.get("input_tokens", 0) + u.get("output_tokens", 0) + u.get("cache_creation_input_tokens", 0)
               + 0.1 * u.get("cache_read_input_tokens", 0))


def spent(role, cfg, t=None):
    return paths.read_json(BUDGET, {}).get(clocks.trading_day(t).isoformat(), {}).get(group(role, cfg), 0)


def add_spend(role, tokens, cfg, t=None):
    day = clocks.trading_day(t)
    cutoff = (day - dt.timedelta(days=14)).isoformat()
    b = {d: v for d, v in paths.read_json(BUDGET, {}).items() if d >= cutoff}
    g = b.setdefault(day.isoformat(), {})
    g[group(role, cfg)] = g.get(group(role, cfg), 0) + int(tokens)
    paths.write_json(BUDGET, b)


def over_budget(role, cfg, t=None):
    limit = cfg.get("budgets", {}).get(group(role, cfg))
    return limit is not None and spent(role, cfg, t) >= limit


def prompt_for(role, job):
    """guide.md, then pod.md for any pod, then the role's own file, then the brief and the job."""
    names = ["guide.md"] + (["pod.md"] if role in paths.config().get("pods", {}) else []) + [f"{role}.md"]
    parts = [(AGENTS / n).read_text(encoding="utf-8") for n in names if (AGENTS / n).exists()]
    parts.append(brief.build(role, job))
    parts.append("## The job\n```json\n" + json.dumps(job, indent=1, default=str) + "\n```\n")
    return "\n\n".join(parts)


def claude_exe():
    p = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    if p.exists():
        return str(p)
    return shutil.which("claude.exe") or shutil.which("claude") or "claude"


def _kill_tree(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def call(role, model, prompt, turns, minutes, job):
    """Run claude once. Returns {ok, tokens, result, why}. Tests replace this."""
    cmd = [claude_exe(), "-p", "--settings", str(SETTINGS), "--permission-mode", "dontAsk",
           "--permission-prompts", "none", "--max-turns", str(turns), "--output-format", "stream-json", "--verbose",
           "--strict-mcp-config", "--disable-slash-commands", "--no-chrome", "--setting-sources", "project,local",
           "--model", model]
    env = dict(os.environ, AURUM_AGENT="1", ECC_GATEGUARD="off", AURUM_DESK_ROLE=role)
    paths.RUNS.mkdir(parents=True, exist_ok=True)
    out = paths.RUNS / f"{job['id']}_{role}.jsonl"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    deadline = clocks.now() + dt.timedelta(minutes=minutes)
    with open(out, "w", encoding="utf-8") as f:
        p = subprocess.Popen(cmd, cwd=str(paths.ROOT), env=env, stdin=subprocess.PIPE, stdout=f,
                             stderr=subprocess.STDOUT, creationflags=flags)
        r = paths.read_json(jobs.RUNNER, {})
        r.update(pid=os.getpid(), job=job["id"], role=role, agent_pid=p.pid,
                 deadline=deadline.isoformat(timespec="seconds"))
        paths.write_json(jobs.RUNNER, r)
        try:
            p.stdin.write(prompt.encode("utf-8"))
            p.stdin.close()
        except OSError:
            pass
        try:
            code = p.wait(timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            _kill_tree(p.pid)
            code = None
    r = paths.read_json(jobs.RUNNER, {})
    r.pop("agent_pid", None)
    paths.write_json(jobs.RUNNER, r)
    usage, result, err = {}, "", False
    for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            usage, result, err = ev.get("usage") or {}, ev.get("result") or "", bool(ev.get("is_error"))
    if code is None:
        return {"ok": False, "tokens": weighted(usage), "result": result, "why": f"timeout after {minutes} min"}
    return {"ok": code == 0 and not err, "tokens": weighted(usage), "result": result,
            "why": "" if code == 0 and not err else f"exit {code}"}


def run_agent(role, job, cfg):
    """One agent run inside a job. Returns 'ok', 'failed' or 'budget'."""
    if over_budget(role, cfg):
        journal.log("agent_skipped", job=job["id"], role=role, why="budget")
        return "budget"
    model = _cfg_for("models", role, cfg, "sonnet")
    turns = _cfg_for("max_turns", role, cfg, 30)
    minutes = _cfg_for("timeout_min", role, cfg, 20)
    t0 = clocks.now()
    try:
        res = call(role, model, prompt_for(role, job), turns, minutes, job)
    except Exception as e:  # a missing claude.exe or a broken prompt fails the run, not the runner
        res = {"ok": False, "tokens": 0, "result": "", "why": f"{type(e).__name__}: {e}"}
    add_spend(role, res.get("tokens", 0), cfg)
    journal.log("agent_run", job=job["id"], kind=job["kind"], role=role, model=model, ok=res["ok"],
                tokens=res.get("tokens", 0), seconds=round((clocks.now() - t0).total_seconds()),
                why=res.get("why", ""), result=(res.get("result") or "")[:500])
    if role == "monitor":
        alert(res.get("result") or "", t0)
    return "ok" if res["ok"] else "failed"


def alert(text, t):
    """A monitor run whose summary has a line starting ALERT goes to the journal and to reports/ALERT.md for the owner."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().upper().startswith("ALERT")]
    if not lines:
        return []
    journal.log("alert", lines=lines)
    paths.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(paths.REPORTS / "ALERT.md", "a", encoding="utf-8") as f:
        f.write(f"\n## {t.isoformat(timespec='minutes')}\n" + "\n".join(f"- {ln}" for ln in lines) + "\n")
    return lines


def _with_head(roles, job, cfg):
    """Run roles, then the head trader when something waits for approval."""
    out = [run_agent(r, job, cfg) for r in roles]
    if brief.proposed():
        out.append(run_agent(HEAD, job, cfg))
    return out


def run_job(job, cfg):
    kind = job["kind"]
    jobs.mark(job["id"], "started")
    try:
        if kind == "brief":
            res = _with_head(job.get("pods") or [], job, cfg)
        elif kind == "wake":
            res = _with_head([job["pod"]], job, cfg)
        elif kind == "debrief":
            res = [run_agent("debrief", job, cfg)]
        elif kind == "weekly":
            from desk import scorekeeper
            scorekeeper.weekly()
            res = [run_agent(HEAD, job, cfg)]
        elif kind == "scorekeeper":
            from desk import scorekeeper
            scorekeeper.daily()
            res = [run_agent("scorekeeper", job, cfg)]
        elif kind == "monitor":
            res = [run_agent("monitor", job, cfg)]
        else:
            jobs.mark(job["id"], "skipped", why=f"unknown kind {kind}")
            return "skipped"
    except Exception as e:
        journal.log("job_error", job=job["id"], kind=kind, error=f"{type(e).__name__}: {e}")
        jobs.mark(job["id"], "failed", why=f"{type(e).__name__}: {e}")
        return "failed"
    if res and all(r == "budget" for r in res):
        jobs.mark(job["id"], "skipped", why="budget")
        return "skipped"
    if "failed" in res:
        jobs.mark(job["id"], "failed", why=f"{res.count('failed')} of {len(res)} runs failed")
        return "failed"
    jobs.mark(job["id"], "done")
    return "done"


def drain(limit=50):
    """Run waiting jobs until none are left. Returns how many ran, or -1 if another runner holds the mutex."""
    with mutex.hold(jobs.RUNNER_MUTEX) as mine:
        if not mine:
            return -1
        paths.write_json(jobs.RUNNER, {"pid": os.getpid(), "started": clocks.now().isoformat(timespec="seconds")})
        n = 0
        while n < limit:
            jobs.expire_stale()
            waiting = jobs.pending()
            if not waiting:
                break
            cfg = paths.config()
            if paths.KILL.exists() and waiting[0]["kind"] not in ("monitor", "debrief"):
                jobs.mark(waiting[0]["id"], "skipped", why="desk halted")
                continue
            run_job(waiting[0], cfg)
            n += 1
        paths.write_json(jobs.RUNNER, {"pid": None, "finished": clocks.now().isoformat(timespec="seconds"), "ran": n})
        return n


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["drain"]:
        n = drain()
        print(json.dumps({"ran": n}))
        return 0 if n >= 0 else 1
    if argv[:1] == ["once"] and len(argv) > 1:
        cfg = paths.config()
        job = {"id": "manual" + clocks.now().strftime("%H%M%S"), "kind": argv[2] if len(argv) > 2 else "manual"}
        print(json.dumps({"result": run_agent(argv[1], job, cfg)}))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
