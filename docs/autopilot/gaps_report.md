# Gaps report - 2026-10-28 06:05 (doctor)

Health: **amber**. The demo trades again: Funded 1.16 on the New York clock preset, first close +0.37 EUR on 10-27.
Relay and keeper show no gap. Still amber: two queue items are invisible to the builder, the finder is still refused
reads of saved tool output, and the week's budget is at 1.34 of its line.

## Fixed this run
- **HANDOFF stale state.** Lines 46, 65-67, 69-70 and 101 said the demo runs Funded 1.10, the Hydra compile is open
  and lesson 21 is unreviewed. They now say: demo on 1.16 and `..._nyclock.set` (demo_log 10-27 19:26, 19:55), Hydra
  1.42 compile done (10-27 17:56), repo Hydra 1.42 / Funded 1.17 (`#property version`), lesson 21 reviewed.
  Logged in decisions.jsonl at 2026-10-28T06:02.

## Open, for Opus
1. **Two queue items at status "pending", so the builder never picks them up.** These are
   `paper_fernandez_perez_commodity_skewness_ls` and `prebuilt_dual_thrust_four_indices_ew` (queue.jsonl, added
   10-28). The relay only runs the builder for "new" or "testing" (`relay.ps1:20`), and finder.md:96 says "new". Since
   00:46 the relay has logged only "finder idle". No decision line queued either one. They arrived uncommitted and were
   swept into builder commit 1f7ff9c (00:09). The untracked `research/prebuilt_dual_thrust_basket_crosses.py` suggests
   an outside session wrote them. Owner: set them to "new" if they are meant for the builder, or else drop them.
2. **Tool-results reads still denied, after the 10-27 allow rule.** Finder Grep and Read were denied at 10-28 00:05:43
   and 00:21:54, and builder Grep at 00:23:43 (`2026-10-28_agent-finder.log:36-37,108`, `_agent-builder.log:63`).
   The paths are `C:\Users\...\.claude\projects\<proj>\<session>\tool-results\*.txt`. The rule likely misses the
   Windows path form, and Grep is not covered at all. Without these reads, full paper reads (lesson 15) are blocked: the
   finder closed 31 leads in 45 min, at least one on "a search summary" only (finder log line 211).
3. **Budget over its line, and skip stops nothing.** Week from 10-23 18:00: $133.99 of $100 (1.34), 631 runs. Today so
   far $4.37: finder 12 runs, builder 4. Owner: make skip stop a role, or raise the line.
4. **Funded 1.17 known risk on gap days.** `InpPropResetHHMM=100` is fixed, so until 11-01 (and again 2027-03-14..28)
   the EA's firm day starts 1 h before FTMO's (demo_log 10-27 20:20). The 3% day stop leaves 2% of room, so this is
   low risk, but it sits in the funded presets. T16 still runs 1.16, and 1.17 loads at the next restart.
5. **Fidelity has no role.** P/L is now logged (demo_log 10-27 23:15 `pl_of_day` 0.37), but
   `backtests/2026-10-25_1557_AurumFunded_fidelity_1019/` is still untracked and no role owns weekly fidelity.
6. **Stray and uncommitted files keep piling up.** Modified: `dashboard/data.js`, `docs/book.json`,
   `docs/candidates.md`, `docs/gaps.json`, `docs/ideas/near_miss.jsonl`, `research/driesprong_oil_index.py`, 3
   driesprong candidate CSVs, `desk/edges/cards/noise.json`. Untracked: about 35 `marketdata/candidates/*.csv`, 5
   `desk/edges/cards/*.json`, `research/grain_harvest_seasonal.py`, `research/prebuilt_dual_thrust_basket_crosses.py`,
   and the temp script `research/fetch/_close_leads_tmp.py` again (deleted on 10-27).
7. **Holdout rows on disk:** `marketdata/ftmo_spread/EURUSD_M1.csv.gz` ran to 2026-07 at the 10-27 report. No trim
   is recorded. Trim the file, or cut at 2025-10-12 through tools/holdout.py.
8. **Owner questions waiting:** (10) the XAUUSD chart is on M1 since the 10-23 re-init; (a6) keep breakout in the demo
   after it failed the belief gate (HANDOFF:200).
9. **Judge used a refused shell form** (`find ... | head`, 10-27 20:04:35, `_agent-judge.log:13`). Minor. The run
   still ended ok. The judge prompt could name the Grep or Glob tools for this.

## Earlier items (10-27 report)
- 1 budget: open (now 3). 2 demo DST pause: **fixed** by the owner (nyclock preset 19:55, Funded 1.17 20:10, demo
  traded 10-27). 3 demo_log rewrap: **fixed** (append-only script). 4 Hydra compile: **fixed**, and HANDOFF is now
  updated too. 5 fidelity and P/L: **P/L fixed**, the fidelity role is open (now 5). 6 false ALERT: **fixed**. 7
  tool-results: **still denied** (now 2). 8 10-25 pause: **explained** (power loss). 9 strays: cleaned on 10-27, new
  ones since (now 6). 10 holdout rows: open (now 7). 11 questions: open (now 8).

## Watching
- Finder `empty_streak` **1** (`last-finder.json` 10-28 00:46, "0 ideas queued", 12 runs today). Owner's choice, no
  brake. The 00:00 scout found 31 leads. 3 were queued (all rejected by the builder) and the rest dropped by 00:46.
  Then "finder idle" every 5 min to 06:00.
- Agents: no failed or timed-out runs, and every end is exit 0. Several 1-2 min finder and builder runs show as
  "ended at once" in the relay log, but each did its work (commits 2e58eb7-c40d1e7). Monitor ran Mon 10-26 and Tue
  10-27 23:15 (ok). Portfolio last ran Sat 10-24 (next 10-31). Judge 10-27 20:00 (demo order ok). Tester last ran
  10-18, with no job queued.
- Scheduled tasks: relay ticks 10-27 00:01 to 10-28 06:00 with no gap over 15 min. The keeper log shows only the 2
  owner holds on 10-27 (19:25, 19:51), each followed by a restart with Funded attached. There is no keeper log for
  10-28, and keeper-steps is present.
- Queue: 95 lines, all parse, no duplicate ids: 81 rejected, 12 done, 2 pending (item 1), none at testing or tester.
  `data-tries.json`: `data_ftmo_m1_spread_history` 3 (done, PARTIAL), others 1-2 (all done). No `tester-help.json`
  or `to-judge.json`. `demo-event.json` is from 10-27 20:00 (judged).
- Demo: last check-in 10-27 23:15, no ALERT, 1 trade (noise US100 0.07, +0.37 EUR), bell skipped by rule. Leverage
  1:100, firm-day start 10001.34. The demo runs 1.16 and the repo has Funded 1.17 / Hydra 1.42.
