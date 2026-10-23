# Gaps report - 2026-10-23 07:10 (doctor)

Health: **amber** - the relay, the keeper and the demo (AurumFunded 1.10) run. But a demo order went unchecked after
a limit, the fidelity week has no P/L or slippage to compare, and the finder uses most of the spend.

## Fixed this run
- `docs/HANDOFF.md` (Next pipeline work, a4): it said the demo "keeps 1.06" and offered an optional 1.09 copy. The
  logs show Terminal 16 restarted at 2026-10-23 01:45:11 with AurumFunded attached (keeper log). Build 1.10 was
  compiled on 10-22 at 22:29 (commit 2869c12). Both entries now say this. Decision logged at 07:06.

## Open, for Opus
1. **The 02:55 demo order was never checked.** The Tokyo leg sold 0.24 USDJPY at 156.425 (`logs/autopilot/demo-event.json`).
   The judge started at 02:56 and hit the session limit at 03:00. The log says "the hand-over stays on judge"
   (`2026-10-23_agent-judge.log`), and dispatch stopped retrying at 03:00:02. When the relay came back at 05:25:04 it
   started the finder instead (`2026-10-23_relay.log`). Fix in relay.ps1 / dispatch: keep the demo event and the
   limit-rerun hand-over until a judge run ends with exit 0. The order itself looks as designed: the 25th is a
   Sunday, so Friday the 23rd is a settlement day (`Legs.mqh:589`). The 23:15 monitor check will cover it.
2. **The fidelity week (due today) has no P/L or slippage data.** `tools/demo_check.py:19` drops every line with a
   run of 6 or more digits, and the journal's deal and order lines carry tickets that long. So
   `journal_trade_lines` has been 0 on every day (demo_log 10-21 and 10-22, and today). Fix: mask the digit runs
   instead of dropping the line, and have the monitor log firm-day, close and P/L lines (old item 6).
3. **demo_check counts noise orders as "other".** `demo_check.py:20,42-46` looks for the leg name, but the noise
   lines ("US100.cash bought 0.09 lots ... bands") have none. Fix: classify a line that has "bands" as noise, or add
   a "noise:" prefix in the EA log (old item 5).
4. **Agents cannot read their own large tool results.** Read and Grep on `~/.claude/projects/*/tool-results/*` were
   refused: finder 10-22 20:00, 20:08, 20:14 and 10-23 01:23; miner 10-22 00:45, 01:39, 03:50, 03:56. These files
   hold fetched papers that were too long to show inline, so a full read (lesson 15) fails. Fix: allow read-only
   access to that folder in tools/autopilot/settings.json.
5. **Refused heredoc writes** (`python - <<'E'`, `cat >> ... <<EOF`): finder 10-23 02:27, 05:27, 06:56, miner and
   worker on 10-22. The runs went on, but turns are wasted. Fix: tell the finder and builder prompts to use the Write
   tool or `python tools/...` (prompt change, owner).
6. **The builder repeated one blocked item 41 times** on 10-22 between 16:22 and 19:45: paper_fx_value_rer waiting
   on data_fred_cpi_g10 (`2026-10-22_agent-builder.log`). Both items are now "rejected" and the data-try cap holds
   (`data-tries.json`: data_fred_dgs10 1). Fix: have the relay skip a builder item whose data item is not done,
   the same way the data cap does.
7. **The relay and the keeper were both silent on 10-22 from 03:57 to 14:40** (10.7 h; relay and keeper-steps logs).
   No limit is logged there and the keeper restarted at 15:52, so the PC was probably off or asleep. Today's only gap
   (03:00-05:25) is the session limit. If the PC was not off, check the task history.
8. Breakout log line: a placed order is logged as "failed, retcode 10009", but 10009 means done (EA log fix,
   reviewer). Open from the last report.
9. Old role names: `last-orchestrator/researcher/scanner/tester/fidelity/worker/miner.json` are still in
   logs/autopilot (the newest is from 10-22). Fix: archive them so they do not look like failed or overdue roles.

## Earlier items
- Last report's items 1-3 (doctor task, gate trial count, T16 on 1.10): still fixed.
- Item 7 (`memory.py decide` refused): no refusal on 10-22 or 10-23. This run's decide call worked. Closed.
- The relay data loop: items still had no id in the relay log at 00:00-00:41, and the finder ran 9 empty times. From
  02:30 the id is logged and counted. Fixed.

## Watching
- Finder `empty_streak` is 30 (owner's choice, no brake). It ran 65 times today by 07:00, about 2-3 min a run, for
  $13.67 of today's $16.81. Every run commits and pushes (about 60 "Finder: 0 ideas" commits today). Each run reports
  the same top gaps: EURUSD has no leg, and carry, volatility premium and the days and weeks+ horizons are thin.
- Budget: $164.02 of $100 this week (fraction 1.64, skip true; information only).
- a6 (keep breakout in the demo?) is pending with the owner. Breakout stays frozen at "tester".
- Queue: 14 lines, all parse, no duplicate ids, nothing at "testing" or "tester". No tester-help or to-judge file.
- Monitor ran 10-21 and 10-22 at 23:15 (no ALERT). The portfolio manager is first due Saturday 2026-10-24.
- Demo log: last check-in 10-22 23:15, no ALERT, no errors. The breakout skip on 10-22 is the RiskLots floor.
