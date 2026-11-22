# Gaps report - 2026-11-22 16:25 (doctor)

Health: **red**. The demo has had no working EA since 11-07. The terminal has not been logged in to FTMO-Demo since
11-07 21:29, so every load since then stalls in OnInit. The PC was also off from 11-15 03:17 to 11-22 16:15, apart from
a boot on 11-17 01:03. Two of the out-of-sample test's trading weeks are lost (11-09 to 11-20).

## Fixed this run
- **`data_histdata_index_m1` done state committed.** At 11-15 02:56 the finder closed the item in the working tree
  but never committed it, because it hit the 5-hour limit. The fetch log shows rc 0 (`logs/autopilot/fetch/data_histdata_index_m1.json`).
  UKXGBP, FRXEUR, AUXAUD, HKXHKD and ETXEUR `_M1.csv.gz` are in `marketdata/histdata` (11-15 02:36-02:53). The
  `queue.jsonl` line and the finder's decision line now go into this commit.

## Open, for Opus
1. **T16 is not logged in, so the EA never initialises (root cause of last week's item 1).** The journal's last
   Network lines are in `logs/20261107.log:27-35`: authorized 21:29:38, then "disconnected from FTMO-Demo" at 21:29:51.
   No Network or "authorized" line appears in 20261117, 20261118 or 20261122.log. On 11-17 01:07 the EA "loaded
   successfully" and then sat in init for 25 h, until "initializing ... failed (execution canceled)" at
   `20261118.log:1`. On 11-22 16:18 it "loaded successfully" again, still with no login line. `MQL5/Logs` is empty.
   Suggest: the owner opens T16 and checks the login. FTMO free-trial demos expire, so a new demo may be needed, and
   AurumFunded 1.23 vs the repo's 1.26 should be decided before re-attaching. Then check for "authorized" and "synchronized" lines and
   the EA's first log line.
2. **The keeper reports "Terminal 16: running" with no login and no EA log** (`2026-11-22_keeper.log:3`). This is
   last week's item 2, now with a better test. Suggest: raise an ALERT when the day's journal has no "authorized on"
   line after the start, or when a weekday has no file in MQL5/Logs.
3. **The PC was off for most of the week.** There are no relay lines from 11-15 02:56 to now. The keeper has only 3
   lines on 11-17 (01:04-01:05) and resumes 11-22 16:16. `tasks.json` shows the Dashboard last at 11-17 01:03 and every task
   catching up at 11-22 16:15. Keeper's "sleep blocked" does not cover shutdown or lid close. Suggest: the owner
   sets the power plan to never sleep on AC and to do nothing on lid close, or adds a wake timer (carried, item 4).
4. **A second terminal64 holds the MCP port.** At `20261122.log:9`, T16 logged "MCP bind error on 127.0.0.1:22346
   (10048)". Two terminal64 processes are running (pids 16992, 17208). It is probably the tester install sharing the port. That is harmless now, but
   check that the keeper did not start a second T16.
5. **The relay does not stop on "payment past due" (carried, item 3).** Not seen this week. Suggest: run-agent.ps1
   treats that text as a 6 h provider backoff.
6. **`fix_stop_switch` still waits for the builder** (`queue.jsonl:116`, queued). The builder last ran 11-03 21:16
   (`last-builder.json`), and nothing has run since.
7. **Portfolio's near-miss review is still uncommitted** (`docs/ideas/near_miss.jsonl` modified since 11-15 02:20;
   `desk/edges/cards/carry.json` untracked, `docs/gaps.json` and `dashboard/data.js` modified). Suggest: add
   near_miss.jsonl to the portfolio role's commit list (carried, item 6).
8. **Holdout rows on disk (carried, now larger).** The new `marketdata/histdata/{UKXGBP,FRXEUR,AUXAUD,HKXHKD}_M1.csv.gz`
   run to 2026-11. So do `marketdata/ftmo_spread/*_M1.csv.gz` and `french_48ind_daily.csv`. Suggest: make sure
   the Dual Thrust basket test reads them through tools/holdout.py, or cut them at 2025-10-12.
9. **Carried:** fidelity has no role of its own. The drawdown row in summary.md shows the absolute max
   (`tester_step.py`). `research/fetch/_tmp_close_leads.py` is still tracked.

## Earlier items (11-15 report)
- 1 no EA on the demo: **open**, now traced to the lost login (item 1). 2 keeper blind: **open** (item 2).
- 3 payment-past-due loop: not repeated, **open** (item 5). 4 sleep: **open**, worse (item 3).
- 5 fix_stop_switch: **open** (item 6). 6 near-miss uncommitted: **open** (item 7). 7, 8: **open** (items 8, 9).

## Tokens by role (week from 11-20 18:00, against the mean of the 3 weeks before)
The PC was off for most of the last two weeks, so the averages are small and every ratio is mostly a base effect.
- **desk:monitor 29.8k (1 run) against 8.6k (25.9k, 0, 0): +246%.** This is a base effect from more runs: it ran
  once in each of only two weeks. Tokens per run are flat (29.8k against 25.9k).
- No other role has run this week (the monitor, portfolio and doctor caught up at 16:15 today).
- The 3 weeks before: 11-13 portfolio 1.39M, doctor 1.33M, monitor 0.78M, finder 0.65M (2 runs). 11-06: 0.
  10-30: finder 56.0M (126 runs), builder 17.2M (46), judge 15.5M (33).

## Watching
- **Finder `empty_streak` 0** (`last-finder.json` 11-15 02:56; `finder-empty.json` streak 0, rotate 2). Owner's choice.
- **Budget** (information only, `enforce` false): week fraction 0.0, $0.01 outside the autopilot.
- **Roles due:** the monitor missed Mon-Fri 11-16 to 11-20 and the portfolio missed Sat 11-21 (PC off). Both tasks
  fired at 16:15 today. The last demo_log entry is 11-15 02:21, and no ALERT is unanswered.
- **Queue:** 136 lines. All parse, with no duplicate ids. Nothing is at testing or tester (111 rejected, 22 done, 1 funded, 1
  queued). Data items at 3 tries (`data_wurgler_sentiment`, `data_ftmo_m1_spread_history`, `data_fred_umcsent`) are
  all closed.
- **Tester:** no tester-help.json or to-judge.json. The tester last ran 11-01.
- **Keeper steps** restart all four steps every minute (`*_keeper-steps.log`). This is probably by design (one-shot
  steps); flag it if pids pile up.
