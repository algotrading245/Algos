# j17: AurumFunded vrp2 on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-10-25 21:23: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_vrp.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set none, compare_set ['InpVrpMult=0.5'].

## legs off (`2026-10-25_2025_AurumFunded_vrp2_off`)

| Measure | Value |
|---|---|
| Net profit | +13,416.12 (+134.2%) |
| Trades / win rate | 2280.0 / 52.11% |
| Profit factor | 1.62 |
| Max equity drawdown | 4.16% |
| Worst day | 2024-07-25 -2.55% |
| Return per unit of drawdown | 32.2 |
| By year | 2024 +4,562, 2025 +8,854 |
| History quality | 99% real ticks |

## legs on (`2026-10-25_2049_AurumFunded_vrp2_on`)

| Measure | Value |
|---|---|
| Net profit | +13,737.34 (+137.4%) |
| Trades / win rate | 2301.0 / 52.15% |
| Profit factor | 1.61 |
| Max equity drawdown | 5.99% |
| Worst day | 2024-04-16 -2.74% |
| Return per unit of drawdown | 22.9 |
| By year | 2024 +4,817, 2025 +8,921 |
| History quality | 99% real ticks |

## On against off

Return per unit of equity drawdown: off 32.2, on 22.9 (not higher with the legs on).

## Expected (from the job)

Step 15 for AurumFunded v1.15 (VRP leg: NYSE holiday list, 3-weekday stale limit, VIX from the file vixcls.csv because FTMO has no VIX symbol; fix_vrp_leg_fidelity2). Preset = OFF run (InpVrpMult=0, funded style, InpPropTargetPct 0 so it does not stop at +10% as j16 did); compare_set adds InpVrpMult=0.5 (ON run). Python (research/vrp_gap_equity_indices.py, US500+US100 at 0.5): about +2.6% / 3.7% DD on 10k over 2024.01-2025.09, about 11 entries a year per index, magics +30/+31. Differences from the Python: size fixed at the entry (Python rescales daily), broker stop 5% of equity, 10 D1 bars. Judge against 67-87% of the model (lesson 4). Check the log shows "uses the VIX from the file vixcls.csv" and a VIX line each Monday check; if it says no VIX source, the file is missing (python research/vrp_vix_file.py). Random-long control (research/vrp_gap_equity_indices.out.txt, 50 seeds): VRP Sharpe 2018+ is the median of random longs, so expect mostly equity beta. Do not tune on this window.

## Log lines worth a look

- `2026-10-25_2049_AurumFunded_vrp2_on`: IL	2	21:09:06.245	Core 1	2024.10.28 00:05:01   failed market sell 0.44 US500.cash, close #2048 buy 0.44 US500.cash 5699.15 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: KG	0	21:09:06.245	Core 1	2024.10.28 00:05:01   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-10-25_2049_AurumFunded_vrp2_on`: MO	2	21:09:06.245	Core 1	2024.10.28 00:05:01   failed market sell 0.08 US100.cash, close #2049 buy 0.08 US100.cash 19804.95 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: LM	2	21:09:06.245	Core 1	2024.10.28 00:05:11   failed market sell 0.44 US500.cash, close #2048 buy 0.44 US500.cash 5699.15 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: RG	0	21:09:06.245	Core 1	2024.10.28 00:05:11   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-10-25_2049_AurumFunded_vrp2_on`: DN	2	21:09:06.245	Core 1	2024.10.28 00:05:11   failed market sell 0.08 US100.cash, close #2049 buy 0.08 US100.cash 19804.95 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: JG	0	21:09:06.245	Core 1	2024.10.28 00:05:11   AurumFunded: close on US100.cash failed, retcode 10018 (market closed)
- `2026-10-25_2049_AurumFunded_vrp2_on`: FM	2	21:09:06.245	Core 1	2024.10.28 00:05:22   failed market sell 0.44 US500.cash, close #2048 buy 0.44 US500.cash 5699.15 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: HG	0	21:09:06.245	Core 1	2024.10.28 00:05:22   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-10-25_2049_AurumFunded_vrp2_on`: RN	2	21:09:06.245	Core 1	2024.10.28 00:05:22   failed market sell 0.08 US100.cash, close #2049 buy 0.08 US100.cash 19804.95 [Market closed]
- `2026-10-25_2049_AurumFunded_vrp2_on`: PF	0	21:09:06.245	Core 1	2024.10.28 00:05:22   AurumFunded: close on US100.cash failed, retcode 10018 (market closed)
- `2026-10-25_2049_AurumFunded_vrp2_on`: GM	2	21:09:06.245	Core 1	2024.10.28 00:05:32   failed market sell 0.44 US500.cash, close #2048 buy 0.44 US500.cash 5699.15 [Market closed]
