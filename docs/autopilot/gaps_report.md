# Gaps report - 2026-10-31 06:05 (doctor)

Health: **amber**. The agents run clean since the 10-30 18:00 limit reset: every finder and builder run exits 0, the
relay ticks every 5 min with no gap, and the budget stands at 0.065. Amber because Dual Thrust goes live on Monday:
PropDays does not count its magics, 1.18 has no review, and today's demo log does not yet show that 1.18 loaded.

## Fixed this run
- Nothing needed an agent fix. The queue's 108 lines all parse (94 rejected, 13 done, 1 funded), with no duplicate ids
  and nothing at testing or tester. In `data-tries.json` only the spread history is at 3, and it is done.

## Open, for Opus
1. **PropDays counts magics only up to +25** (`AurumFunded.mq5:317`). Dual Thrust (+32 to +35), breakout, noise and VRP
   days do not count toward InpPropMinDays, and Dual Thrust trades from Mon 11-02. Suggest: count every leg magic, or
   any deal with the EA's base magic range.
2. **The 1.18 load is not confirmed.** The keeper logged "Terminal 16: started, AurumFunded attached" at 00:31:13 and
   "running" at 00:32:14 (`2026-10-31_keeper.log`). But `demo_check.py` finds 0 EA lines in `20261031.log`, so there is
   no init line with the version or preset. No monitor runs on Saturday. Suggest: the owner checks the T16 Experts tab
   (version 1.18, preset `..._nyclock_dual.set`, InpDualMult 0.25) before Monday's open.
3. **1.18 has no independent review and no committed compile log** (demo_log 10-30 17:45). GER40 was at Sharpe -0.04
   alone in j18 (the owner chose to keep it). Suggest: a reviewer pass on the 1.18 diff before Monday.
4. **Weekly-limit loop (10-30 report item 1).** The owner's regex fix is in. It has not been tested yet: no limit was
   hit since then. `provider-backoff.json` still holds the 10-25 entry. Suggest: cap the relay's same-role retries
   (3 failed starts in a row means a 60 min pause).
5. **Tool-results reads are still denied.** Grep on `...\.claude\projects\...\tool-results\*.txt` was denied at 00:06:04
   and 00:22:04 (`2026-10-31_agent-finder.log:36,82`). The finder then closes leads without reading the full paper.
   Suggest: allow Read and Grep on that path.
6. **The relay says "finder ended at once or failed" after normal runs.** 04:39:43 follows a 2 min run with exit 0
   (`2026-10-31_relay.log`, finder log 04:37:54-04:39:41). The same happened 7 times today. Suggest: base the message
   on the exit code, or on a run under 30 s.
7. **Staged files from someone else.** `desk/memory/lessons.jsonl` (A), `desk/reports/live_gate.md` (M) and
   `desk/reports/scores_2026-10-30.md` (A) are staged, and a bare `git commit` would carry them (lesson 17). Suggest:
   the owner commits them or unstages them.
8. **Funded gap-day risk ends 11-01.** `InpPropResetHHMM=100` is 1 h early on gap days. It comes back 2027-03-14..28.
9. **Fidelity has no role.** `backtests/2026-10-25_1557_AurumFunded_fidelity_1019/` is still untracked.
10. **Stray and uncommitted files.** 10 modified files, as before, plus `research/fetch/_tmp_close_leads.py`. About 55
    untracked: candidate CSVs, 5 edge cards, 3 new gate JSONs (leg_cross_dailyz, ml_jump_model, thomakos) and research
    scripts. Also the temp files `_close_leads_tmp.py`, `_queue_line_tmp.py`, `_kwcheck.py`, `_finder_close_0.py` and
    `docs/ideas/backlog_done.jsonl.new`. Suggest: commit the gate JSONs and delete the temp files.
11. **Holdout rows on disk.** `marketdata/ftmo_spread/EURUSD_M1.csv.gz` runs to 2026-07. Suggest: cut it at 2025-10-12
    through tools/holdout.py.
12. **Owner questions still waiting.** (10) XAUUSD chart on M1 since 10-23. (a6) Breakout stays in the demo though it
    failed the belief gate.
13. **The summary.md drawdown row** shows the absolute max, not `eq_dd_rel` (`tester_step.py`).

## Earlier items (10-30 report)
- 1 weekly-limit loop: **partly fixed** (regex in, not yet tested). The retry cap is open (now 4).
- 2 finder commit carried owner work: **no repeat today**. Staged files remain (now 7).
- 3 budget over its line: **fixed by the reset**. The week from 10-30 18:00 is at $6.47 of $100 (0.065, skip false).
- 4 1.18 review: **open** (now 2 and 3). 5 PropDays: **open** (now 1, most urgent).
- 6 tool-results: **open** (now 5). 7 gap day, 8 fidelity, 9 strays, 10 holdout, 11 questions, 12 dd row: **open**
  (now 8-13).

## Watching
- **Finder `empty_streak` 0** (`last-finder.json` 05:16, "queued 0 ideas", 15 runs today). This is the owner's choice,
  not a fault. The 00:00 and 04:35 scouts found 31 and 32 leads. One was queued (Jones-Pyun) and the builder rejected it
  at halves 0.05/0.34. 0 leads are left.
- **Builder.** 7 runs today, all exit 0. 4 of them took 1-2 min (fast rejections at the halves or the prescreen).
- **Roles due.** Monitor ran Fri 10-30 23:15 (no alert). Portfolio last ran Sat 10-24 and is due today at 10:00. The
  judge last ran 10-30 17:33, and nothing is waiting for it.
- **Scheduled tasks.** The relay ran 90 lines today at 5 min steps from 00:00 to 06:00 with no gap. Keeper-steps runs
  every minute (1412 lines, latest 06:00:22).
- **Tester.** There is no `tester-help.json` or `to-judge.json`. The last tester run was 10-18.
- **Demo.** Fri 10-30: +58.68 EUR, no ALERT, nothing open overnight. Day start 9993.33, final stop 9150.00. T16 is
  running, the window is open until 11-01 18:00. The repo has Funded 1.18 and Hydra 1.42.
