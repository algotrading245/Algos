# Algos

MT5 trading algorithms: simple, maths-based, one spec per algo under `docs/superpowers/specs/`.

## AurumLadder

A gold zone-recovery ladder for the Vantage cent account (`XAUUSD.pc`). Design and feasibility numbers: [`docs/superpowers/specs/2026-10-09-aurumladder-design.md`](docs/superpowers/specs/2026-10-09-aurumladder-design.md).

### Backtest on Windows (Terminal 14)

Close Terminal 14 first (MT5 ignores tester configs while that install is open), then from the repo folder:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run unittest   # compile + in-terminal maths tests
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run baseline   # defaults, 2023-10-09 to 2025-10-09
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run tune       # genetic optimisation, same 2 years
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run holdout    # final year, ONCE, with the chosen inputs
```

Each run links the sources into the terminal, compiles them, runs on real ticks for `XAUUSD.pc` with a 40,000 USC deposit, and saves the report, a per-ladder `ladders.csv` and the acceptance verdict (`summary.txt`) to `backtests\<date>_<run>\`. Configs live in `tester\`. Before the holdout run, copy the inputs picked from the tune results into `tester\holdout.ini`.

Reference maths and tests (any OS): `cd tools && python3 -m unittest`.
