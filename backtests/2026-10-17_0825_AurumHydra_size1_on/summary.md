# j5 AurumHydra, size 1, legs on (FTMO names), XAUUSD M15, 2024-01-01 to 2026-10-17

Real ticks (99%), deposit 10,000, leverage 1:500, preset AurumHydra_FTMO_size1.set, `-Set InpBreakRiskPct=0.5,InpNoiseMult=0.275`.

| Figure | Legs on | Legs off (size1_off) | Expected (j5 `expect`) |
|---|---|---|---|
| Net profit | +146,043.94 (+1460.44%) | +146,043.94 (+1460.44%) | model +1574% on; about +620% at 70% of log growth |
| Trades | 4,174 (won 2,145, 51.39%) | 4,174 (2,145, 51.39%) | |
| Profit factor | 1.53 | 1.53 | |
| Equity drawdown max | 13,322.55 (13.11%) | 13,322.55 (13.11%) | model 11.5% |
| Balance drawdown max | 11,761.98 (12.43%) | 11,761.98 (12.43%) | |
| Recovery / Sharpe | 10.96 / 4.06 | 10.96 / 4.06 | |
| Return per unit of equity DD | 111.4 | 111.4 | model 110 -> 136 |

## The two runs are identical, so there is no legs-on vs legs-off comparison
Every figure matches to the cent (net, gross profit and loss, trades, drawdowns, equity curve). Step 16's test (return per drawdown higher with the legs on) cannot be read from this pair.

What the files show:
- The report inputs of BOTH runs list `InpBreakRiskPct=0.5` (the off run's report too, although its `tester.ini` and the preset hold no such key; only the on run's `tester.ini` has `InpBreakRiskPct` and `InpNoiseMult`).
- The off run's by-symbol list already held US100.cash and US500.cash (noise leg symbols), as noted in its summary.
- Likely cause (a guess, not checked): the preset does not set these two inputs, so the tester kept the values of the previous run (j4 legs-on used 0.5 / 0.275), and the "off" run ran with the legs on. Then both runs here are legs-on, and the real legs-off figure is missing.
- The log file copied to `summary.txt` holds both runs' lines (the tester log is not cleared between runs), so its leg counts are doubled and cannot separate them.

## By symbol, year, log
Not recomputed; same equity curve and deal count (8,341 deals) as the off run, see its summary.md. Log tail: normal trading to 2026-10-15/16, final balance 156,043.94, no "not found", "cannot", "failed" or margin lines in the tail.

## For the orchestrator
To get a valid pair, rerun legs off with explicit `-Set InpBreakRiskPct=0,InpNoiseMult=0` (and check the report's input list shows 0), then compare with this run. The current +1460% / 13.11% is a legs-on figure (or at least not a clean legs-off one).
