# j12: AurumFunded on the shared leg library (FTMO funded preset), 2024-01-01 to 2025-10-09

Run: `AurumFunded_FTMO_funded.set`, XAUUSD M15, 10,000 deposit, 1:33, real ticks (99%), in-sample only
(ends 2025-10-10, before the 2025-10-13 holdout). Legs on by default at half Hydra size (BreakRisk 0.0625,
NoiseMult 0.1375), as in the shared library. tester.ini inputs checked: the preset's FTMO inputs
(DayStop 3.0, MaxStop 8.5, Cap 1.4, MinSize 0.3) and the legs-on defaults are as written.

## Figures

| Measure | j12 (shared library) | j3 legs on (v1.00 run) | j3 legs off (v1.00 run) |
|---|---|---|---|
| Net profit | +14,050.03 (**+140.5%**) | +221.48% | +167.68% |
| Trades | 2,197 (4,395 deals) | | |
| Win rate / profit factor | 52.48% / 1.76 | | |
| Max equity drawdown | **7.50%** (843.24) | 8.28% | 6.67% |
| Max balance drawdown | 6.95% | | |
| Worst day | 2024-05-01, -2.73% | -2.55% | -1.64% |
| Months positive | 17 of 22 | | |
| Sharpe / recovery | 6.9 / 16.66 | | |

By year: 2024 +3,687.99; 2025 (to 10-09) +10,362.04.

Largest contributors by symbol: XAUUSD +4,554.65, EURUSD +2,700.61, USDJPY +1,651.48, USDCHF +1,137.64.
Gold (bell leg) is the largest single symbol; US500.cash +142.42 and US100.cash +184.53 are small, as the
noise half is now at half size.

Best month 2025-04 +2,824.18; worst month 2024-05 -436.72.

## Against the expectation (job `expect`, "sharper yardstick")

- Return: expected about +130-170%. Actual **+140.5%**. Inside the range.
- Equity drawdown: expected 6.7-8.3%. Actual **7.50%**. Inside the range.
- Day stops: expected about 5 (the five j3 legs-on stops before 2025-10-10). Actual **8**.
  - The five j3 dates all appear: 2024-07-25, 2024-11-06, 2025-05-01, 2025-05-30, 2025-10-03.
  - Three extra: **2024-05-01, 2024-08-05, 2025-02-28**. Each is a single day with equity 3.0% of the
    initial balance under the day's start (the EA's day-stop message).
  - The expectation was written from j3's count and does not hold. Gap: 3 more day stops than expected, all
    in the early-to-mid window (2024-05 to 2025-02). Not a rule failure; reported as found.
- Worst day -2.73% (2024-05-01) is the same day as one of the extra stops.

## Log notes

- No "not found", "cannot", "failed", error or margin lines in the run.
- 129 lines "balance too small for the minimum lot" (mostly USDJPY breakout and some GBPJPY, GBPUSD, USDCHF
  at small balances). This is the EA refusing sub-minimum sizes, as in j3 (the same kind of line appears there),
  so it is expected and not an error.
- The phase-3 header shows day stop 300.00 and final stop 9,150.00 on the 10,000 start. No final-stop
  message appears in the log, and the daily curve stays above 10,400 in every day listed.

## Verdict (orchestrator to judge)

Return and drawdown sit inside the expectation; the day-stop count is 8 against about 5, the one clear gap.
No model figure for this exact run exists in the repo, so no share-of-model-growth figure is given here.
Nothing was tuned on this window.
