# j14: AurumFunded, Instant Funding PRO guard (in-sample, 2024-01-01 to 2025-09-30)

Preset `mql5/Experts/AurumFunded/AurumFunded_InstantFunding_pro.set`, XAUUSD M15, 10,000 deposit, 1:33, real ticks
(99%), FTMO demo data. Job j14, tag `ifpro`. The tester input list (`tester.ini`) shows the guard inputs written:
max stop 8.5% fixed (trailing false), lock at +5% to a 3.5% final stop, day stop 3.0%, floating stop 1.7%, room 8.5%,
size minimum 0.3, cap 1.4, 0.0625 breakout and 0.1375 noise legs (the shared library's half-size defaults).

## Result

| Figure | Value |
|---|---|
| Net profit | +10,981.44 (+109.81%), final balance 20,981.44 |
| Profit factor / recovery | 1.71 / 10.97 |
| Trades / win rate | 2,086 / 52.25% (4,173 deals) |
| Equity drawdown (max) | 1,000.67 (6.71%) |
| Balance drawdown (max) | 941.96 (6.32%) |
| Worst day | 2024-08-05, -2.80% (daily curve) |
| Months positive | 16 of 21 |
| By year | 2024 +3,146.03; 2025 (to 09-29) +7,835.41 |
| By symbol (top) | EURUSD +2,640.37; XAUUSD +2,288.48; USDJPY +1,784.67 |

## Against the job's expectation (the guard)

- **First date equity reaches +5%:** 2024-01-09. The log line is
  `equity 10500.31 is 5.0% up, the final stop moves to 9650.00 for good` at 2024-01-09 23:04:40. The daily curve shows
  10,496.34 that day and 10,548.89 on 2024-01-18, so the curve alone would give a later date; the log is used.
- **Final stop after the lock:** 9,650 (3.5% under the start). The log has no final-stop or halt line after the lock,
  and the lowest daily close after it is 10,334.77 (2024-08-08), well above 9,650. The run was not halted.
- **Day stops:** the log has 14 "closing everything until the firm's next day" lines in this run's part:
  - 13 are the 1.7% floating stop ("open positions are about 170 in loss together"), on 2024-02-20, 2024-05-01,
    2024-07-25, 2024-11-06, 2025-02-21, 2025-02-27, 2025-03-03, 2025-04-03, 2025-04-25, 2025-05-01, 2025-05-30,
    2025-06-30 and 2025-09-24.
  - 1 is the 3.0% day stop, on 2024-08-05 (equity 10,501.95 against the day's start 10,802.90).
- **Equity drawdown:** 6.71% (max), at the level the tester reports. The date of this trough is not printed.
- **Worst day:** -2.80% (2024-08-05, daily curve), which is the same day as the one day stop.

## Notes

- The shared library's half-size legs make the PRO run a lower-return path than the 8.5%-stop AurumFunded run (j12,
  +140.5% to 2025-10-10). The end date (2025-09-30) and the day-stop sizing both differ, so the two are not directly
  comparable.
- `summary.txt` holds the log lines of several tester runs. This job's part starts at its own "phase 1 started, final
  stop at 9150.00" line (03:02:07). Earlier lines in the file belong to other jobs and were not used.
- In-sample only: months end 2025-09-30, before the holdout (2025-10-13). Not tuned.
