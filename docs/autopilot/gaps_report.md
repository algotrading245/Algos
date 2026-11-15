# Gaps report - 2026-11-15 02:30 (doctor)

Health: **red**. The demo EA has not run since 11-07, so the 11-09 to 11-13 trading week of the out-of-sample test is
lost. Every load since then failed with "symbol synchronization timeout", the same fault as 11-03. Before that, the
autopilot lost 11-04 to 11-08 to a Claude billing stop, and the PC was asleep from 11-08 01:35 to 11-15 02:06. The
loop runs again from today.

## Fixed this run
- Nothing needed fixing. `queue.jsonl` has 134 lines, all of them parse, with no duplicate ids and nothing at testing
  or tester. The data items at 3 tries are all closed: `data_wurgler_sentiment` is rejected, and
  `data_ftmo_m1_spread_history` and `data_fred_umcsent` are done.

## Open, for Opus
1. **No EA on the demo since 11-07.** The T16 journal (`66FB.../logs/20261107.log:23-83`, `20261108.log:11-26`) shows
   AurumFunded loaded and then removed 5 times on 11-07 (21:15-21:51) and twice on 11-08 (00:57, 01:30). Three of the
   11-07 loads and both 11-08 loads end in "initializing ... failed with code 0 (symbol synchronization timeout)". The
   last EA log is `MQL5/Logs/20261106.log` (11:57). There is no journal file for 11-09 to 11-15. The keeper still
   says "running".
   Suggest: the owner session finds the symbol that never syncs (AUDCAD was "n/a" on 11-03) and adds it or drops it
   from the preset. Then it re-attaches through t16_attach.ini, checks that "loaded successfully" is not followed by
   "removed", and logs the build in demo_log. The repo has Funded 1.26; demo_log's last deploy is 1.23.
2. **The keeper and demo_check miss a failed init (carried over, now proven costly).** A whole trading week passed
   with no ALERT. The 11-15 monitor saw no EA lines for 11-09 to 11-13 but had no ALERT category for that case.
   Suggest: raise an ALERT when the journal shows "initializing of AurumFunded ... failed" or "removed" with no later
   "loaded successfully", or when a weekday has no EA log.
3. **The relay does not stop on "payment past due".** From 11-04 03:03 to 11-08 00:00 there were 21 instant exit-1
   runs: judge 12 (`last-judge.json` fails_in_row 12), doctor 7, finder 3, monitor 1. All logged "Claude Code can't
   use your Claude subscription ... payment is past due" (e.g. `2026-11-05_agent-judge.log` 02:57, 15:49, 17:50).
   `provider-backoff.json` caught only the weekly limit (11-04 00:01). Every judge run that week was a demo-order
   check, and none was done.
   Suggest: `run-agent.ps1` treats "payment is past due" or "can't use your Claude subscription" as a provider
   backoff, 6 h or more, with one dashboard alert.
4. **The PC slept for 7 days.** No relay or keeper lines between 11-08 01:35 and 11-15 02:06, apart from keeper-steps
   11-13 15:14-15:18. Two terminal64 processes date from 11-08, so this was sleep, not a shutdown.
   Suggest: the owner sets the power plan to never sleep on AC, or adds a wake timer to the keeper task.
5. **`fix_stop_switch` waits for the builder.** It is queued (`queue.jsonl:116`); the judge's 11-03 verdict was
   NOT superseded. The builder last ran 11-03 21:16. It should be built once the relay resumes, so watch for it.
6. **Portfolio's near-miss review is not committed.** `docs/ideas/near_miss.jsonl` is modified in the working tree
   (portfolio decision 11-15 02:20), and `desk/edges/cards/carry.json` is untracked.
   Suggest: add near_miss.jsonl to the portfolio role's commit list.
7. **Holdout rows on disk (carried over).** `marketdata/ftmo_spread/{EURUSD,GBPUSD,USDJPY}_M1.csv.gz` and
   `marketdata/french_48ind_daily.csv` run past 2025-10-12. Suggest: cut them with tools/holdout.py, or confirm that
   every reader goes through it.
8. **Carried over:** fidelity has no role of its own (the monitor wrote `docs/fidelity/2026-11-13.md`). The drawdown
   row in summary.md still shows the absolute max (`tester_step.py`). `research/fetch/_tmp_close_leads.py` is still
   tracked.

## Earlier items (11-03 report)
- 1 no EA on the demo: **reopened**. It ran again 11-03 to 11-06 (noise closes on both days) and fell again on 11-07
  (now item 1). 2 keeper blind to failed init: **open** (item 2).
- 3 builder blocked-on-data loop and 4 judge storm: **not seen**, because nothing ran. Watch them once the relay resumes.
- 5 fix_stop_switch: answered by the judge 11-03, queued (item 5).
- 6 untracked gate JSONs: **fixed** (fea9d65 synced them). 7-10: open (items 7, 8).

## Tokens by role (week from 11-13 18:00, about 8 h awake, against the mean of the 3 weeks before)
The 11-06 week logged 0 (billing stop and sleep), which pulls every average down.
- **portfolio 1.39M (1 run) against 0.72M, +93%.** The cause is more tokens per run (1.39M against 0.84M and 1.31M).
  This run did the 28-row near-miss review.
- **desk:monitor 26k (1) against 8k, +207%.** Base effect: it has run once in each of only two weeks.
- monitor 0.78M (1) against 1.23M. desk:crypto 77k (2) against 133k. The week has barely started.
- The finder, builder, judge and doctor have not run yet this week.

## Watching
- **Finder `empty_streak` 2** (`last-finder.json` 11-08 00:00). `finder-empty.json` shows a streak of 4, with lead
  iwanaga_sp_nikkei_contrarian. This is the owner's choice and not a fault.
- **Budget** (information only, `enforce` false): 0.005 of the week.
- **Roles due:** the monitor missed 11-05 to 11-13 (billing, then sleep) and ran 11-15 02:21; next 11-16 22:15. The
  portfolio missed Sat 11-14 (asleep) and ran 11-15 02:15. The doctor's last good run was 11-03.
- **Scheduled tasks:** `tasks.json` (02:23) shows Relay ok at 02:20 and Keeper running. There is no relay log today
  yet, because the monitor and this run held the mutex.
- **Tester:** there is no tester-help.json or to-judge.json. The tester last ran 11-01.
