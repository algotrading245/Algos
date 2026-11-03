# AurumFunded, FTMO funded-account preset, Strategy Tester (FTMO-Demo)

Run by the owner on 2026-10-15: XAUUSD M15, 2024-01-01 to 2026-10-14, real ticks, 10,000 USD, 1:33, inputs of
`AurumFunded_FTMO_funded.set` (no target, size 0.5, day stop 3%, final stop 8.5%). Sizes follow the balance, so the
result compounds.

Result: **+11,053.77 (+110%) in 34 months**, 1,760 trades on 667 days, profit factor 1.63. Equity drawdown at most
4.08% (balance 3.05%). Worst day -1.64% of the day's starting balance (2026-01-20); no day below -2%, so the 3% day
stop and FTMO's 5% were never near. 23 of 34 months positive, worst month -2.09%, median +2.14%, mean +2.25%.
By year: 2024 +2,018, 2025 +6,698, 2026 to 10-13 +2,338.

| Leg | Trades | Net USD | Commission |
|---|---|---|---|
| fix | 224 | +2,290.2 | -99.5 |
| dip | 50 | +2,229.2 | -12.2 |
| Tokyo | 179 | +1,859.8 | -466.5 |
| after holiday | 150 | +1,287.5 | -138.4 |
| midday | 664 | +1,098.4 | -954.1 |
| bell | 99 | +807.2 | -122.5 |
| stock fall | 95 | +770.6 | -50.0 |
| morning | 156 | +652.0 | -87.5 |
| after fix | 143 | +58.7 | -110.2 |

Against the Python model of the same legs at size 0.5 on the same dates (`marketdata/hydra_legs_daily.csv.gz`):
+189% compounded (simple sum +108%). The tester keeps about 70% of the model's log growth (ln 2.10 against ln 2.89).
On an FTMO 100k funded account at the 80% split, the average month here would pay about 1,800 USD before the
scaling plan, with the worst month at -2.1%.
