# AurumFunded XAUUSD M15, legs on (job j3, second run), 2024-01-01 to 2026-10-17

Real ticks (99% history quality, 123.5M ticks), deposit 10,000, leverage 1:33, preset AurumFunded_FTMO_funded.set plus InpBreakRiskPct=0.125, InpNoiseMult=0.275.

| Figure | Legs on | Legs off (0505 run) | Expected, legs on (j3 note) |
|---|---|---|---|
| Net profit | +22,148.13 (+221.48%) | +16,767.64 (+167.68%) | about +185-190% |
| Max equity drawdown | 2,363.38 (8.28%) | 1,699.37 (6.67%) | 7.5-8% |
| Max balance drawdown | 2,181.24 (7.69%) | 1,612.17 (6.33%) | n/a |
| Report trades (deals counted in the report) | 3,468 | 1,737 | n/a |
| Won | 1,737 (50.09%) | 969 (55.79%) | n/a |
| Profit factor | 1.50 (gross +66,820.61 / -44,672.48) | 1.60 | n/a |
| Sharpe / recovery | 5.84 / 9.37 | 9.59 / 9.87 | n/a |
| Worst day (daily closing equity) | -2.55% (2024-07-25) | -2.70% | n/a |
| Final balance | 32,148.13 | 26,767.64 | |

Gap to the expectation: profit about 31-36 points above the +185-190% range, drawdown 0.3 points above 7.5-8%.
Leg on vs off: +53.8 points of return (+32% more profit), +1.61 points of equity drawdown.
Return per unit of equity drawdown: legs on 221.48 / 8.28 = 26.7; legs off 167.68 / 6.67 = 25.1.

By year (net): 2024 +4,484.41, 2025 +13,228.87, 2026 +4,434.85 (off: +3,000.49, +11,812.20, +1,954.95).
Months positive: 28 of 34 (off: 24 of 34). Worst months: 2026-01 -939.03, 2026-03 -377.01, 2026-08 -348.88. Best: 2025-04 +3,282.64, 2025-10 +3,114.30, 2024-12 +1,782.44.
By symbol (net): XAUUSD +5,690.92, USDJPY +4,671.28, EURUSD +3,467.90, USDCHF +1,569.83, USDCAD +1,467.67, GBPUSD +1,464.36, AUDUSD +1,084.54, US100.cash +976.53, CADJPY +707.07, GBPJPY +420.91, EURJPY +439.86, AUDJPY +244.07, US500.cash -56.81.
The legs add US100.cash and US500.cash (noise leg) and the break leg trades; the noise leg's US500.cash is slightly negative, US100.cash positive.

Day stop: hit 21 times in this run (off run: 17), "equity ... is 3.0% of the initial balance under the day's start, closing everything":
2024-07-25, 2024-11-06, 2025-05-01, 2025-05-30, 2025-10-03, 2025-10-16, 2025-10-20, 2025-10-24, 2025-11-17, 2025-11-18, 2025-11-20, 2025-12-29, 2025-12-31, 2026-01-20, 2026-02-13, 2026-03-31, 2026-07-31, 2026-08-10, 2026-08-14, 2026-09-15, 2026-10-13.
Versus the off run the legs-on run drops 2026-04-30 and adds 2025-10-16, 2025-11-17, 2025-11-18, 2025-12-29, 2026-09-15.
(The tester log in summary.txt holds both runs; these are the lines from the second run, which starts at 05:49 log time.)

Log: no "not found", "cannot", "failed", "skip" or margin lines.

Reading for the orchestrator (no judgement made here): more profit and more drawdown than the corrected expectation, more day stops than the
off run (21 against 17), as the note predicted. Drawdown stays under the 10% firm limit but is above the model's 6.0% cap-1.0 check.
