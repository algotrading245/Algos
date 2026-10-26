# Gaps report - 2026-10-26 06:05 (doctor)

Health: **amber** - the relay and keeper ran without a gap since 10-25 22:55, the queue is clean and the demo is
attached (AurumFunded 1.10). But the week's budget is now past $100 (1.252) with 4.5 days left, the finder still
makes most of the spend, and the demo has had no monitor check since Friday (none due until tonight).

## Fixed this run
- `docs/ideas/queue.jsonl:78` `fix_vrp_leg_fidelity` sat at "tester", though j17 was judged FAIL on 10-25 23:10
  (`docs/autopilot/queue.json` j17 note), the VRP leg was rejected and HANDOFF:59 says "no fix item". Set to "done"
  with that note before the old result. Decision logged at 06:01.
- `docs/HANDOFF.md:64` said the repo wrappers are "Hydra 1.39 and Funded 1.10". `#property version` gives Hydra 1.41
  (`AurumHydra.mq5:139`) and Funded 1.15 (`AurumFunded.mq5:97`). The line now says that, and that the demo still runs 1.10.
  Decision logged at 06:02.

## Open, for Opus
1. **Budget well past its line, skip does nothing.** `budget.py status`: the week from 10-23 18:00 is $125.23 of $100
   (fraction 1.252, skip true), 595 runs. By day: 10-24 $57.61, 10-25 $43.01, 10-26 $9.09 by 06:00. Finder: 241 runs /
   $49.43 (10-24), 189 / $27.76 (10-25), 35 / $8.32 (10-26), against builder $5.75 / $7.73 / $0.77 (usage.jsonl).
   Owner: decide whether skip should stop the finder, or raise the weekly line.
2. **The finder's back-off is too short to matter.** relay.ps1 now backs it off 30 min after an empty run
   (`2026-10-26_relay.log` 02:51, 03:31, 04:11, 04:50, 05:25). But each back-off ends in a "normal" run that closes
   2-5 leads it just scouted, then a "scout" run that adds 0 (decisions 04:05-05:25: "topics exhausted"). That is
   about 3 runs an hour, all night. It also hit the Claude session limit twice on 10-25 (relay 17:23 and 20:51, idle
   until 17:52 and 22:52). Fix (relay.ps1): grow the back-off (30 -> 60 -> 120 min) while scouts add 0, and keep
   quota for judge and monitor in market hours.
3. **Overnight pause and keeper restarts, 10-25 00:01-03:02** (item 1 of 10-25, not explained). The keeper started
   7 times with new pids (`2026-10-25_keeper.log` 00:19-03:00) and restarted Terminal 16 each time. No repeat since:
   no keeper restart on 10-26, keeper-steps has no gap over 30 min. Owner: check the Windows restart/update history
   for that night and have relay/keeper log who sets the pause file.
4. **Fidelity has no role and no P/L data** (item 4 of 10-25). `last-fidelity.json` is gone (archived), and
   `backtests/2026-10-25_1557_AurumFunded_fidelity_1019/` is untracked. `demo_check.py:19` still drops 6+ digit deal
   tickets (10-23 monitor: 0 journal trade lines; "P/L of the day: not logged"). Fix: give fidelity to judge or
   monitor, mask the digits, log P/L and close lines in the EA.
5. **demo_check false ALERT** for the 10-23 14:00 retcode 10036 duplicate close (demo_log 10-23 23:16). Fix: skip a
   10036 close when the same second has a closing deal; count "bands" lines as noise orders.
6. **Refused commands.** Finder Grep on `C:\Users\ailea\.claude\projects\...` tool-results denied 10-25 16:21, 23:27
   and 10-26 02:42 (blocks full paper reads, lesson 15). Finder `python -c` append to backlog_done denied 10-25 18:37.
   Judge handoff.py and HANDOFF edit denied 10-25 22:58:49 at session end. Fix: allow read-only Grep/Read of
   tool-results in tools/autopilot/settings.json; tell the finder to append with a script.
7. **Uncommitted and stray files.** Modified: `docs/memory/decisions.jsonl` (finder lines), `docs/book.json`,
   `docs/candidates.md`, `docs/gaps.json`, `docs/ideas/near_miss.jsonl`, `dashboard/data.js`. Untracked: 4 temp
   scripts (`research/fetch/_append_done_tmp.py`, `_close_leads_tmp.py`, `close_leads_tmp.py`,
   `research/fetch_tmp_close_leads.py`), `docs/ideas/sources.jsonl.new`, `backlog_done.jsonl.new`,
   `docs/gates/paper_announcement_day_long_indices.json`, new `marketdata/` folders (fred, cot, fomc, ftmo_spread,
   crypto) and ~50 old `backtests/` folders. Owner: commit the gate verdict and state files, delete the temps,
   decide on marketdata/backtests in .gitignore.
8. **Hydra compile for the shared Legs.mqh/Inputs.mqh change** is still listed as open (HANDOFF:60). No compile log
   seen by this run. Do it before any Hydra job.
9. **Owner questions waiting:** (10) XAUUSD chart on M1 since the 10-23 re-init; (a6) keep breakout in the demo
   after it failed the belief gate (HANDOFF:200).
10. **Data with holdout rows on disk.** `marketdata/ftmo_spread/` EURUSD runs to 2026-07 (queue item
   `data_ftmo_m1_spread_history` result). Any use must cut at 2025-10-12 via tools/holdout.py; better to trim the file.

## Earlier items (10-25 report)
- Item 9 (old role files): **fixed** - only `last-tester.json` (10-18, exit 0) is left of the old roles.
- Item 2 (finder cost): **partly fixed** - a 30 min back-off exists; cost per day fell from $49 to $28 (now item 2).
- Items 1, 3, 4, 5, 6, 7, 8 still open (now 3, 1, 4, 5, 6, 7, 9).

## Watching
- Finder `empty_streak` **0** in `last-finder.json` (05:25, "scouted 0 leads", 35 runs today). Owner's choice, no brake.
- Queue: 85 lines, all parse, no duplicate ids; 73 rejected, 12 done, none at "testing" or "tester" now.
  `data-tries.json`: `data_ftmo_m1_spread_history` at 3, but it is already "done" (PARTIAL); the rest at 1-2, all done.
  No `tester-help.json` or `to-judge.json`.
- Judge: last run 10-25 22:58 (exit 0, "nothing left"). Builder 10-26 00:53 (exit 0). Portfolio 10-24 (Saturday, ok).
  Monitor: last 10-23 23:16; Monday's run is due tonight.
- Demo: last check-in 10-23 23:16, no unanswered ALERT apart from the known 10036 one. Owner hold 10-25 19:10, Terminal 16
  restarted 19:11 with AurumFunded attached, running now. Demo 1.10 vs repo Funded 1.15: 1.13-1.15 added the VRP leg,
  off by default (HANDOFF:59). This run did not check 1.11-1.12 line by line.
- Relay gaps 10-25: 00:00-03:02 (item 3), 17:23-17:55 and 20:51-22:55 (session limits). None on 10-26.
