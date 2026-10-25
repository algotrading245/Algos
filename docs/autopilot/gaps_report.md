# Gaps report - 2026-10-25 06:05 (doctor)

Health: **amber** - the queue is clean and the demo is attached (AurumFunded 1.10). Three things are wrong: the system
was paused for about 3 h overnight with repeated PC or keeper restarts, the finder burned $48.78 in 237 empty runs
on 10-24, and the week's budget is already at 0.767, past its 0.7 skip line.

## Fixed this run
- `docs/HANDOFF.md:155-156` still said the demo has "1.06 loaded". The keeper log (10-23 01:45 "Terminal 16:
  started, AurumFunded attached") and HANDOFF:86 say 1.10. The line now says 1.06 was loaded and 1.10 runs since
  10-23 01:45. Decision logged at 06:02.

## Open, for Opus
1. **Overnight pause and restarts, 10-25 00:01-03:02.** `2026-10-25_keeper-steps.log` shows "paused: no steps
   started" from 00:01:52 to 02:55:55, so the pause file existed. The relay log has nothing between 00:00:05 and 03:02:22.
   The finder run that started at 00:00:06 has no end line (`2026-10-25_agent-finder.log:1`). The keeper started 6 times,
   each with a new pid (`2026-10-25_keeper.log` 00:19, 00:57, 01:15, 01:30, 01:45, 02:55), and each time it found
   Terminal 16 down and restarted it. The line before 00:57 is padded with blanks, which points to an unclean
   shutdown. The 03:00 to 02:00 DST change falls inside this window, so the times between 02:00 and 03:00 are ambiguous.
   No harm on a Sunday, but on a weekday this would stop the demo. Fix (owner): check the Windows restart and update
   history for that night, and why the pause file was set. Have relay/keeper log who sets or clears the pause.
2. **The finder's cost.** On 10-24 it made 237 runs for $48.78 (sum of usage lines in `2026-10-24_agent-finder.log`),
   against $5.76 for the builder. It also hit the Claude session limit 4 times (relay 00:16, 04:51, 09:35, 14:19), and
   the relay was idle for 1.1-2.1 h each time. Today: 36 runs by 05:55, each about 30 s, all "0 ideas". The relay logs
   each one as "ended at once or failed". Fix (relay.ps1, owner): space the finder out after an empty run (e.g. 60 min)
   and keep quota for judge and monitor in market hours. This continues item 1 of 10-24.
3. **Budget past its skip line:** `budget.py status` gives the week from 10-23 18:00 at $76.66 of $100 (fraction
   0.767 > skip_above 0.7, skip true), with 5 days left. Information only, no brake. If skip does nothing and the finder
   spends at 10-24's rate, the week passes $100 within a day. Owner: decide whether skip should stop the finder.
4. **The fidelity week (due 10-23) still has no role and no P/L data** (HANDOFF:83, `last-fidelity.json` 10-18).
   `demo_check.py:19` drops deal lines with 6+ digit tickets (journal_trade_lines 0). Fix as on 10-24: give
   fidelity to judge or monitor, mask the digits, and log P/L and close lines in the EA.
5. **demo_check false flags:** the 10-23 14:00 retcode 10036 duplicate close still raises ALERT (demo_log 10-23 23:16).
   Noise orders count as "other". Fix: skip a 10036 close when the same second has a closing deal, and count
   "bands" lines as noise.
6. **Refused commands are still happening.** Finder heredocs `python - <<'E'` were refused on 10-24 at 02:01, 02:05,
   04:47, 08:15 and 12:46. Reads of tool-results were refused at 12:09 and 12:16, which blocks full paper reads
   (lesson 15). `memory.py search RSI(2)` was refused at 14:11 (parentheses). None so far today. Fix: tell the finder
   prompt to use Write or a script, and allow read-only tool-results in tools/autopilot/settings.json.
7. **Stray and uncommitted files.** Untracked: `docs/ideas/_finder_tmp_note.txt`, `sources_tmp_note.txt` and the new
   `sources.jsonl.new`; 5 `docs/ideas/specs/f_*_vl.json`; and `AurumBreakout/Funded/Noise.ex5`. Modified:
   `AurumHydra.ex5` (no source change since 2869c12). The finder says it does not commit its decision lines. Owner:
   delete the temp files, and decide whether the specs and `.ex5` files belong in git or in .gitignore.
8. **Owner questions are waiting:** (10) the XAUUSD chart has been on M1 since the 10-23 re-init, and (a6) whether
   to keep breakout in the demo after it failed the belief gate (HANDOFF:200).
9. **Old role files** still look like failed or overdue roles: `last-scanner.json` (exit 1, 10-18), and
   `last-tester/fidelity/orchestrator/researcher/worker/miner.json` (10-18 to 10-22). Fix: archive them.

## Earlier items (10-24 report)
- Item 3 (8 gate verdicts uncommitted): **fixed**. `docs/gates/` is no longer untracked, and `vrp_gap.json` and the
  others are in commit 0322e13.
- Portfolio check: **done**. The portfolio manager ran Saturday 10-24 11:53-12:01 (exit 0, `last-portfolio.json`).
  It was late against 10:00 because of the 09:35 session limit.
- Items 1, 2, 4, 5, 6, 7, 8, 9 are still open (now 2, 4, 5, 6, 7, 7, 8, 9 above).

## Watching
- Finder `empty_streak` is **14** in `last-finder.json` (it was 72 on 10-24, so it was reset by the dropped and closed
  leads). That is the owner's choice, with no brake. 36 runs today, 125 numbered runs so far on 10-25 (decisions
  log), and 14 open leads, all venue crawls.
- Queue: 49 lines, all parse, no duplicate ids. 41 rejected, 8 done, none at "testing" or "tester".
  `data-tries.json`: none at 3 or more (binance_crypto_1h at 2). No tester-help or to-judge file.
- Monitor: last run Friday 10-23 23:16, exit 0 (none due on the weekend). Judge: last run 10-23 20:25.
- Demo log: last check-in 10-23 23:16, no unanswered ALERT apart from the known 10036 flag. Weekend: no EA lines
  expected. Terminal 16 is running, with the window open until 10-25 18:00. Repo builds: Funded 1.10 (= demo), Hydra 1.39.
- Gaps on 10-24 in the relay (00:16-01:25, 04:51-06:25, 09:35-11:25, 14:19-16:25) are the session-limit back-offs.
  keeper-steps has no gap over 30 min on 10-24.
