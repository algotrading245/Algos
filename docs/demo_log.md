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
- **Account currency is EUR**, while the tester jobs use a deposit of 10000 USD. The firm's limits are in EUR: "firm day 2026.10.19, day start 10000.00, day stop at 9700.00, final stop at 9150.00 (static)". Compare demo and tester in % of the balance, not in currency. The P&L of USD-quoted symbols carries the EURUSD move.
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

## 2026-10-21 (Wednesday), 23:15 check (monitor): no ALERT

Checked by the monitor role. `tools/demo_check.py` reports 8 EA lines, orders midday 1 and other 4, 0 journal trade
lines. The Terminal 16 experts log has 9 AurumFunded lines, all listed below.

- **Trades:** 5 orders today, each 1 order with no repeat. Midday 1 (sell 0.42 EURUSD at 12:29:59, 1.12258). Breakout 1
  (sell 0.03 USDJPY at 12:56:54, 158.025). Noise 3 (buy 0.09 US100.cash at 17:59:59, 18:59:59 and 20:29:59). The noise
  buys match the 19:00 and 20:31 notes above and add nothing new.
- **New since 20:31:** one skip line at 21:59:59, "bell move +1.25 is below 1.5 x average 3.25, no trade today".
  It is a skip, not an order.
- **Account:** the firm day started at 10011.14 EUR, with the day stop at 9711.14 and the final stop at 9150.00 (static).
  Neither was hit. No margin error was logged.
- **Clock check and errors:** no clock-check skips and no errors in the log.
- **P/L of the day:** not logged (the EA log has no close lines for today).
- **Slippage:** not logged; the fill comparison with the tester waits for the first demo week (10-23).
- **Trades without a broker stop:** none logged; each open line shows a stop (1.12458, 158.388, and the noise bands).

## 2026-10-22 (Thursday), 16:30 check (judge): no ALERT

`tools/demo_check.py` reports 5 EA lines, orders midday 1 and other 2, 0 journal trade lines, no day stop, final stop,
failure or clock line.

- Midday sold 0.23 EURUSD at 1.12225, stop 1.12422 (1 order).
- Breakout skipped: USD/JPY range 157.290-158.251 (1.58x its 60-day average), "balance too small for the minimum lot
  of USDJPY at a stop of 1.181" (`RiskLots()` floor; see the judge's 14:40 note in `docs/HANDOFF.md`).
- Noise sold 0.68 US500.cash at 7657.45 (bands 7783.22 / 7662.51) and 0.09 US100.cash at 29172.68 (bands 29922.10 /
  29227.01). Both bids were below the lower band, the designed short entry (`Legs.mqh:1880-1887`); one order each, no
  repeat. The checker counts them as "other" (proposed tools change (7) in `docs/HANDOFF.md`).

## 2026-10-22 (Thursday), 23:15 check (monitor): no ALERT

Checked by the monitor role. `tools/demo_check.py` reports ok, 5 EA lines, orders midday 1 and other 2, 0 journal trade lines, and one skip (breakout). The Terminal 16 experts log has 6 AurumFunded lines, the last at 16:29:59. Nothing new was logged after the 16:30 judge check.

- **Trades per leg:** midday 1 (sell 0.23 EURUSD at 12:29:59, 1.12225, stop 1.12422, model weight 1.00). Breakout 0 (skipped at 08:59:59: range 157.290-158.251 at 1.58x its 60-day average, and "balance too small for the minimum lot of USDJPY at a stop of 1.181"). Noise 2 (sell 0.68 US500.cash at 16:29:59, 7657.45, bands 7783.22 / 7662.51; sell 0.09 US100.cash at 16:29:59, 29172.68, bands 29922.10 / 29227.01). One order each, no repeat. No bell, Tokyo, fix or other leg lines today.
- **Account:** the firm-day lines (day start, day stop, final stop) are not logged today, so the day stop and final stop cannot be checked from the log. No margin error logged.
- **P/L of the day:** not logged (no close lines in the EA log).
- **Slippage:** not logged. The log gives fill prices only, not the quote at signal time, so the fills cannot be compared with the tester yet. The fill comparison starts 10-23.
- **Trades without a broker stop:** none. The midday line shows its stop. The noise lines print the bands, not the stop, but the code sets a broker stop for each noise order (`mql5/Include/Aurum/Legs.mqh:2022`, 3 x the leg's volatility from the entry price). The printed line does not show that stop value, so it is not logged.
- **Odd:** the breakout skip is the RiskLots floor (judge notes 14:43 and 16:33 in `docs/HANDOFF.md`), not a fault. The two noise shorts are designed lower-band entries.

## 2026-10-23 (Friday), 10:30 check (judge): no ALERT

`tools/demo_check.py` reports ok, 4 EA lines, orders Tokyo 1 and other 1, 0 journal trade lines, no day stop, final stop,
failure or clock line.

- **Account:** firm day 2026.10.23, day start 10043.55, day stop at 9743.55, final stop at 9150.00 (static).
- **Leverage:** "account leverage 1:100, margin of 1 lot in EUR, XAUUSD 7183.07 at 4029.02" at 00:05, and again at
  01:45:34 after the keeper restart onto AurumFunded 1.10 (gold about 1:50, as on 10-19). `demo_check.py` hides this
  line because it contains "account" (proposed tools change (8) in `docs/HANDOFF.md`).
- Tokyo sold 0.24 USDJPY at 156.425 at 02:55, stop 156.895, model weight 0.50 (1 order).
- Breakout: USD/JPY range 156.075-157.123 (1.70x its 60-day average), bought 0.01 lots at 157.123 at 09:06, stop
  156.075. The 1.048 range is just under the 1.09 above which the 0.01 floor blocks a trade (judge note 10-22 14:40).
  The checker counts it as "other" (tools change (7)).
- **Trades without a broker stop:** none; both order lines show a stop.
- **Slippage:** the fill comparison waits for the full first demo week (fidelity, after today's close).

## 2026-10-23 (Friday), 12:36 check (judge): no ALERT

`tools/demo_check.py` reports ok, 5 EA lines, orders Tokyo 1, other 1, midday 1, 0 journal trade lines.

- **New since 10:30:** at 12:30:00 the midday leg sold 0.44 EURUSD at 1.11993, stop 1.12200, model weight 1.36
  (1 order, no repeat, broker stop set).
- **Size check (midday 10-21 / 10-22 / 10-23: 0.42 / 0.23 / 0.44 lots):** risk at the stop divided by model weight is
  0.63 / 0.40 / 0.60% of balance. With `InpSizeMult` 0.5 and `InpMeridianRiskPct` 1.0 (phase1 preset), that is the
  loss-run factor `Progression()` (`Legs.mqh:519-535`, `InpLossMult` 0.67 / `InpLossNorm` 0.80): 1.25 after a win,
  0.84 after one loss. So 10-21's midday trade closed at a loss (inferred from the size; the EA logs no closes) and
  10-22's at a win. Designed behaviour; the tester runs the same code, so it is in the tester figures.
- No skip, error, day stop or clock line. No ALERT.

## 2026-10-23 (Friday), 15:25 check (judge): ALERT, harmless (a duplicate close)

`tools/demo_check.py` reports ALERT, 6 EA lines, orders Tokyo 1, other 1, midday 1: "close on EURUSD failed,
retcode 10036 (position closed)" at 14:00:00.795.

- **What happened (terminal journal):** the midday exit sent a close for the 12:30 EURUSD sell at 13:59:59.507. It
  was placed at 13:59:59.612 and filled at 14:00:00.736 (1235 ms): bought 0.44 at 1.11902 against the 1.11994 sell,
  about +40 USD before commission. At 14:00:00.792 a second close of the same position was refused ("Position doesn't
  exist"), and the EA logged it as retcode 10036.
- **Cause:** `CloseAll` (`Legs.mqh:357-373`) runs on every tick and once a second, and trades synchronously. On the
  next call, 56 ms after the fill, `PositionsTotal()` still listed the position, so the EA sent the close again.
  Nothing opened, and `Leg()` (`Legs.mqh:779-780`) ignores the return value, so no state changed. The tester fills
  at once, so the tester figures are not affected.
- **Win after loss:** with this win, the next midday size goes up by the 1.25 factor (`Progression()`, 12:36 note).
- No other skip, error, day stop or clock line. The checker and EA changes are proposed as (9) in `docs/HANDOFF.md`.
  The demo's inputs are not changed.

## 2026-10-23 (Friday), 17:03 check (judge): no new ALERT; EA re-initialised on M1 at 16:30

`tools/demo_check.py` still reports the ALERT, but it is the 14:00 duplicate close explained at 15:25. There are 8 EA
lines now; 2 are new:

- **16:30:16, chart now XAUUSD,M1 (it was attached on M15):** the EA ran OnInit again and printed the USD/JPY
  breakout range 156.075-157.123 again. This is likely a chart timeframe change. The terminal journal is written to
  disk only up to 01:45, so the cause is not confirmed. No order was repeated:
  - OnInit resets the breakout state (`Legs.mqh:2319-2320`).
  - The late-start guard (`Legs.mqh:1747-1772`) skips a side that is already held or traded, so the 09:06 high-side
    buy was not sent again.
  - The low side (156.075) stays armed, as it would in an EA that kept running.
  - The loss-run sizing (`Progression()`, `Legs.mqh:519-535`) is read from the 90-day deal history, so the reinit
    does not reset it.
  - The legs read their bars with explicit `PERIOD_*` arguments, so the chart period should not change what they
    trade. Ticks on an M1 chart can arrive at different times, which may shift when an order is sent within a minute.
- **17:00:00, US100.cash bought 0.08 lots at 29120.83, bands 29077.93 / 28742.05:** the noise leg ("other" 2 =
  breakout + noise). Designed; 1 order, no repeat.
- No skip, error, day stop or clock line apart from the 14:00 one. No job and no change to the demo. Owner: please
  confirm whether the XAUUSD chart was switched to M1 at 16:30 (switching back to M15 is the owner's choice; agents do
  not touch the terminal).

## 2026-10-23 (Friday), 20:25 check (judge): no new ALERT; second US100 noise buy at 17:59:59

`tools/demo_check.py` still shows only the explained 14:00 ALERT. There are 9 EA lines; 1 is new:

- **17:59:59.596, US100.cash bought 0.08 lots at 29123.83, bands 29114.00 / 28706.11:** the noise leg's exit and
  re-entry at the same half-hour check, the pattern judged on 10-21 (18:59 and 20:29). The leg cannot add to a held
  position: when it holds one it either keeps it (`continue`) or closes it under max(upper band, session average) and,
  with the bid still above the upper band, buys again (`Legs.mqh:1989-2012`). The close leaves no EA line, and the
  journal is flushed only to 01:45, so the close itself is not visible. The same code runs in the tester.
- No skip, error, day stop or clock line apart from the 14:00 one. No job and no change to the demo.

## 2026-10-23 (Friday), 23:16 check (monitor): no new ALERT; the tool's ALERT is the known 14:00 duplicate close

Checked by the monitor role. `tools/demo_check.py` reports ALERT, 10 EA lines, orders Tokyo 1, other 3, midday 1, 0 journal
trade lines. The flag is the failed close at 14:00:00.795 (retcode 10036), explained in the 15:25 judge check: a second
close of a position already closed at 13:59:59. It is not a monitor trigger (no day stop, final stop, margin error or
trade without a broker stop).

- **Trades per leg (logged opens):** Tokyo 1 (sold 0.24 USDJPY at 156.425 at 02:55, stop 156.895). Breakout 1 (bought 0.01
  USDJPY at 157.123 at 09:06, stop 156.075). Midday 1 (sold 0.44 EURUSD at 1.11993 at 12:30, stop 1.12200; closed at
  13:59:59 by the leg's exit, per the 15:25 note). Noise 2 (bought 0.08 US100.cash at 17:00:00 and at 17:59:59, bands in
  the log). Bell skipped at 21:59:59 (move +0.83 is below 1.5 x the average 2.95). Each leg shows one order, no repeat.
- **Tester comparison:** not possible. Tester jobs end 2025-09-30 (holdout), so there is no tester figure for this day.
- **P/L of the day:** not logged (no P/L line in the EA log, no journal trade lines, no end-of-day equity). Only the midday
  close can be worked out from the logged prices: sold 1.11993 and closed at 1.11902 on 0.44 lots is about +40 USD before
  commission. The other legs' closes are not in the log.
- **Slippage on fills:** not logged (fill prices only, no quote at signal time). The fill comparison waits for fidelity
  after the first demo week.
- **Account:** firm day 2026.10.23, day start 10043.55, day stop 9743.55, final stop 9150.00 (static). No day-stop or
  final-stop line. No margin error. No clock-check skip.
- **Trades without a broker stop:** none shown. Midday and breakout lines print a stop. The noise lines print bands, not the
  stop; the code sets a broker stop for each noise order (`mql5/Include/Aurum/Legs.mqh:2022`), which the printed line does
  not show.
- **Odd:** nothing new. The 16:30 M1 re-initialisation and the 17:59:59 noise buy are the ones judged at 17:03 and 20:25.

## 2026-10-24 and 2026-10-25 (weekend)

No entry: the demo window was closed (Saturday 00:00 to Sunday 18:00), so no trades were expected.

## 2026-10-26 (Monday), 23:15 check (monitor): no ALERT; no trades logged

`tools/demo_check.py` reports ok: 3 EA lines, orders none, 0 journal trade lines, no day stop, final stop, margin error, failure, skip or clock line.

- **Trades per leg:** none. No order was logged for any leg.
- **Reason given in the log:** no trading today, European and US summer time differ. The EA held out for the session; the two regions change clocks on different dates, so session times are off for part of the year.
- **Account:** firm day 2026.10.27 as logged, day start 10000.97, day stop 9700.97, final stop 9150.00 (static). Neither stop was hit; no trade was taken.
- **Leverage:** account leverage 1:100 (gold 7189.40 at 4016.43), the same as the 10-19 reading.
- **P/L of the day:** not logged.
- **Slippage on fills:** not logged (no fills). No tester figure: tester jobs end 2025-09-30 and demo days are after the holdout.
- **Trades without a broker stop:** none (no orders).
- **Odd:** only the summer-time note. Worth a look if the demo should trade every weekday.
- **Fidelity:** docs/fidelity/2026-10-23.md exists, so no fidelity week is due today.
