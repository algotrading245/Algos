# j18: AurumFunded dual1 on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-10-28 13:27: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_dual.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set none, compare_set ['InpDualMult=0.25'].

## legs off (`2026-10-28_1213_AurumFunded_dual1_off`)

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

## legs on (`2026-10-28_1245_AurumFunded_dual1_on`)

| Measure | Value |
|---|---|
| Net profit | +15,182.14 (+151.8%) |
| Trades / win rate | 3046.0 / 53.74% |
| Profit factor | 1.6 |
| Max equity drawdown | 7.59% |
| Worst day | 2024-07-25 -2.5% |
| Return per unit of drawdown | 20.0 |
| By year | 2024 +5,213, 2025 +9,970 |
| History quality | 99% real ticks |

## On against off

Return per unit of equity drawdown: off 32.2, on 20.0 (not higher with the legs on).

## Expected (from the job)

Step 15 for AurumFunded v1.18 (Dual Thrust index leg, magics +32 S&P 500 / +33 Nasdaq / +34 GER40.cash / +35 JP225.cash). Preset = OFF run; compare_set adds InpDualMult=0.25 (ON run). Python (research/prebuilt_dual_thrust_four_indices_ew.py, four indices equal weight at size 1): +12.6% over 2024.01-2025.10 with annual vol 3.8% and max DD 2.3%; the preset runs it at SizeMult 0.5, so about +6% and 1.2% DD on 10k, i.e. about +600 USD, 67-87% of that in the tester (lesson 4). Rule: 4-day range, buy at 01:00 open + 0.3 x range, sell at open - 0.7 x range, broker stop at the opposite level (reverses), flat 22:00, several trades a day expected (reversals). Check the log shows the four symbols selected and 'Dual Thrust ... bought/sold' lines; if GER40.cash or JP225.cash is not on the tester server the log says the leg leaves it out (then judge on the two US indices). Differences from the Python: D1 bars of the broker, stop = reversal level, cap of 8 entries per day and index. Lesson 21: the book CloseEverything (day stop etc.) can close trades early; this leg is intraday so the effect is small, but check for off-schedule closes. Do not tune on this window.

## Log lines worth a look

- None matched (not found, cannot, failed, margin, invalid, error).
