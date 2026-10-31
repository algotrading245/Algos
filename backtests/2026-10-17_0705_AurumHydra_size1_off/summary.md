# j5 AurumHydra, size 1, legs off (FTMO names), XAUUSD M15, 2024-01-01 to 2026-10-16

Real ticks (99%), deposit 10,000, leverage 1:500, preset AurumHydra_FTMO_size1.set, no `-Set`.

| Figure | Tester | Expected (j5 `expect`) | Gap |
|---|---|---|---|
| Net profit | +146,043.94 (+1460.44%) | model +1184%; about +500% at 70% of log growth | well above both |
| Final balance | 156,043.94 | | |
| Trades | 4,174 (won 2,145, 51.39%) | | |
| Profit factor | 1.53 | | |
| Equity drawdown max | 13,322.55 (13.11%) | model 10.7%; tester roughly 15-25% | below the 15-25% guess, 2.4 points over the model |
| Balance drawdown max | 11,761.98 (12.43%) | | |
| Recovery factor / Sharpe | 10.96 / 4.06 | | |
| Worst day | 2026-06-30, -5.94% | | |
| Months positive | 29 of 34 | | |
| Return per unit of equity DD | 1460.44 / 13.11 = 111.4 | model 110 (legs off) | matches the model |

## By year (net per calendar year, from the deal list)
2024: +10,845.31 | 2025: +71,845.32 | 2026 (to 10-16): +63,353.31

Losing months: 2024-05 (-173), 2024-08 (-360), 2026-01 (-9,295), 2026-06 (-6,329), 2026-08 (-1,477). Biggest: 2025-10 (+24,259), 2026-07 (+22,254), 2026-09 (+20,224).

## By symbol (net)
XAUUSD +41,928 | USDJPY +36,979 | EURUSD +14,498 | GBPUSD +9,683 | USDCHF +8,167 | USDCAD +7,540 | AUDUSD +6,917 | AUDCAD +6,441 | US100.cash +5,890 | AUDJPY +3,196 | GBPJPY +2,306 | CADJPY +2,289 | EURJPY +1,245 | US500.cash -1,036

14 symbols traded, no symbol missing from the set-up fault of j4 (all FTMO names resolved). Legs off, so no noise or breakout legs expected beyond the base legs; US100.cash and US500.cash show up in the by-symbol list already (the index legs of the base set).

## Log
No "not found", "cannot", "failed" or margin lines seen in the tail of the log (end of run: normal trading on 2026-10-15/16, final balance 156,043.94). The tail was the only part read here.

## For the orchestrator
The figures above are for judging; the share of the model's log growth was not computed here. The legs-on run (tag `size1_on`, `InpBreakRiskPct=0.5`, `InpNoiseMult=0.275`) starts next; step 16 compares return per unit of equity drawdown, off = 111.4.
