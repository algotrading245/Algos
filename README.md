# Algos

MT5 trading algorithms: simple, maths-based, one spec per algo under `docs/superpowers/specs/`.

## AurumLadder

A gold zone-recovery ladder for the Vantage cent account (`XAUUSD.pc`). Design and feasibility numbers: [`docs/superpowers/specs/2026-10-09-aurumladder-design.md`](docs/superpowers/specs/2026-10-09-aurumladder-design.md).

Set up on Windows:

1. `powershell -ExecutionPolicy Bypass -File tools\link-terminal.ps1` links `mql5\*\AurumLadder` into Terminal 14.
2. In MetaEditor, compile `Scripts\AurumLadder\LadderTest.mq5` and run it on any chart. The Experts log should end with `0 failed`.
3. Compile `Experts\AurumLadder\AurumLadder.mq5` and backtest it on `XAUUSD.pc` with "Every tick based on real ticks".

Reference maths and tests (any OS): `cd tools && python3 -m unittest`.
