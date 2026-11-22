# AurumBreakout, USDJPY, Strategy Tester (FTMO-Demo)

Run on 2026-10-17 by `tools/run-tester.ps1 -Detach` (pipeline step 15): USDJPY M1, 2024-01-01 to 2026-10-01, every
tick based on real ticks (99% real-tick history, 90.7 million ticks), 10,000 USD, 1:100, `AurumBreakout_USDJPY.set`
(risk 0.25% per side, both sides). The first launch at 00:56 died with its shell; this is the detached rerun.

Result: **+996.08 (+9.96%) in 33 months**, 771 trades, 47.7% winners, profit factor 1.16, tester Sharpe 1.79,
recovery factor 2.37. Equity drawdown at most 4.02% (balance 3.70%). Worst day -0.91% of the day's starting balance
(2024-05-23). 20 of 33 months positive, worst month -218 (2024-05), best +445, median +23, mean +30.
By year: 2024 +377, 2025 +196, 2026 to 09-30 +423.

| | Expected (Python, measured costs) | Tester | |
|---|---|---|---|
| Trades | 777 | 771 | -0.8% |
| Winners | 47% | 47.7% | |
| Profit factor | 1.14 | 1.16 | |
| Return | +8.6% | +9.96% | |
| Max equity drawdown | 5.0% | 4.02% | |

The tester matches the model within noise, slightly better on return and drawdown; no gap for the reviewer to
explain. Step 15 passed for the standalone EA. Next: step 16, the leg on vs off inside AurumFunded 1.03
(`InpBreakRiskPct=0.125`).
