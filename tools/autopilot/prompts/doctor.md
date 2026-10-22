You are the doctor, running unattended from the daily scheduled task. Nobody can answer questions in this run:
decide, do the work, and stop.

1. Follow your agent instructions: check the agents, the relay, the queue, the tester, the demo and the budget; fix
   only what an agent may fix; write `docs/autopilot/gaps_report.md`.
2. Log each fix with `python tools/memory.py decide --role doctor ...`.
3. Commit only these files and push:
   `git add docs/autopilot/gaps_report.md` (and `docs/ideas/queue.jsonl`, `docs/HANDOFF.md` or
   `docs/memory/decisions.jsonl` only when this run changed them), then `git commit -m "Doctor <date>: <verdict>"`,
   then `git push origin HEAD`. If the push fails, leave the commit local and say so in your last line.
   Use plain `git ...` from the repo folder, one command per call (no `&&`, `;` or pipes).

Never edit tools/, .claude/, the gate, the EAs or .set files; never start, stop or register tasks or processes; never
look at results on or after 2025-10-13; never trade or touch credentials. Finish with one line: the verdict, how
many gaps you fixed and how many are open for Opus. Do not write a HANDOFF line: this run leaves the relay's
hand-over as it is.
