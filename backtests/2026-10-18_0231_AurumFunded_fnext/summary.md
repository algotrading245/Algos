# j13: AurumFunded, FundedNext Stellar Instant guard (in-sample, 2024-01-01 to 2025-09-30)

Preset `mql5/Experts/AurumFunded/AurumFunded_FundedNext_instant.set`, XAUUSD M15, 10,000 deposit, 1:33, real ticks
(99%), FTMO demo data. Job j13, tag `fnext`. The tester input list (`tester.ini`) shows the guard inputs written:
day stop 3.0%, max stop 4.5% trailing, room 4.5%, size 0.3, cap 1.0, 0.0625 breakout and 0.1375 noise legs.

## Result

| Figure | Value |
|---|---|
| Net profit | +4,243.05 (+42.43%), final balance 14,243.05 |
| Profit factor / recovery | 1.82 / 16.69 |
| Trades / win rate | 1,853 / 52.73% |
| Equity drawdown (max) | 254.22 (2.39%) |
| Balance drawdown (max) | 235.35 (2.22%) |
| Worst day | 2024-08-05, -0.81% |
| Months positive | 17 of 21 |
| By year | 2024 +1,577.53; 2025 (to 09-29) +2,665.52 |
| By symbol (top) | XAUUSD +1,149.76; EURUSD +852.51; USDJPY +608.73 |

## Against the job's expectation

- **First date equity reaches +5% (payout):** 2024-05-01, daily close 10,503.65 (result.json curve). The EA logs no
  payout event, so the date is read from the daily curve.
- **Guard halt:** none. The log has one phase line, "phase 1 started ... final stop at 9550.00" (4.5% under the 10,000
  start), and no later stop, halt or phase-change line. The lowest daily close is 10,175.19 (2024-01-02), far above
  9,550. The trailing move of the stop is not printed in the log, so the level it reached is not checked here.
- **Equity drawdown:** 2.39%, within the expected shape for a 0.3-size run (the job gives no figure).
- **Worst day:** -0.81% (2024-08-05). No day-stop line appears in the log (day stop 3% of the initial balance).

## Notes

- The return (+42%) is well below the half-size AurumFunded legs-on run (j12, +140.5% to 2025-10-10). That is expected
  with size 0.3 and a short end date: the FundedNext guard sizes the position down on purpose.
- `summary.txt` holds the log lines of more than one tester run; the j13 part starts with its own "phase 1 started"
  line at 02:38 (the first lines belong to an earlier run). No guard, halt or day-stop line appears in that part.
- In-sample only: months end 2025-09-30, before the holdout (2025-10-13). Not tuned.
