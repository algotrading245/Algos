# j10b: AurumHydra target 5x, 21 fresh-deposit months (2024.01-2025.09)

Preset `AurumHydra_target5x_FTMO.set` (InpTarget=5, scale 2.5), XAUUSD M15, deposit 10,000, leverage 1:500, FTMO
symbols, real ticks. Each month is a fresh deposit; the round runs to the 5x goal or to month end. In-sample only:
every month ends before 2025-10-13 (holdout respected).

## Result

| Measure | Value |
|---|---|
| Months at 5x (held to month end) | 2 of 21 (9.5%): 2024.12, 2025.09 |
| P(3x) / P(4x) / P(5x) | 29% (6) / 14% (3) / 10% (2) |
| P(ruin) | 0% |
| Median multiple | 1.07x (1.065) |
| Months below 0.5x | 5 of 21 (24%): 2024.02, 2024.05, 2024.08, 2024.11, 2025.04 |
| Months with margin refusals | 0 |
| Largest month equity drawdown | 82.3% (2024.05), 82.2% (2024.08), 77.8% (2025.07) |

Multiples by month: 2024.01 0.61x, 02 0.45x, 03 4.42x, 04 1.78x, 05 0.37x, 06 0.51x, 07 1.07x, 08 0.36x, 09 3.42x,
10 0.63x, 11 0.45x, 12 5.00x; 2025.01 3.34x, 02 1.67x, 03 3.89x, 04 0.47x, 05 1.36x, 06 0.57x, 07 0.65x, 08 1.44x,
09 5.00x.

## Against the expectation

- `expect` gave about 40% of rounds at 5x (target_odds.py, Python model). The tester gives 9.5% (2 of 21). The gap is
  large and not explained here; reported, not tuned.
- Earlier tester result for the same EA family: j8 1 of 21 (EA 1.33, 2025.01-2026.09). j10b is 2 of 21 on the
  same kind of series with the target-5x preset; the two windows differ (j10b 2024.01-2025.09, j8 2025.01-2026.09).
- Gold (XAUUSD, whole-month `by_symbol` from each month's result.json): negative in 13 of 21 months. Largest losses:
  2024.07 -8,950, 2024.12 -11,017 (month still reached 5.0x; `by_symbol` covers the whole run, so the goal round's
  end is not separated out), 2025.07 -12,323, 2025.05 -9,414, 2024.01 -7,724, 2025.04 -7,245. Gold made the largest
  gains in 2025.09 (+40,717), 2024.03 (+33,575), 2025.03 (+27,288), 2024.09 (+24,544).
- Non-gold symbols were not summarised per month here; each month's `result.json` holds them.

## Files

Per-month `result.json` and `tester.ini` are in each `..._t5b_2024MM` folder; `months.json` and `months_result.json`
in this folder. Source: `months_result.json`.
