# j15: AurumHydra target 4x, 21 fresh-deposit months (2024.01-2025.09)

Preset `AurumHydra_target4x_FTMO.set` (InpTarget=4, scale 2.5), XAUUSD M15, deposit 10,000, leverage 1:500, FTMO
symbols, real ticks. Each month is a fresh deposit; the round runs to the 4x goal or to month end. In-sample only:
every month ends before 2025-10-13 (holdout respected).

## Result

Counted from the month multiples in `months_result.json`, not from the `round` field (see the correction below).

| Measure | Value |
|---|---|
| Months at 4.00x or more | 3 of 21 (14%): 2024.03 (4.002), 2024.09 (4.00), 2025.09 (4.00) |
| Month at 3.99x, just short of 4x | 1 of 21: 2024.12 (3.992) |
| Months at 3x or more | 6 of 21 (29%): the three above, 2024.12 (3.99), 2025.01 (3.42), 2025.03 (3.68) |
| Months at 5x or more | 0 of 21 |
| P(ruin) | 0% (no month wiped out; lowest month 0.35x) |
| Median multiple | 1.10x |
| Months below 0.5x | 6 of 21 (29%): 2024.02, 2024.05, 2024.06, 2024.08, 2024.11, 2025.04 |
| Months with margin refusals | 0 |
| Largest month equity drawdown | 82.4% (2024.08), 82.3% (2024.05), 75.3% (2024.06) |

Multiples by month: 2024.01 0.58x, 02 0.48x, 03 4.00x, 04 1.76x, 05 0.36x, 06 0.48x, 07 1.10x, 08 0.35x, 09 4.00x,
10 0.61x, 11 0.47x, 12 3.99x; 2025.01 3.42x, 02 1.63x, 03 3.68x, 04 0.48x, 05 1.50x, 06 0.58x, 07 0.64x, 08 1.54x,
09 4.00x.

## Against the expectation

- `expect` gave P(4x) 22% at edge 0.7 and 32% at edge 1.0 (tools/target_odds.py, 4x target, scale 2.5). The tester gives
  14% at 4.00x or more (19% if the 3.99x month of 2024.12 is counted). That is below the model's range; reported, not
  tuned.
- `expect` gave P(ruin) 17% / 12%; the tester gives 0%, the same narrow ruin tail as j10b and j11b.
- Against j10b (5x target, same months): 2 of 21 at 5x, 3 of 21 at 4x+ by the multiples. Against j11b (3x target):
  3 of 21 at 3x+ by the multiples (see the correction).

## Correction to j11b (found while counting this run)

`tools/months_summary.py` takes its p_3x and p_5x from the `round` field, which is the target the round was opened
with, not whether the month reached it. j15's `months_result.json` reports p_3x 43% (9 months) and p_5x 9.5% (2
months), but no month reached 5x and 6 reached 3x. j11b's file has the same bug: p_3x 0.43 (9 months), while only 3
of its 21 months have a multiple of 3.0 or more (2024.x and 2025.x rows at 3.0, 3.0 and 3.004).

So j11b's judgement ("9 of 21 at 3x, pass") is wrong: the tester's 3x share is 3 of 21 (14%), against target_odds
32-43% at edge 0.7-1.0. j10b's 3x share (6 of 21 by multiples) and 5x share (2 of 21) are correct, because its
multiples were counted from the months. The j11b figure is reported here and not tuned; the orchestrator should
re-judge j11b on 3 of 21. The fix is in `tools/months_summary.py` (count `multiple >= level`), which agents cannot edit.

## Judgement (tester, 2026-10-18)

- Counted from the multiples, the 4x goal is reached in 3 months (14%), with a 4th at 3.99x. This is below the
  target_odds range (22-32%) and well above the tester's 0 ruin, as in j10b and j11b.
- Median 1.10x and 6 months below 0.5x: the tester's months are again narrower in ruin and lower in the middle than
  the model's, the same pattern as j10b.
- Nothing tuned. The result is recorded for the orchestrator to judge.

## Files

Per-month results: `months.json`, `months_result.json` in this folder. Source: `months_result.json`.
