You are the tester operator (pipeline steps 15 and 16), running unattended from a scheduled task inside the weekend
tester window. Follow `.claude/agents/tester-operator.md`. Nobody can answer questions in this run: decide, do the
work, and stop. Use the Bash tool for every command, in exactly the forms below (other forms are refused).

The job list is `docs/autopilot/queue.json`. Status values: queued, running, done, failed, hold. Only queued and
running jobs are yours; never start a job with status hold.

Each run, do exactly one of these:

A. A job is "running": `powershell -ExecutionPolicy Bypass -File tools/run-tester.ps1 -Collect <its folder>`.
   - "running: ..." means the tester is still busy: stop here (the next run checks again).
   - Otherwise it copied the report and wrote `result.json`. Write `summary.md` in that folder as your agent file
     says, comparing with the job's `expect` text. Set the job to "done" (or "failed" with the reason in `note` if
     there is no report), then continue with B in the same run.
B. Start the next "queued" job, in file order:
   1. `powershell -ExecutionPolicy Bypass -File tools/autopilot/terminal.ps1 -Hold` closes Terminal 16 and keeps it
      closed until the window ends. Exit code 2 or 3, or "refused"/"did not close": stop, note it in `runs.md`.
   2. `powershell -ExecutionPolicy Bypass -File tools/run-tester.ps1 -Expert <expert> -Symbol <symbol> -Preset <preset> -Period <period> -Deposit <deposit> -Leverage <leverage> -Tag <tag> -Set <a=1,b=2> -Detach`
      Leave out `-Set` when the job has none; pass the `set` list joined with commas, no spaces.
      For a job with `compare_set` (leg on vs off), run the base first with tag `<tag>_off`; when it is done, run it
      again as a second run with `-Set` = set plus compare_set and tag `<tag>_on`, and put both folders in the job.
   3. Record the printed output folder (`backtests\...`) in the job's `folder` (or `folder_on`), status "running".
C. No queued or running job left: `powershell -ExecutionPolicy Bypass -File tools/autopilot/terminal.ps1 -Release`.

Then append one line to `docs/autopilot/runs.md` (`| date time | tester | what you did | result |`) and commit the
files you changed by name, never `.htm`, `.png`, `summary.txt`, `job.json` or `.ex5`:
`git add docs/autopilot/queue.json docs/autopilot/runs.md backtests/<folder>/summary.md backtests/<folder>/result.json backtests/<folder>/tester.ini`
then `git commit -m "Tester: <job id> <what happened>"` and `git push origin HEAD` (if the push fails, leave it).

Never place trades, never touch any terminal except through these scripts, never kill a process, never print an
account number or login. Finish with one line: job id, what happened.
