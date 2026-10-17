# j6 AurumHydra, size 1, legs off (FTMO names), XAUUSD M15, 2024-01-01 to 2026-10-17

Real ticks (99%), deposit 10,000, leverage 1:500, preset AurumHydra_FTMO_size1.set, no `-Set`. Tag size1b_off.

Inputs in `tester.ini` (check done): InpBreakRiskPct=0.0, InpNoiseMult=0.0, InpMonthEndBoost=1.0, InpMaxDrawdownPct=35.0. As the job's `expect` asked.

| Figure | Result | Expected (j6 `expect`) |
|---|---|---|
| Net profit | +72,513.16 (+725.13%) | model legs off +1184%; about +500% at 70% of log growth |
| Trades | 2,262 (won 1,300, 57.47%) | |
| Profit factor | 1.70 | |
| Equity drawdown max | 8,333.74 (12.48%) | model 10.7%; tester likely above |
| Balance drawdown max | 6,711.43 (10.82%) | |
| Recovery / Sharpe | 8.7 / 3.83 | |
| Return per unit of equity DD | 58.1 | model 110 (off) |
| Worst day | 2024-08-05, -5.4% | |
| Months positive | 28 of 34 | |

Gap: about 1.45x the 70%-of-model guess (+725% vs +500%); drawdown 1.8 points over the model's 10.7%. The 35% halt did not matter (peak DD 12.48%).

## By year (net)
2024 +6,336.98; 2025 +44,312.63; 2026 +21,863.55 (to 10-16). Worst months: 2026-01 -5,046.87, 2026-08 -2,283.56, 2024-07 -763.58.

## By symbol (net)
XAUUSD 26,903.20; EURUSD 9,792.63; USDJPY 9,694.64; USDCHF 4,570.77; AUDCAD 4,189.82; GBPUSD 4,192.00; USDCAD 3,452.05; AUDUSD 3,172.61; CADJPY 2,305.01; GBPJPY 1,899.35; AUDJPY 1,416.87; EURJPY 924.21.
No US100.cash or US500.cash: the noise leg did not trade, as it should with legs off. USDJPY magic check (+26/+27 breakout, +28/+29 noise) not done separately from the deal list; the by-symbol list and the 0.0 inputs agree with legs off.

## Log
No "cannot", "not found", "failed" or skip lines found in the log copy (`summary.txt`). Tail: normal trading to 2026-10-16, final balance 82,513.16.

## For the orchestrator
Legs-on run (`size1b_on`, -Set InpBreakRiskPct=0.5,InpNoiseMult=0.275) is next. Compare return per equity DD: off 58.1 here. j5 (legs on plus month-end boost, no halt) gave 111.4, so the boost, not only the legs, may carry much of the j5 gap.
