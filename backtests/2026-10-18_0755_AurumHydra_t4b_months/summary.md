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

## Judgement (orchestrator, 2026-10-18)

Step 16, `research/hydra_t4b_months_model.py`: the j10b same-months model (`research/hydra_t5b_months_model.py`) at
goal 4x on these 21 months. A month counts as at a level from 0.3% below it, as in j11b's judgement. The tester's
multiple is the final balance after the last fill. 2024.12's own log line says the round stopped at the goal:
`backtests/2026-10-18_0847_AurumHydra_t4b_202412/summary.txt` line 699411, "goal round of 2024.12.01 ended, equity
40004.42 from 10000.00 (4.00x, goal 4.0x)".

| Source | Months at 4x | P(3x) | P(ruin) | Median |
|---|---|---|---|---|
| Model, odds settings, edge 1.0 | 9 of 21 (43%) | 43% | 14% (3) | 2.52x |
| Model, odds settings, edge 0.7 | 8 of 21 (38%) | 43% | 24% (5) | 1.68x |
| Model, preset settings, edge 1.0 / 0.7 | 12 / 11 of 21 (57% / 52%) | 57% / 52% | 43% / 48% | 4.00x |
| Tester | 4 of 21 (19%) | 29% (6) | 0% | 1.10x |
| `target_odds.py`, every weekday a round, scale 2.5 | 22% (0.7) to 32% (1.0) | | 17% / 12% | 1.11x / 1.77x |
| Month-start rounds from 2010 (184), odds settings | 17% (0.7) to 25% (1.0) | 22% / 32% | 18% / 13% | 1.00x / 1.69x |

- **Inside the base rate, below the same-months model.** 4 of 21 at 4x is inside the month-start base rate (17-25%)
  and just under `target_odds` (22-32%). The same-months model gives 8-9 (odds) and 11-12 (preset), so these 21
  months favoured the model, and the tester falls short of it on its own months. j10b showed the same pattern at 5x
  (2 against 5-9).
- Month by month, odds model at edge 1.0 against the tester: the tester's 4 months (2024.03, 09, 12; 2025.09) are
  all model months as well, so no month reaches 4x in the tester alone. Model only: 2024.10 (tester 0.61x), 2025.01
  (3.42x), 2025.02 (1.63x), 2025.03 (3.68x), 2025.08 (1.54x). 2024.10 is again the largest miss, as in j10b and j11b.
  Log correlation 0.53 / 0.56 (odds), 0.62 / 0.49 (preset).
- **Ruin tail narrower than the model's, the third time.** The model ruins 3-10 of 21 months; the tester ruins none
  (lowest 0.35x, 2024.08, 82% equity drawdown). The cause is still not measured.
- **Across the same 21 months, by the goal.** InpTarget=3 reaches 3x in 9 of 21 (43%, j11b). InpTarget=4 reaches 4x in
  4 (19%, j15). InpTarget=5 reaches 5x in 2 (10%, j10b). All three have 0 ruin. At 3x the tester matches the
  same-months model (9 against 9-10 odds). At 4x and 5x it falls short of it, by more as the goal grows. A hypothesis
  only: the EA's day sizing is gentler than the model's at the larger goal sizes. Not measured, and nothing is
  tuned on these months.
- **The tester's "Correction to j11b" above is wrong, and j11b is not re-judged.** j11b's months at 2.999x and 3.0x
  stopped at the goal. Their own log lines say 3.00x, for example
  `backtests/2026-10-18_0643_AurumHydra_t3b_202502/summary.txt` line 351145, "goal round of 2025.02.01 ended, equity
  30003.86 from 10000.00 (3.00x, goal 3.0x)". j11b's multiples (`months_result.json`) are 2.999-3.004 in 9 months,
  so 9 of 21 stands. A strict `multiple >= 3.0` drops the 2.999x months; the right count takes 0.3% below the
  level, or the month's own "ended" line. The tester is right on one point: the script's `round` field and its
  p_3x/p_5x must not be used (this file's p_3x 43% and p_5x 9.5% are wrong; the true 3x count is 6 and the 5x count 0).

## Files

Per-month results: `months.json`, `months_result.json` in this folder. Source: `months_result.json`.
