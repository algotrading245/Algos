# Gaps report - 2026-11-02 06:00 (doctor)

Health: **red**. The FTMO demo, which is the clean out-of-sample test, cannot trade. The server disabled trading at the
03:14 reconnect, and every order since then fails with 10017 (owner item a7). Two more problems: the 5-hour usage limit
is not caught by the relay's backoff, and the week's budget is at 0.94 (chat $205 of $235).

## Fixed this run
- Nothing needed an agent fix. `queue.jsonl` has 116 lines and all of them parse: 98 rejected, 16 done, 1 funded and
  1 queued (`fix_stop_switch`, added today). No id appears twice and nothing is at testing or tester. In
  `data-tries.json` only `data_ftmo_m1_spread_history` is at 3, and it is done.

## Open, for Opus
1. **The demo cannot trade (a7).** The T16 journal at 03:14:19 says "trading has been disabled - disabled on server".
   `demo-event.json` (04:36) shows 3 Dual Thrust JP225 orders failing with 10017. The balance is 10050.36 with 0
   positions, so no rule was breached (judge 04:39). No demo day counts until this is fixed. Suggest: the owner checks
   the FTMO demo or trial status, renews it or opens a new demo, and then re-attaches through t16_attach.ini.
2. **The 5-hour limit is not caught by the backoff.** "You've hit your 5-hour limit" appears in the judge log at 02:00,
   04:19, 04:20 (x2) and 06:25 on 11-01, in the finder log at 02:00 and in the doctor log at 06:00. All of these ran
   after the 10-30 regex fix. `provider-backoff.json` still holds only the 10-25 entry. The judge was started 3 times in
   2.5 min (relay 04:17:46, 04:20:06, 04:20:33) and was then paused only by the failure count. That cost the 11-01
   doctor run. Suggest: add "5-hour limit" (or any "hit your .* limit") to the relay's limit regex, and pause the
   provider until the reset time given in the message.
3. **The `fix_stop_switch` fix is waiting.** While the stop flag is set, each leg sends again every call and Dual
   spends its 8 daily tries (`Legs.mqh:2836,2861`). With trading disabled on the server, the same thing happens with
   10017 now. Suggest: the builder takes it next. Do not reload T16 without the owner's yes.
4. **Denied reads still block agents.** The judge was denied piped and compound Bash calls 6 times on 11-01 (log lines
   27, 92-94, 111, 118). The tester was denied Get-Process and an `ls` of the tester data folder (lines 12-13, 28). The
   tester then said it could not confirm that j19 was running. Suggest: allow read-only `Get-Process terminal64`, and
   tell the roles to use one command per call, as the doctor prompt does.
5. **A builder run hit max turns.** The 11-01 run at 01:59:21 ended `error_max_turns` after 12 min
   (`2026-11-01_agent-builder.log:62`). The next run finished the work. Suggest: watch for a repeat on fix items.
6. **Tool-results reads (10-31 item 5).** No new denial on 11-01-02. It is still unverified whether the path is
   allowed. Suggest: allow Read and Grep on `.claude/projects/.../tool-results`.
7. **The tester commit has no attribution.** Commit `751dcd8` has no Co-Authored-By line, and the amend was denied
   (`2026-11-01_agent-tester.log:25,29`). This is cosmetic. Suggest: leave it, or the owner amends it.
8. **Holdout rows on disk.** `marketdata/ftmo_spread/EURUSD_M1.csv.gz` is still there (it runs to 2026-07 per the
   10-31 report). Suggest: cut it at 2025-10-12 through tools/holdout.py.
9. **Uncommitted work.** 16 files are modified (dashboard/data.js, 13 desk files, docs/candidates.md, docs/gaps.json).
   Untracked: `docs/gates/graziani_ea.json`, `desk/edges/prebuilt.py`, `desk/agents/build.md`,
   `docs/ideas/desk_notes.md`, `backtests/2026-11-01_2146_AurumFunded116_fidelity_1028/`, plus the temp file
   `research/fetch/_tmp_close_leads.py`. Nothing is staged. Suggest: commit the gate JSON and the fidelity folder, and
   delete the temp file.
10. **Fidelity has no role.** There are now two untracked fidelity folders (10-25 and 11-01).
11. **The summary.md drawdown row** still shows the absolute max, not `eq_dd_rel` (`tester_step.py`).

## Earlier items (10-31 report)
- 1 PropDays to +25: **fixed** in 1.19 (magics up to +35, demo_log 10-31 18:11).
- 2 1.18 load: **fixed**. 1.19 loaded at 18:11:34, and 1.23 loaded at 21:57:52 on 11-01 (demo_log). The repo has
  Funded 1.23 and Hydra 1.43, the same build as T16.
- 3 1.18 review: **fixed**. The 1.19 review, the compile logs and commit 7d4306e are in the repo.
- 4 weekly-limit loop: **open, now 2**. The fix does not match the 5-hour message.
- 5 tool-results: **open** (now 6). 6 "ended at once" message: **fixed or quiet**, with 0 matches in the 11-01 and 11-02
  relay logs.
- 7 staged files: **fixed**, nothing is staged. 8 gap-day risk: **closed**, the window ended 11-01 and it returns
  2027-03-14.
- 9 fidelity, 10 strays, 11 holdout, 13 dd row: **open** (now 10, 9, 8, 11). 12 owner questions: closed 10-31.

## Tokens by role (week from 10-30 18:00, 2.5 of 7 days, against the mean of the 3 weeks before)
Week totals (`budget.py trend`). The mean counts the 10-09 week, which logged 0, and roles that did not exist then
as 0.
- finder 23.7M (46 runs) against 88.4M. builder 8.5M (15) against 16.7M. tester 2.0M (2) against 4.8M. doctor 0.6M
  (2) against 3.7M. monitor 0.8M (1) against 1.1M.
- **judge 9.8M (11 runs) against 10.1M.** That is 97% after 2.5 days, so on pace for about 27M, about 2.7x the mean.
  The cause is more runs: 11 runs, on pace for about 31 (the mean is about 9). Tokens per run are about 0.9M against
  0.78M. j19, j20, the graziani reviews and the limit retries drove it.
- **portfolio 0.84M (1 run) against 0.44M, up 92%.** The cause is the base: portfolio did not exist in the 10-16 and
  10-09 weeks. Tokens per run are lower (0.84M against 1.31M).
- **desk:crypto 137k (4) against 61k, up 125%.** The cause is more tokens per run (34k against 23k). It is small.
  The other desk roles are under their means.

## Watching
- **Finder `empty_streak` 6** (`last-finder.json` 09:50, 11-01, 20 runs that day). `finder-empty.json` shows 0. The
  finder is backed off until 11-02 09:50 ("3 empty runs, 22 open leads"). This is the owner's choice, not a fault.
- **Budget** 0.941 of weekly_usd 250 (skip true, skip_above 0.7). Autopilot $26.9, chat $205.0. This is information
  only. CLAUDE.md: above 75%, no `/model opus` in chat.
- **Roles due.** The monitor last ran Fri 10-30 23:15 and is next due tonight at 23:15. The portfolio ran Sat 10-31
  10:00. The doctor failed on 11-01 at 06:00 (the limit, exit 1). The judge ran 04:37-04:40 today, exit 0.
- **Scheduled tasks.** The relay logged 299 lines on 11-01, with its largest gap 26 min (01:15). Today it has 76 lines,
  every 5 min, to 05:55. Keeper-steps logged its last line at 06:00:41, with its largest gap today 61 s.
- **Tester.** There is no `tester-help.json` or `to-judge.json`. j15-j20 are all done in `queue.json`.
- **Demo.** The repo and T16 both have Funded 1.23 (deployed 11-01 21:57). Hydra 1.43 is not attached. The demo log
  has no 11-02 entry yet, and the judge recorded the ALERT in HANDOFF and a7.
