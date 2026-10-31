# The judge's mechanical half without an AI (owner 2026-10-18): when no AI provider can take a run (router.py
# available says none: every provider limited, keyless or missing), the relay calls this each tick instead of the
# judge, so collected jobs do not pile up and jobs waiting on them start.
#
#   python tools/autopilot/code_judge.py [--dry-run]
#
# - Takes only to-judge.json entries whose fixed expect check matched (match true): notes the confirmation on the job,
#   releases every "hold" job whose needs are all done and confirmed (the judge's rule: return within 15 pp,
#   drawdown no more than 5 above expect - which is exactly what match true means), records a memory decision, adds a
#   runs.md row, clears the entries (handoff.py --judged) and commits by path.
# - A mismatch or an unchecked result (match false/null) stays in to-judge.json for the judge: judging why a
#   result missed is research, not arithmetic. Candidates, settings and HANDOFF.md are never touched here.
# - Quiet when there is nothing to do; skips while an agent holds Local\AurumAgent.
import subprocess
import sys

import tester_step as ts

MARK = "Confirmed by code_judge"


def confirmed(job, ids):
    return job.get("status") == "done" and (job["id"] in ids or MARK in (job.get("note") or ""))


def main():
    if ts.PAUSE.exists() or not ts.agent_free():
        return
    entries = ts.read_json(ts.TO_JUDGE, []) or []
    ids = [e["id"] for e in entries if isinstance(e, dict) and e.get("match") is True]
    if not ids:
        return
    q = ts.read_json(ts.QUEUE)
    if not q or "jobs" not in q:
        ts.log("code_judge: queue.json unreadable")
        return
    jobs = {j["id"]: j for j in q["jobs"]}
    ids = [i for i in ids if i in jobs]
    if not ids:
        return
    for i in ids:
        ts.note_add(jobs[i], f"{MARK} {ts.now():%Y-%m-%d %H:%M} (no AI available): the fixed expect check matched "
                             "(return within 15 pp, drawdown no more than 5 above expect).")
    released = []
    for j in q["jobs"]:
        needs = j.get("needs")
        if j.get("status") != "hold" or not needs:
            continue
        needs = [needs] if isinstance(needs, str) else list(needs)
        if all(n in jobs and confirmed(jobs[n], ids) for n in needs):
            j["status"], j["needs"] = "queued", None
            ts.note_add(j, f"Released by code_judge {ts.now():%Y-%m-%d %H:%M}: {', '.join(needs)} done and confirmed.")
            released.append(j["id"])
    what = f"code_judge confirmed {', '.join(ids)}" + (f"; released {', '.join(released)}" if released else "")
    print(what)
    if ts.DRY:
        return
    ts.log(what)
    ts.save_queue(q)
    with open(ts.RUNS, "a", encoding="utf-8", newline="") as f:
        f.write(f"| {ts.now():%Y-%m-%d %H:%M} | code-judge | {what} (no AI available) | "
                f"{'; '.join(i + ' confirmed' for i in ids)} |\r\n")
    py = sys.executable
    subprocess.run([py, str(ts.REPO / "tools" / "memory.py"), "decide", "--role", "code-judge",
                    "--decision", what,
                    "--why", "No AI provider available; the fixed expect check matched, so the confirmation and the "
                             "hold release follow the judge's rule mechanically.",
                    "--evidence", "logs/autopilot/to-judge.json match true; summary.md of each job"],
                   cwd=ts.REPO, capture_output=True)
    subprocess.run([py, str(ts.REPO / "tools" / "autopilot" / "handoff.py"), "--judged", *ids],
                   cwd=ts.REPO, capture_output=True)
    ts.commit(["docs/autopilot/queue.json", "docs/autopilot/runs.md", "docs/memory/decisions.jsonl"],
              f"code_judge: {what}")


if __name__ == "__main__":
    main()
