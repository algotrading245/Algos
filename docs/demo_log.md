# Demo log

## 2026-10-17 (Saturday)

- Trades per leg: not logged (0 EA lines, 0 orders, 0 journal trade lines).
- P/L of the day: not logged.
- Slippage on fills: not logged (no fills).
- Day stop / final stop / margin error / trades without broker stop: none in the log.
- Odd: no trades logged; EA not attached? Saturday, so the forex market is closed and zero activity is expected; the log file 20261017.log exists. Tester window open until 2026-10-18 18:00, Terminal 16 reported running.

## 2026-10-19 (Monday) — ALERT: demo EA not attached

- Found by the orchestrator at 07:36 local. AurumFunded is on no chart of Terminal 16 and has not been since
  2026-10-17 04:57:06 (journal: "expert AurumFunded (XAUUSD,M15) removed"). It had loaded at 04:33:55 that day.
- After that the terminal ran tester configs until 2026-10-18 01:20:43. The keeper then restarted it plain at 01:24:53
  ("Terminal 16: started", not "started, AurumFunded attached"). The journal has no Experts line after that start.
  It logged in to the demo with 0 positions and 0 orders, and it showed 0 positions again on the 23:01 reconnect.
- The saved charts (Profiles/Charts/Default chart01-04.chr, written 2026-10-18 01:20:40) contain no `<expert>`
  block. The EA log (MQL5/Logs) exists only for 20261017. demo_check for 2026-10-19 reports "ok" with 0 EA lines.
- Result: no demo trading since Saturday. The clean out-of-sample demo test due to start today has not started.
  Agents may not attach an EA, so the owner has to re-attach it (HANDOFF "Waiting on the owner", approvals a4).
- Likely cause: the keeper copy that ran at 01:24 had been started on 10-17, before the attach branch was added to
  keeper.ps1, so it ran the old code. The attach check also runs only while Terminal 16 is closed, so a terminal
  that stays open without the EA is never caught.

## 2026-10-19 (Monday), 15:30 update: demo EA attached; demo_check ALERT is a false alarm

- Found by the orchestrator at 15:30 local. At 14:53:44 Terminal 16 was shut down and restarted at 14:53:59 from
  `tools/autopilot/t16_attach.ini`. At 14:54:09 the journal says "16 inputs read from ... AurumFunded_FTMO_phase1_legs.set"
  and "expert AurumFunded (XAUUSD,M15) loaded successfully". The EA log prints the 1.06 firm-day line, so the build
  is 1.06. The clean demo test runs from 14:54 today.
- **Leverage and margin (the open fidelity question):** "account leverage 1:100, margin of 1 lot in EUR, XAUUSD
  7417.67 at 4162.76, USDJPY 890.96 at 158.365, EURUSD 1000.00 at 1.12241, AUDCAD 622.02 at 0.9839, US500.cash
  137.11 at 7694.45". At EURUSD 1.12241 that is gold 1:50.0, USDJPY 1:100.0, EURUSD 1:100, US500.cash 1:50.0 (at
  contract size 1). That is the tester install's setting (1:100, gold 1:50), so j12-j14 are the right reference for
  the demo, and j3 (Terminal 16 tester at 1:33, gold 1:16.5) is not.
- **Account currency is EUR**, while the tester jobs use a deposit of 10000 USD. The firm's limits are in EUR: "firm day
  2026.10.19, day start 10000.00, day stop at 9700.00, final stop at 9150.00 (static)". Compare demo and tester in %
  of the balance, not in currency. The P&L of USD-quoted symbols carries the EURUSD move.
- **Trades:** 1 order, 1 deal: a breakout market buy of 0.01 USDJPY with sl 157.700, "done in 180.438 ms". The deal
  filled at 158.365 three ms after the order result. Range 157.700-158.143 (0.73x its 60-day average).
- **The ALERT is false.** demo_check reported "breakout order on USDJPY failed, retcode 10009 (done at 0.000)".
  10009 is TRADE_RETCODE_DONE. The EA judges `!ok || g_trade.ResultDeal()==0` (`Legs.mqh:1630`), and FTMO's market
  execution returns the order with deal 0; the deal comes moments later. So the fill was logged as a failure and
  its "broke its range, bought" line is missing. No duplicate: on the next tick `HeldLots` (`Legs.mqh:1605`) sees the
  position. The same deal-0 test is on the grid (915), fix (1156), stock-fall (1258), Tokyo-morning (1375),
  after-holiday (1513) and noise (1843) legs. Their next-tick guards (HeldLots / TradedSince, the grid's level
  count) stop a repeat unless a tick arrives before the position shows. The demo has no repeat order so far.
- **Late-attach entry:** the leg bought on the first tick after the attach, 22 pips above the range high, because
  the break had happened before 14:54 and nothing limits how late the entry may come. The tester would have bought
  at the break, nearer 158.143. Fidelity should flag today's breakout fill as a restart artefact, not a model gap.
  Any mid-session restart by the keeper can cause the same thing.

## 2026-10-20 (Tuesday): ALERT is the deal-0 false alarm again; one unplanned restart, no harm

Checked on 2026-10-21 (orchestrator). The demo still runs AurumFunded 1.06; the repo's 1.07 has the deal-0 fix.

- **The ALERT is false.** The Tokyo leg sold 0.63 USDJPY at 02:55:00, filled at 158.558. That is 1 order and 1 deal,
  with no repeat. The ALERT is the same 10009/deal-0 read as on 10-19.
- **Unplanned restart:** the EA was removed at 04:12:58 and the terminal exited cleanly at 04:13:21. The keeper's 10-20
  log starts at 04:14:22; its 10-19 log ends at 14:54, so the keeper itself was restarted. It relaunched T16 with the
  attach ini at 04:14:28, and the EA loaded at 04:14:35 and synced 1 position. The cause of the keeper restart is not
  in the logs (a PC or scheduled-task restart?).
- **Tokyo exit on time:** the position closed at 04:24:59 at 158.432, the planned 90-min end, so the restart did no
  harm. The leverage line prints twice (00:05 and 04:14).
- **Other trades:** each was 1 order with no repeat.

  | Leg | Side and size | Opened | Closed |
  |---|---|---|---|
  | breakout | sell 0.02 USDJPY | 158.106 at 09:40 (range 158.106-158.600, 0.81x) | 157.985 at 16:59:59 |
  | midday | sell 0.44 EURUSD | 1.12121 at 12:30 | 1.12110 at 13:59:59 |
  | US500.cash | buy 0.70 | 7743.15 at 16:30 | 7717.55 at 17:30 |
  | US100.cash | buy 0.09 | 29689.08 at 16:30 | 29560.13 at 17:30 |

  The bell leg was skipped (move -0.45 is below 1.5x the average 3.30).
- **Account:** the firm day started at 9992.46 EUR; the day stop was 9692.46 and the final stop is 9150.00. Neither
  was hit.
- **Agent runs:** every relay run on 10-20 ended at once with "weekly limit, resets Oct 23 18:00". So no orchestrator
  or fidelity run happened between 10-19 15:35 and this run.

## 2026-10-21 (Wednesday)

- demo_check ok; 1 EA line so far.
- 05:32 local: still no orders, as expected. The Tokyo leg trades only on settlement days (dates divisible by 5, or
  the Friday before one that falls on a weekend; `Legs.mqh:589`), so the 21st has no Tokyo trade. The breakout and
  noise legs open later in the day.
- 12:36 local: no ALERT. The firm day started at 10011.14 EUR, with the day stop at 9711.14 and the final stop at
  9150.00 (static). At 09:00 the USDJPY range was 158.025-158.388, 0.59x its 60-day average. That is inside the
  filter (`InpBreakMinRange` 0.25, `Legs.mqh:1618`), so the breakout leg is armed and waiting for a break. At
  12:29:59 the midday leg sold 0.42 EURUSD at 1.12258, with the stop at 1.12458 and model weight 1.19. That is
  1 order with no repeat. Fills are compared with the tester after the first demo week (10-23).
- 13:16 local: no ALERT. At 12:56:54 the breakout leg sold 0.03 USDJPY at 158.025, the range low, with the stop at
  158.388, the range high. That is 1 order with no repeat.
- 19:00 local: no ALERT. The noise leg bought 0.09 US100.cash twice: at 17:59:59 at 29856.58 (bands 29832.19 /
  29356.58) and at 18:59:59 at 29884.08 (bands 29838.62 / 29350.19). The leg never adds to a held position. It skips
  a new entry while it holds one (`Legs.mqh:1864-1880`). Before it buys again, it closes the position once the bid is
  below max(upper band, day average). So the second buy follows an exit at the 18:30 or 19:00 check. The EA does not
  log noise exits, so the demo log cannot show which check closed it. The fill comparison (10-23) will show it from
  the deal history.
- 20:31 local: no ALERT. At 20:29:59 the noise leg bought 0.09 US100.cash at 29896.58 (bands 29864.07 / 29324.90),
  its third buy today with the same size. It again follows an exit of the held position: the leg cannot add while it
  holds one (`Legs.mqh:1864-1880`). The exit can fall in the same check as the re-entry. When the day average lies
  above the bid and the bid above the upper band, the leg closes and buys again at once. The Python model does the
  same and charges the cost of each close (`research/noise_area_index.py:106-117`), so this churn is in the
  expectation. The deal history at the 10-23 fill comparison shows which checks closed the positions.


