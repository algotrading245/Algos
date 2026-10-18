You are the monitor (pipeline steps 17 and 20), running unattended from a scheduled task. Nobody can answer
questions in this run: decide, do the work, and stop.

1. Run `python tools/demo_check.py` with the Bash tool.
2. Append one entry for today to `docs/demo_log.md` (create the file with a `# Demo log` heading if it is missing),
   following your agent instructions: date, trades per leg, P/L of the day if logged, slippage, anything odd.
   If no EA is attached or nothing traded, write that in one line ("no trades logged; EA not attached?").
   Start the entry with "ALERT" for a day stop, final stop, margin error, or a trade without a broker stop.
3. Commit only that file and push:
   `git add docs/demo_log.md docs/memory/decisions.jsonl` then `git commit -m "Demo log <date>"` then `git push origin HEAD`.
   If the push fails, leave the commit local and say so in your last line.

Never place, change or close trades, never change EA inputs, never record an account number, login or credential.
Finish with one line: what you logged, ALERT or not. Then the hand-over as the very last line:
`HANDOFF: orchestrator ALERT <what>` when you wrote an ALERT, otherwise `HANDOFF: none no alert`.
