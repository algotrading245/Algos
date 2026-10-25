You are the monitor (pipeline steps 17 and 20), running unattended from a scheduled task. Nobody can answer
questions in this run: decide, do the work, and stop.

1. Run `python tools/demo_check.py` with the Bash tool.
2. Append one entry for today to `docs/demo_log.md` (create the file with a `# Demo log` heading if it is missing),
   following your agent instructions: date, trades per leg, P/L of the day if logged, slippage, anything odd.
   If no EA is attached or nothing traded, write that in one line ("no trades logged; EA not attached?").
   Start the entry with "ALERT" for a day stop, final stop, margin error, or a trade without a broker stop.
   A "duplicate_close" line (retcode 10036 in the same second as a closing deal) is harmless: list it, no ALERT.
3. The fidelity week (owner 2026-10-25; the retired fidelity role's job). If today is a Friday, or the last Friday
   has no `docs/fidelity/<that Friday>.md` yet, write that file for the week Monday to Friday:
   run `python tools/demo_check.py --day <each day> --json`, one call per day, and put in a table per day the orders
   per leg, the journal trade lines, the alerts and the skipped trades, plus the account leverage line if one was
   logged. Under the table: legs that never traded, legs that sent more than one order a day, and any day with no EA
   lines. The pairing with a tester run (`tools/fill_check.py`) is not run: the demo days are after the holdout, so
   a tester run over them needs the owner's yes. Write "tester pairing: waiting on the owner" and nothing more.
4. Commit only those files and push:
   `git add docs/demo_log.md docs/fidelity docs/memory/decisions.jsonl` then `git commit -m "Demo log <date>"` then
   `git push origin HEAD`. If the push fails, leave the commit local and say so in your last line.

Never place, change or close trades, never change EA inputs, never record an account number, login or credential.
Finish with one line: what you logged, ALERT or not. Then the hand-over as the very last line:
`HANDOFF: judge ALERT <what>` when you wrote an ALERT, otherwise `HANDOFF: none no alert`.
