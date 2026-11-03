# Gaps report - 2026-11-03 06:05 (doctor)

Health: **red**. Overnight the account on Terminal 16 was replaced, and trading is enabled again (journal 01:18:39).
But AurumFunded failed to start at 01:55:24 ("symbol synchronization timeout") and was removed. The demo has had no EA
since then, on a weekday. The research loop is healthy.

## Fixed this run
- **`data_fred_umcsent` set to done.** `marketdata/fred/UMCSENT.csv` exists: 887 rows, 1952-11-01 to 2026-09-01. The
  dependent `paper_fisher_statman_confidence_us100_month` was built and rejected at 23:41 on 11-02. The item still said
  "new", so the relay logged "stuck after 3 finder runs" on every tick from 00:00 to 05:50 (about 70 lines in
  `2026-11-03_relay.log`). The decision is logged.
- **Queue check:** `queue.jsonl` has 130 lines and all of them parse. There are no duplicate ids and nothing is at
  testing or tester.

## Open, for Opus
1. **No EA on the demo since 01:55.** In the T16 journal (`66FB.../logs/20261103.log`): at 00:03 the old account
   was deleted. At 00:04 and 01:17 the new login was in investor mode. At 01:18:39 trading was enabled. At 01:50 the
   terminal restarted from a scratchpad config (`t16_attach_audcad`), not t16_attach.ini. The AddSymbol script failed
   at 01:55:12, and AurumFunded failed init at 01:55:24 (symbol sync timeout). The experts log says "AUDCAD n/a" at
   00:04, 01:17 and 01:18. There is no authorize line after the 01:50 restart. The keeper still reports "running".
   Suggest: the owner session logs T16 in, adds AUDCAD (or drops it from the preset), and re-attaches through the
   standard t16_attach.ini. Then the owner confirms which build is loaded. The repo has Funded **1.26** (7220ad8,
   01:52), and the demo_log has no deploy entry after 1.23. Write the account change and the new start balance (10000)
   into demo_log.
2. **The keeper does not notice an EA that failed init.** It logged "Terminal 16: running" at 01:51:22 and has logged
   nothing since. Suggest: the keeper or demo_check should look for "initializing of AurumFunded ... failed" or
   "removed" in the journal with no later "loaded successfully", and raise an ALERT.
3. **The builder loops on items blocked on data.** On 11-02 it ran 10 times, every 5 min (17:00-17:40), on
   `paper_aligned_sentiment_us500_pls`, which was waiting for `data_wurgler_sentiment`. It ran 7 more times from 23:02
   to 23:35 on fisher_statman, which was waiting for UMCSENT (`2026-11-02_agent-builder.log:65-151, 152-220`). Each
   run took about 20 s and ended "no buildable item". Suggest: the relay counts a paper item as waiting only when the
   data items it names are done, or backs the builder off 30-60 min after a "blocked on data" handoff.
4. **Judge storm on repeated ALERTs (11-02).** The judge was started 6 times in 17 min (11:34-11:51) on the same 10017
   USDJPY burst (relay log). Commit ad7529c ("alert dedupe") came later, at 19:52. Suggest: watch for a repeat once
   T16 trades again.
5. **`fix_stop_switch` has been at `ask_judge` since 11-02.** The judge has not run since 13:10 on 11-02. Suggest:
   check that `ask_judge` wakes the judge. Expected answer: superseded by 1.25 (j21 PASS), keeping F1 (login in the
   flag name, flag age on the dashboard) as a new item.
6. **Builder gate JSONs are not committed.** Six files are untracked: `docs/gates/{avg_industry_correlation,
   fisher_statman_confidence, own_implied_move_fade_3mkts, paper_bab_index_beta_neutral, paper_post_ecb_drift_indices,
   variant_yen_cross_carry_vix_calm}.json`. Also untracked: `marketdata/french_48ind_daily.csv` (it runs to
   2026-09-30 and sits outside any ignored subfolder), `research/paper_post_ecb_drift_indices_ger40_daily.csv`, 5
   desk cards, and 3 owner backtest folders from 11-03 00:20-00:40. Suggest: the builder adds its gate JSON to its
   commit, and the owner moves the French CSV under an ignored folder.
7. **Holdout rows on disk (carried over).** `marketdata/ftmo_spread/EURUSD_M1.csv.gz` is still there, and UMCSENT and
   French 48 also run past 2025-10-12. Suggest: cut them at 2025-10-12 with tools/holdout.py, or confirm every reader
   goes through it.
8. **Fidelity has no role (carried over).** The 10-25 and 11-01 fidelity folders are now tracked.
9. **The summary.md drawdown row (carried over)** still shows the absolute max (`tester_step.py`). The dashboard and
   research pages now show the relative figure (7ee93d0).
10. **Temp file:** `research/fetch/_tmp_close_leads.py` is still there (tracked). Suggest: delete it.

## Earlier items (11-02 report)
- 1 demo 10017: **changed**. Trading is enabled on the new account, but the EA is down (now item 1).
- 2 5-hour limit: **fixed**. `run-agent.ps1:339-342` now matches it, and there are 0 limit lines on 11-02 or 11-03.
- 3 fix_stop_switch: **mostly superseded** by 1.25 (now item 5). 4 denied reads: **mostly fixed**. Since gap 8
  (ff5a093) there has been 1 denial, a compound judge command at 11:51 on 11-02.
- 5 max turns: **quiet**. 6 tool-results: **quiet**. 7 attribution: cosmetic, dropped. 8, 10, 11: open (now 7, 8, 9).
- 9 uncommitted work: **partly fixed**. The graziani gate and the fidelity folders are committed, and there are new
  strays (item 6).

## Tokens by role (week from 10-30 18:00, 4.5 of 7 days, against the mean of the 3 weeks before)
The 10-09 week logged 0. Roles that did not exist in a week count as 0 there, which inflates the new roles.
- **judge 14.6M (20 runs) against 10.1M, +44% already, on pace for about 23M (2.2x).** The cause is more runs: 20,
  against a mean of about 9. Tokens per run are 0.73M, against 0.78-2.0M. The demo ALERT retriggers (11-02) and
  j19-j21 drove it.
- **builder 15.3M (42 runs) against 16.7M, 91%, on pace for about 24M (+42%).** The cause is more tokens per run
  (0.36M against 0.14-0.21M). The blocked-on-data loop (item 3) adds runs.
- **portfolio 0.84M (1) against 0.44M, +92%.** Base effect: the role is new. Tokens per run are lower.
- **The desk roles are up but small.** crypto 176k (5) against 61k (+189%), fxmacro 216k (5) against 79k (+172%),
  scorekeeper 88k (4) against 32k (+176%, more runs), indices 121k (3) against 59k (+104%, more tokens per run).
  head-trader is new (79k). These are mostly the base effect, because the desk did not exist before 10-23.
- Under the mean: finder 46.4M (103) against 88.4M, tester 2.0M against 4.8M, doctor 1.5M against 3.7M. monitor is
  1.25M against 1.10M (+13%).

## Watching
- **Finder `empty_streak` 0** (`last-finder.json` 05:52, 9 runs today). It queued 1 idea at 05:51, and the builder
  rejected it at 06:01. The 60-120 min backoff after an empty run is in place.
- **Budget** (information only, `enforce` false): 0.997 of the week's figure.
- **Roles due:** monitor ran Mon 11-02 23:15, next due tonight. portfolio ran Sat 10-31 10:00. doctor ran 11-02 06:00.
- **Scheduled tasks:** the relay logged every 5 min from 00:00 to 06:00 today. keeper-steps logged at 06:03.
- **Tester:** there is no `tester-help.json` or `to-judge.json`, and j21 is done.
- **Data tries:** `data_wurgler_sentiment` 3 (rejected, untestable) and `data_ftmo_m1_spread_history` 3 (done). Both
  are closed.
