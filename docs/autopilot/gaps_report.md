# Gaps report - 2026-10-27 06:05 (doctor)

Health: **amber**. The relay and keeper ran without a gap through 10-26 and 10-27. The queue is clean, and the finder
now stops after its daily scout, so spend fell to $11 on 10-26. But the week's budget is at 1.273 of its line, and the
demo will not trade this week: the EA's summer-time guard is on until the US clock change on 11-01.

## Fixed this run
- Nothing needed an agent fix. The queue parses and has no duplicate ids. Every data item is done. HANDOFF:53-65 agrees
  with the logs, and the version line from the 10-26 doctor run is still right (Hydra 1.41, Funded 1.15).

## Open, for Opus
1. **Budget over its line, skip does nothing.** `budget.py status` 06:00: week from 10-23 18:00 is $127.33 of $100
   (fraction 1.273, skip true), 610 runs. By day: 10-24 $57.61, 10-25 $43.01, 10-26 $11.06, 10-27 $0.13.
   It is no longer rising fast (see Watching), but skip still stops nothing. Owner: make skip stop a role, or raise the line.
2. **The demo does not trade from 10-26 to 10-30.** `AurumFunded.mq5:264-265` `ClockOk()` stops all trading while
   `EuSummer != UsSummer` (InpEuClock). demo_log 10-26 23:15: "no trading today, European and US summer time differ".
   Europe changed clocks on 10-25 and the US changes on 11-01, so the out-of-sample demo loses a week, and it does the
   same each March. Owner: decide whether to accept that or shift the leg times by one hour on those days.
3. **The monitor rewrapped a past demo_log entry.** Its shell append was refused (`2026-10-26_agent-monitor.log` 23:17:11),
   so it rewrote the whole file with Write. Commit 0611c40 rewrapped the 10-19 "Account currency is EUR" paragraph
   (`docs/demo_log.md:37`; the words are unchanged). Fix: allow an append-only script for demo_log
   (tools/autopilot/settings.json), and restore the 3-line wrap.
4. **Hydra compile for the shared Legs.mqh/Inputs.mqh change** is still not done: HANDOFF:60, judge review 10-25
   20:40 (runs.md:141). There is no compile log after that. Do it before any Hydra job.
5. **Fidelity has no role and no P/L data.** `backtests/2026-10-25_1557_AurumFunded_fidelity_1019/` is still
   untracked. demo_log 10-26 still says "P/L of the day: not logged". `demo_check.py:19` drops 6+ digit deal tickets.
   Fix: give fidelity to the judge or the monitor, mask the digits, and have the EA log P/L and close lines.
6. **demo_check false ALERT** for the 10-23 14:00 retcode 10036 duplicate close (demo_log:193, 224). Fix: skip a 10036
   close when a closing deal falls in the same second.
7. **Refused commands.** Finder Grep on `.claude/projects/.../tool-results` was denied again on 10-26 02:42, which
   blocks full paper reads (lesson 15). Monitor append denied 10-26 23:17 (item 3). Fix: allow read-only Grep/Read of
   tool-results.
8. **Overnight pause and keeper restarts, 10-25 00:01-03:02:** still not explained, and not repeated on 10-26 or 10-27.
   Owner: check the Windows update history for that night, and have the relay and keeper log who sets the pause file.
9. **Uncommitted and stray files.** Modified: `dashboard/data.js`, `desk/journal/2026-10-26.jsonl`, `docs/book.json`,
   `docs/candidates.md`, `docs/gaps.json`, `docs/ideas/near_miss.jsonl`. Untracked: 4 temp scripts
   (`research/fetch/_append_done_tmp.py`, `_close_leads_tmp.py`, `close_leads_tmp.py`,
   `research/fetch_tmp_close_leads.py`), `research/_cache_eur.csv`, `_cache_xau.csv`,
   `docs/ideas/*.jsonl.new` (2), `docs/gates/paper_announcement_day_long_indices.json`, `desk/board.jsonl`,
   `desk/inbox/`, `marketdata/` (cot, fomc, fred, ftmo_spread, crypto, candidates) and about 50 old `backtests/`.
   Owner: commit the gate verdict and state files, delete the temp files, and decide on .gitignore.
10. **Holdout rows on disk.** `marketdata/ftmo_spread/` EURUSD runs to 2026-07 (`data_ftmo_m1_spread_history`).
    Trim the file, or cut any use at 2025-10-12 via tools/holdout.py.
11. **Owner questions waiting:** (10) the XAUUSD chart has been on M1 since the 10-23 re-init; (a6) keep breakout in
    the demo after it failed the belief gate (HANDOFF:200).

## Earlier items (10-26 report)
- Item 2 (finder back-off too short): **fixed.** Since 10-26 12:25 the relay logs "finder idle: 0 open leads, today's
  scout done, no new steer". On 10-27 there was one scout at 00:00, then idle every 5 min to 06:00 (`2026-10-27_relay.log`).
- Item 3 (10-25 night pause): no repeat, still open as item 8.
- Items 1, 4, 5, 6, 7, 8, 9, 10 are still open (now 1, 5, 6, 7, 9, 4, 11, 10).

## Watching
- Finder `empty_streak` **0** (`last-finder.json` 10-27 00:00, "scouted 0 leads", 1 run today). Owner's choice, no
  brake. 21 scouts in a row have added 0 leads (decisions 10-26 to 10-27 00:00).
- Agents: no failed runs, none timed out. Monitor ran 10-26 23:15 (Monday, ok). Portfolio ran 10-24 (Saturday, ok).
  Judge last ran 10-25 22:58, builder 10-26 00:53, both exit 0 with nothing waiting. The last tester run was 10-18
  (no job queued).
- Scheduled tasks: relay ticks every 5 min with no gap over 10 min on 10-26 or 10-27. The keeper-steps log has about
  1 step a minute (10-26: 1,432 tester_step lines; 10-27: 359 by 06:00). No `*_keeper.log` exists for 10-26 or 10-27,
  so the keeper has not restarted since 10-25.
- Queue: 85 lines, all parse, no duplicates, 73 rejected and 12 done, none at testing or tester. `data-tries.json`:
  `data_ftmo_m1_spread_history` 3 (done, PARTIAL), others 1-2 (all done). No `tester-help.json` or `to-judge.json`.
- Demo: last check-in 10-26 23:15, no ALERT, no trades (item 2). Leverage 1:100, day start 10000.97 EUR. Demo runs
  1.10, repo Funded 1.15 (1.13-1.15 add the VRP leg, off by default).
- Owner commits 10-27 00:30-01:20 started the "desk" (phase 3, all pods, full risk, prop_10k rules), with "live stays
  off" (git log 87de223). This is outside the autopilot. Noted, not judged.
