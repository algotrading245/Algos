# Gaps report - 2026-10-30 17:45 (doctor)

Health: **amber**. The weekly Claude limit stopped all agent work from 10-30 00:07 to 17:00. The relay restarted the
builder every 5 minutes through that window (206 failed starts). The owner's fix to the limit pattern is now committed.
After 17:00 the agents recovered: the judge caught up on all of the day's demo orders with no ALERT. The demo is
healthy.

## Fixed this run
- Nothing needed an agent fix. The queue's 101 lines all parse, with no duplicate ids and nothing at testing or tester.
  No data item is stuck.

## Open, for Opus
1. **The weekly limit was not caught, so 17 h were lost.** `2026-10-30_agent-builder.log`: 209 starts, 206 of them
   "You've hit your weekly limit, resets 5pm" (first at 00:07:47). The relay logged "builder ended at once" every 5 min
   from 00:07 to 17:00 (`2026-10-30_relay.log` lines 4-418). The doctor at 06:00 and the judge at 01:56, 12:08, 12:31
   and 15:31 also died in about 5 s (`last-doctor.json` exit 1).
   `provider-backoff.json` was never set. The owner's fix (`run-agent.ps1:327-330`, regex now has `weekly limit`) is in.
   Suggest: check that the next limit message writes `provider-backoff.json`. Also cap the relay's same-role retries
   (for example, 3 failed starts in a row means a 60 min pause), so an unmatched message cannot loop.
2. **A finder commit carried the owner's work in progress (lesson 17 again).** b5eda88 "Finder 2026-10-30" includes
   `tools/autopilot/run-agent.ps1`, `tools/autopilot/t16_attach.ini`, the new
   `AurumFunded_FTMO_phase1_legs_nyclock_dual.set` and the owner's demo_log entry. Suggest: the finder (and every
   role) commits only named paths (`git add <file>`), never all staged files. Owner sessions should commit before
   the relay's next commit, or work on a branch.
3. **Budget at 1.50 of its line, and skip stops nothing.** The week from 10-23 18:00 stands at $149.50 of $100, over
   883 runs (`budget.py status`). The real cap hit at about 00:07 today. The week resets today at 18:00. Suggest: let
   `skip` pause the finder and builder, or set `weekly_usd` to about 145, the level where the real limit hit.
4. **Demo goes to 1.18 with Dual Thrust on at the 10-31 00:30 restart (owner, demo_log 10-30 17:45).** Still open:
   1.18 had no independent review and its compile log is not in the repo. GER40 was at Sharpe -0.04 in the gate
   rerun (item 2 of the last report: the owner chose to keep it). Suggest: a reviewer pass on the 1.18 diff and a
   committed compile log before Monday's first Dual Thrust orders.
5. **`PropDays` counts magics only up to +25** (`AurumFunded.mq5:317`). Dual Thrust (+32 to +35), breakout, noise and
   VRP days do not count toward InpPropMinDays. With Dual Thrust going live on Monday, this now matters for the
   challenge.
6. **Tool-results reads denied.** Last seen 10-29 00:30:59 (`2026-10-29_agent-finder.log:160`). Not seen today, but
   the finder barely ran today. Suggest: allow Read and Grep on `C:\Users\ailea\.claude\projects\C--Users-ailea-desktop-algo\*\tool-results\*`.
7. **Funded gap-day risk until 11-01.** `InpPropResetHHMM=100` is 1 h early on gap days. The risk is low, with 2% of
   room. It recurs 2027-03-14..28.
8. **Fidelity has no role.** `backtests/2026-10-25_1557_AurumFunded_fidelity_1019/` is still untracked, and no role
   pairs demo days with tester runs.
9. **Stray and uncommitted files.** 10 are modified (dashboard/data.js, docs/book.json, docs/candidates.md,
   docs/gaps.json, near_miss.jsonl, noise.json card, driesprong script and 3 CSVs). About 50 are untracked:
   marketdata/candidates CSVs, 5 edge cards, 3 research scripts, and the temp files `research/fetch/_close_leads_tmp.py`
   and `_queue_line_tmp.py`. `docs/ideas/backlog_done.jsonl.new` (2 bytes) is still there. New: the finder tried to
   write `_src.jsonl` at the repo root (denied, 10-30 17:26:55).
10. **Holdout rows on disk.** `marketdata/ftmo_spread/EURUSD_M1.csv.gz` ran to 2026-07 (10-27 report). No trim is found
    in memory (`memory.py search ftmo_spread trim holdout`: no matches). Suggest: cut it at 2025-10-12 through
    tools/holdout.py.
11. **Owner questions still waiting.** (10) The XAUUSD chart has been on M1 since 10-23. (a6) Breakout stays in the
    demo even though it failed the belief gate.
12. **The summary.md drawdown row** shows the absolute max, not `eq_dd_rel` (`tester_step.py`).

## Earlier items (10-29 report)
- 1 tool-results: **open** (now 6), not seen today.
- 2 j18 GER40: **decided by the owner**. The leg goes on with GER40 (demo_log 10-30). The review gap moves to item 4.
- 3 budget: **open** (now 3), and the real limit hit.
- 4 PropDays: **open** (now 5), more urgent.
- 5 gap day, 6 fidelity, 7 strays, 8 holdout, 9 questions, 10 dd row: **open** (now 7, 8, 9, 10, 11, 12).

## Watching
- **Finder `empty_streak` 3** (`last-finder.json` 17:39, "0 ideas queued", 9 runs today). This is the owner's choice,
  not a fault. The 00:00 scout found 31 leads. 7 are left at 17:37, and most leads closed as 404s or covered families.
- **Agents since 17:00.** The finder, builder and judge all exit 0. The builder rejected 3 ML ideas (c9f5286, f1bc219,
  91a3132). The monitor last ran Thu 10-29 at 23:15 with no alert. Fri is due at 23:15. Portfolio last ran Sat 10-24
  and is due Sat 10-31 at 10:00, after the 18:00 limit reset.
- **Scheduled tasks.** No gap over 10 min in the relay (10-29: 301 lines, 10-30: 434) or keeper-steps (latest
  17:39:41). There is no keeper.log on 10-29 or 10-30, so no hold or restart happened yet.
- **Queue and tester.** 87 rejected, 13 done, 1 funded. `data-tries.json` has only done items (spread history at 3,
  done). There is no `tester-help.json` or `to-judge.json`.
- **Demo.** Last monitor check-in was 10-29 23:15 with no ALERT, day P/L +31.74 EUR. On 10-30 the judge checked at
  17:33-17:34 with no ALERT: every order had a broker stop, and midday made +68.56. Day start 9993.33, final stop
  9150.00. The demo runs 1.16. The repo has Funded 1.18 and Hydra 1.42.
