# j6 AurumHydra, size 1, legs on (FTMO names), XAUUSD M15, 2024-01-01 to 2026-10-17

Real ticks (99%), deposit 10,000, leverage 1:500, preset AurumHydra_FTMO_size1.set, `-Set InpBreakRiskPct=0.5,InpNoiseMult=0.275`. Tag size1b_on.

Inputs in `tester.ini` (check done): InpBreakRiskPct=0.5, InpNoiseMult=0.275, InpMonthEndBoost=1.0, InpMaxDrawdownPct=35.0. As the job's `expect` asked.

| Figure | Result | Expected (j6 `expect`) |
|---|---|---|
| Net profit | +107,618.20 (+1076.18%) | model legs on +1574%; j5 (with month-end boost, no halt) +1460%, clean run near or a little under |
| Trades | 4,173 (won 2,145, 51.40%) | j5: 4,174 |
| Profit factor | 1.49 | j5: 1.53 |
| Equity drawdown max | 13,335.78 (15.54%) | model 11.5%; j5 13.11% |
| Balance drawdown max | 11,957.14 (14.87%) | |
| Recovery / Sharpe | 8.07 / 3.98 | |
| Return per unit of equity DD | 69.2 | model 136 (on); off run here 58.1; j5 111.4 |
| Worst day | 2024-08-05, -5.38% | off run: -5.4% |
| Months positive | 28 of 34 | |

Gap: return is 384 points under j5 (1076% vs 1460%), so "a little under" is more than a little; drawdown 2.4 points above j5 and 4 above the model.

## Legs on vs off (step 16)
| | Off (size1b_off) | On (size1b_on) |
|---|---|---|
| Return | +725.13% | +1076.18% |
| Equity DD | 12.48% | 15.54% |
| Return per unit of equity DD | 58.1 | 69.2 |
| Profit factor | 1.70 | 1.49 |
| Trades | 2,262 | 4,173 |

Return per equity DD is higher with the legs on (69.2 vs 58.1, +19%). Net profit +48% more, drawdown +3.06 points.

## By year (net)
2024 +9,627.37; 2025 +59,145.62; 2026 +38,845.21 (to 10-16). Worst months: 2026-01 -10,243.90, 2026-08 -1,834.25, 2026-06 -1,139.68.

## By symbol (net)
XAUUSD 34,033.65; USDJPY 25,859.78; EURUSD 12,094.31; USDCHF 5,630.44; AUDCAD 5,431.05; GBPUSD 5,232.82; USDCAD 4,297.73; US100.cash 4,181.31; AUDUSD 3,864.74; CADJPY 2,847.18; GBPJPY 2,349.07; AUDJPY 1,776.23; EURJPY 1,112.19; US500.cash -1,092.30.
US100.cash and US500.cash trade in the on run (noise leg), absent in the off run. US500.cash is slightly negative.

## Log
No "cannot", "not found", "failed" or skip lines found in the log copy (`summary.txt`). Tail: normal trading to 2026-10-16, final balance 117,618.20.

## For the orchestrator
Job j6 collected. Compared with j5 (legs on + month-end boost 2.0, no halt): +1460% / 13.11% / PF 1.53, so the boost adds about +384 points of return and the boost run also had 2.4 points less drawdown (return per DD 111 vs 69).
