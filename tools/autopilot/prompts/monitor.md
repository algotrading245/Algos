You are the monitor (pipeline steps 17 and 20), running unattended from a scheduled task. Nobody can answer
questions in this run: decide, do the work, and stop.

1. Run `python tools/demo_check.py` with the Bash tool.
2. Write one entry for today to the draft `docs/demo_log_entry.md` with the Write tool, then run
   `python tools/demo_log_append.py`, which appends it to `docs/demo_log.md` and deletes the draft. Never Write or
   Edit `docs/demo_log.md` itself (the settings refuse it) and never append with `python -c`. The entry follows your
   agent instructions: date, trades per leg, P/L of the day (demo_check's `closes` and `pl_of_day`, from Funded 1.16
   and Hydra 1.42 on), slippage, anything odd.
   If no EA is attached or nothing traded, write that in one line ("no trades logged; EA not attached?").
   Start the entry with "ALERT" for a day stop, final stop, margin error, or a trade without a broker stop.
   A "duplicate_close" line (retcode 10036, or 10013 on a close, in the same second as a deal on that symbol) is
   harmless: list it, no ALERT. So is "done_reported_failed" (retcode 10009 is "done": the journal shows the fill).
   So is "no trading today, European and US summer time differ": the clock skip is by design (owner 2026-10-27; the
   tester skips the same days, about three weeks a year in March/April and October/November). Note it in one line.
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
