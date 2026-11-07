# j16: AurumFunded vrp on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-10-25 20:16: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_vrp.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set none, compare_set ['InpVrpMult=0.0'].

## legs off (`2026-10-25_1955_AurumFunded_vrp_off`)

| Measure | Value |
|---|---|
| Net profit | +1,000.15 (+10.0%) |
| Trades / win rate | 346.0 / 51.16% |
| Profit factor | 1.44 |
| Max equity drawdown | 3.61% |
| Worst day | 2024-02-20 -1.66% |
| Return per unit of drawdown | 2.8 |
| By year | 2024 +1,000 |
| History quality | 99% real ticks |

## legs on (`2026-10-25_2005_AurumFunded_vrp_on`)

| Measure | Value |
|---|---|
| Net profit | +1,000.15 (+10.0%) |
| Trades / win rate | 346.0 / 51.16% |
| Profit factor | 1.44 |
| Max equity drawdown | 3.61% |
| Worst day | 2024-02-20 -1.66% |
| Return per unit of drawdown | 2.8 |
| By year | 2024 +1,000 |
| History quality | 99% real ticks |

## On against off

Return per unit of equity drawdown: off 2.8, on 2.8 (not higher with the legs on).

## Expected (from the job)

Step 15 for the variance-premium leg (AurumFunded v1.13, research/vrp_gap_equity_indices.py). Leg alone at InpVrpMult 0.5 on 10k, 2024.01-2025.09: about +2.6% / 3.7% DD from the Python daily series (2 indices at 0.25 x the 10%-vol series), about 11 entries a year per index (hold 10 trading days), magics +30/+31. Judge against 67-87% of the model (lesson 4). Check the input list shows InpVrpMult 0.5 (on) and 0.0 (off compare). NEEDS a VIX symbol on the FTMO tester server (InpVrpVix, default VIX.cash): if the log says the volatility index is not available, the leg never traded; that is a data problem, not a result - report the symbol list and stop.

## Log lines worth a look

- None matched (not found, cannot, failed, margin, invalid, error).
