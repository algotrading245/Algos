# Gaps report - 2026-10-24 07:10 (doctor)

Health: **amber** - the relay, the keeper and the demo (AurumFunded 1.10) run with no gap over an hour, and the queue
is clean. But the finder uses up the Claude session quota about every 4-5 hours, which holds back demo checks by up
to 2.5 h. The fidelity week also has no role to run it and no P/L data to use.

## Fixed this run
- `docs/HANDOFF.md` (Terminals line 46, Current state line 53): these lines still said the demo runs 1.06 and the
  repo builds are 1.09 / 1.38. The keeper log shows 2026-10-23 01:45:11 "Terminal 16: started, AurumFunded attached"
  (1.10), and the source has `AurumFunded.mq5:83` "1.10" and `AurumHydra.mq5:137` "1.39". Both lines are corrected,
  and the M1 re-init points to owner question (10). Decision logged at 07:05.

## Open, for Opus
1. **The finder uses up the session quota, and the demo checks wait for it.** The finder has run 84 times today by
   07:01 ($19.98 of $21.09, `budget.py status`). The Claude session limit hit 4 times on 10-23 (03:00, 08:49, 13:21,
   17:20) and twice today (00:16, 04:51), and finder runs set off the last five (`2026-10-2x_relay.log`). Because of
   this, the 17:59:59 demo order was judged only at 20:25, the 09:06 order at 10:23 and the 14:00 ALERT at 15:25.
   Fix (relay.ps1, owner): keep part of the quota for judge and monitor, for example by pausing the finder for 30-60
   min after an empty run while the demo market is open.
2. **The fidelity week (due 10-23) has no role and no data.** HANDOFF:83 says "Fidelity is next, after the first demo
   week", but the 5-step loop has no fidelity role (`last-fidelity.json` is from 10-18) and nothing ran. Also,
   `demo_check.py:19` drops deal and order lines with 6+ digit tickets, so journal_trade_lines has been 0 every day
   (demo_log 10-23 23:16, "P/L not logged"). Fix: give fidelity to the judge or monitor, mask digit runs instead of
   dropping the line, and log P/L and close lines in the EA.
3. **The builder's gate verdicts are not committed.** These are untracked: `docs/gates/` dao_gap, fx_carry_g10,
   opex_week_indices, overreaction_fx, policy_gap, totm_us, vix_vxv_spike and vrp_gap.json (`git status`). The
   queue results cite them, and their scripts are committed. Fix: have the builder prompt `git add docs/gates/<id>.json`,
   and commit these 8 now.
4. **demo_check false flags.** (a) The 14:00 10036 duplicate close still shows as ALERT in every check (HANDOFF
   proposal 9). (b) Noise orders count as "other" (`demo_check.py:20,42-46`; 10-23 "other 3" = breakout 1 + noise 2).
   Fix: skip a 10036 close when the same second has a closing deal, and treat "bands" lines as noise.
5. **Refused heredoc writes are still happening.** `python - <<'E'` was refused for the finder at 10-24 02:01, 02:05
   and 04:47, and at 10-23 02:27, 05:27, 06:56, 07:19, 16:13, 17:14, 22:12 and 23:32. Each one wastes turns. At 22:14
   the finder also tried `git checkout` / `git restore docs/ideas/sources.jsonl`, both refused. sources.jsonl still
   parses (1110 lines). Fix: tell the finder prompt to use the Write tool or `python tools/...`.
6. **Stray temp files from the finder:** `docs/ideas/_finder_tmp_note.txt` and `docs/ideas/sources_tmp_note.txt`
   (untracked). Agents are not allowed to delete. Owner: delete them.
7. **Agents cannot read their own large tool results** (`~/.claude/projects/*/tool-results/*`). The last refusal was
   finder 10-23 01:23, so full paper reads (lesson 15) fail. Fix: allow read-only access in tools/autopilot/settings.json.
8. **Owner questions are waiting:** (10) the XAUUSD chart has been on M1 since the 10-23 16:30 re-init (judge says
   harmless), and (a6) whether to keep breakout in the demo after it failed the belief gate.
9. Old role files: `last-orchestrator/researcher/scanner/tester/fidelity/worker/miner.json` (newest 10-22) still
   look like failed or overdue roles (`last-scanner.json` exit 1, 10-18). Fix: archive them.

## Earlier items
- Item 1 (02:55 order never checked): fixed. The 10:23 judge run covered the Tokyo sell (`2026-10-23_agent-judge.log`
  line 13), and after each limit on 10-23 the relay resumed the judge (10:23, 15:25, 20:25). Closed.
- Item 6 (builder repeated one blocked item 41 times): not seen again. 14 builder runs on 10-23/24, each on a new item
  and each ending with exit 0. Closed, but the relay guard is still not built.
- Item 7 (10.7 h silence on 10-22): no gap over 1 h from 10-23 00:00 to 10-24 07:03 in the relay and keeper-steps
  logs. Closed.
- Item 8 (breakout "failed, retcode 10009"): fixed by the deal-0 change in 1.07 (now on the demo in 1.10). The 10-21
  and 10-23 breakout fills log as "bought/sold". Closed.
- Items 2, 3, 4, 5, 9 are still open (now 2, 4, 7, 5, 9 above).

## Watching
- Finder `empty_streak` is **72** (owner's choice, no brake). 84 runs today and about 346 numbered runs so far, every
  one "0 ideas" with the steer examples (carry, VRP, policy gap) already rejected.
- Budget: week from 10-23 18:00, $36.61 of $100 (fraction 0.366, skip false). Today: finder $19.98, builder $1.10.
- Queue: 25 lines, all parse, no duplicate ids, nothing at "testing" or "tester". 21 rejected, 4 data items done.
  `data-tries.json`: data_fred_dgs10 1 (done). No tester-help or to-judge file.
- The monitor ran Friday 10-23 at 23:16 (no ALERT, exit 0). The portfolio manager is due today at 10:00 (install.ps1:7)
  and has not run yet (no last-portfolio.json). Check that it ran in the next report.
- Demo log: last check-in 10-23 23:16 (monitor), no unanswered ALERT. Today (Saturday): 0 EA lines, as expected.
  Window open until 10-25 18:00.
