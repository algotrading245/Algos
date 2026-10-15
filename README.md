# Algos

MT5 trading algorithms: simple, maths-based, one spec per algo under `docs/superpowers/specs/`.

## AurumLadder

A gold zone-recovery ladder for the Vantage cent account (`XAUUSD.pc`). Design and feasibility numbers: [`docs/superpowers/specs/2026-10-09-aurumladder-design.md`](docs/superpowers/specs/2026-10-09-aurumladder-design.md).

### Backtest on Windows (Terminal 15)

Backtests run in Terminal 15, a spare install, because MT5 ignores tester configs while an install is open and Terminals 1–14 stay running. One-time setup: open `C:\Program Files\MetaTrader 5 - 15\terminal64.exe`, log in to the Vantage cent account (the read-only investor password is enough), add `XAUUSD.pc` to Market Watch, then File → Exit. Then, from the repo folder:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run unittest   # compile + in-terminal maths tests
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run baseline   # defaults, 2023-10-09 to 2025-10-09
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run tune       # genetic optimisation, same 2 years
powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run holdout    # final year, ONCE, with the chosen inputs
```

Each run links the sources into Terminal 15 (`-Terminal <install path>` picks another), compiles them, runs on real ticks for `XAUUSD.pc` with a 40,000 USC deposit, and saves the report, a per-ladder `ladders.csv` and the acceptance verdict (`summary.txt`) to `backtests\<date>_<run>\`. Configs live in `tester\`. Before the holdout run, copy the inputs picked from the tune results into `tester\holdout.ini`.

Reference maths and tests (any OS): `cd tools && python3 -m unittest`.

## AurumFunded (prop-firm EA)

The FTMO 2-Step Swing EA; design, simulation and open points are in [`docs/HANDOFF.md`](docs/HANDOFF.md). To run it in
the Strategy Tester of an FTMO MT5 install (a free trial account is enough for the symbols and history), close that
install and run from the repo folder:

```powershell
powershell -ExecutionPolicy Bypass -File tools\run-funded.ps1                         # phase 1 preset, 2024 to today
powershell -ExecutionPolicy Bypass -File tools\run-funded.ps1 -Preset funded -From 2023.01.01
```

`-Terminal <install folder>` picks another install (default `C:\Program Files\FTMO MetaTrader 5`). The script links
the sources, compiles, runs on real ticks with a 100,000 USD deposit at 1:30, and saves the report and the EA's own
log lines to `backtests\<date>_funded_<preset>\`. It was written in a cloud session without PowerShell and has not
been run yet; report any error it prints.

### Tests to run next (Strategy Tester, every tick based on real ticks, from 2024-01-01)

None of these was compiled in the cloud session that wrote them; report any compile error.

1. `AurumBreakout` (USD/JPY London breakout) on **USDJPY**, M1, preset `mql5/Experts/AurumBreakout/AurumBreakout_USDJPY.set`
   (needs about three months of M1 history before the first trade). Backtest expectation: Sharpe ~0.8-1.0 at the
   real ~1.2 bp cost, roughly 45-50% winners, ~300 trades a year.
2. `AurumNoise` (noise-area index momentum) on **US500.cash** and **US100.cash**, M1, presets in
   `mql5/Experts/AurumNoise/`. Expectation: Sharpe ~0.7 (S&P 500) and ~0.9 (Nasdaq) at their spreads.
3. If both hold on FTMO's data: `AurumFunded` 1.03 with a funded preset plus `InpBreakRiskPct=0.125` and
   `InpNoiseMult=0.275` (`-Preset funded` in `tools\run-funded.ps1`, then set the two inputs), or `AurumHydra` 1.33
   with `InpBreakRiskPct=0.5` and `InpNoiseMult=0.275`.

Prop routes and their simulated first-payout times (details in `docs/HANDOFF.md`): FTMO 2-Step Swing (median ~9.6
months), FTMO 1-Step (~7.8 months at size 0.5, `-Preset 1step` / `1step_funded`; verify its maximum loss on ftmo.com), FundedNext Stellar Instant (~1.4 months, or ~4.3 if it has a 40% consistency rule - ask them), Instant
Funding PRO (~2.5 months at size 0.5, preset `AurumFunded_InstantFunding_pro.set` - ask them the Account Drawdown
figure, their EA policy and their server clock).
