# AurumFunded XAUUSD M15, legs off (job j3, base run), 2024-01-01 to 2026-10-17

Real ticks (99% history quality, 123.5M ticks), deposit 10,000, leverage 1:33, preset AurumFunded_FTMO_funded.set, no overrides.

| Figure | Tester | Expected (README test 3, legs off) | Gap |
|---|---|---|---|
| Net profit | +16,767.64 (+167.68%) | about +110% (earlier tester run); Python model +189% | +57.7 points over the tester run, 21.3 under the model |
| Max equity drawdown | 1,699.37 (6.67%) | 4.1% (earlier tester run); model 5.2% | 2.6 points more than the tester run |
| Max balance drawdown | 1,612.17 (6.33%) | n/a | |
| Trades | 1,737 | n/a | |
| Win rate | 55.79% (969 won) | n/a | |
| Profit factor | 1.60 (gross +44,863.55 / -28,095.91) | n/a | |
| Sharpe / recovery | 9.59 / 9.87 | n/a | |
| Worst day | -2.70% (2024-07-25, daily closing equity) | -1.64% | 1.06 points worse |

By year (net): 2024 +3,000.49, 2025 +11,812.20, 2026 +1,954.95.
Months positive: 24 of 34. Worst months: 2026-04 -991.87, 2026-08 -393.01, 2026-03 -333.34. Best: 2025-04 +2,504.22, 2025-09 +2,159.97, 2025-10 +2,007.42.
By symbol (net): XAUUSD +5,581.21, USDJPY +3,178.74, EURUSD +2,711.95, USDCHF +1,290.81, USDCAD +1,104.39, GBPUSD +1,032.25, AUDUSD +809.98, EURJPY +368.12, GBPJPY +364.70, CADJPY +338.85, AUDJPY -13.36.

Day stop: hit 17 times in the log ("equity ... is 3.0% of the initial balance under the day's start, closing everything until the firm's next day"):
2024-07-25, 2024-11-06, 2025-05-01, 2025-05-30, 2025-10-03, 2025-10-20, 2025-10-24, 2025-11-20, 2025-12-31, 2026-01-20, 2026-02-13, 2026-03-31, 2026-04-30, 2026-07-31, 2026-08-10, 2026-08-14, 2026-10-13.

Log: no "not found", "cannot", "failed" or margin errors. Final balance 26,767.64.

Reading for the orchestrator (no judgement made here): clearly more profit than the earlier tester run's +110% and more
drawdown than its 4.1%, and the day stop fired on 17 days, where the expectation says none. Worst day is -2.70% on the
daily closing curve, intraday the stop level was reached on each hit. The leg-on run follows.
