# j11b: AurumHydra target 3x, 21 fresh-deposit months (2024.01-2025.09)

Preset `AurumHydra_target3x_FTMO.set` (InpTarget=3), XAUUSD M15, deposit 10,000, leverage 1:500, FTMO symbols, real
ticks. Each month is a fresh deposit; the round runs to the 3x target or to month end. In-sample only: every month ends
before 2025-10-13 (holdout respected). Same months as j10b, for comparison.

## Result

| Measure | Value |
|---|---|
| Months at 3x (multiple 2.99 or more) | 9 of 21 (43%): 2024.03, 04, 07, 09, 12; 2025.01, 02, 03, 09 |
| Months at 4x or more by multiple | 0 of 21 |
| Months at 5x by multiple | 0 of 21 (the script's `p_5x` = 2 counts 2024.12 and 2025.09, see below) |
| P(ruin) | 0% |
| Median multiple | 1.82x (1.818) |
| Months below 0.5x | 4 of 21 (19%): 2024.02 (0.49), 2024.05 (0.34), 2024.08 (0.27), 2024.11 (0.49) |
| Months with margin refusals | 0 |
| Largest month equity drawdown | 86.8% (2024.08), 82.2% (2024.05), 72.4% (2024.02) |

Multiples by month: 2024.01 0.59x, 02 0.49x, 03 3.00x, 04 3.00x, 05 0.34x, 06 0.63x, 07 3.00x, 08 0.27x, 09 3.00x,
10 0.57x, 11 0.49x, 12 3.00x; 2025.01 3.00x, 02 3.00x, 03 3.00x, 04 0.55x, 05 1.98x, 06 0.57x, 07 0.84x, 08 1.82x,
09 3.00x.

## Against the expectation

- `expect`: the same months as j10b, reported as P(3x/4x/5x), P(ruin), median, refusals and the gold losses.
- The 3x share is 43% (9 of 21). The Python yardstick (`tools/target_odds.py`, 3x target, every weekday a round) gives
  32% at edge 0.7 and 43% at edge 1.0, with P(ruin) 16% / 12%. The tester is inside the range at edge 1.0 and shows 0%
  ruin.
- Against j10b on the same months: 3x share 29% (6) in j10b, 43% (9) here; j10b's 5x months (2024.12, 2025.09) both
  ended at 3.00x in this run.
- Gold, whole-month `by_symbol`: not summarised here; each month's `result.json` holds it.

## Count of 5x: script versus multiples

`months_result.json` gives `p_5x` 0.095 (2 months) and `share_goal_reached` 2 of 21, from the rounds whose `round`
field is 5.0 (2024.12, 2025.09). Both months' `multiple` values are 3.004 and 2.999. No month in this series reached a
multiple of 5. Read the 5x count as 0 of 21 until the script's `round` field is explained. Nothing is tuned from it.
Flagged to the orchestrator in the decision line.

## Judgement (tester, 2026-10-18)

- Measured on the same 21 months, the 3x target gives 9 of 21 at 3x (43%), which is at the model's edge 1.0 value,
  and no ruin. The j10b 5x run gave 2 of 21 at 5x against the model's 5-9. Both are the tester's own months.
- The 5x count in this file is not a 5x result; the multiples show 0 at 5x.
- Nothing tuned on these months.

## Judgement (orchestrator, 2026-10-18)

Step 16, `research/hydra_t3b_months_model.py`: the j10b same-months model (`research/hydra_t5b_months_model.py`) at
goal 3x on these 21 months. A month counts as at a level from 0.3% below it, because the tester's multiple is the final
balance after the last fill (2.999x).

| Source | Months at 3x | P(4x) | P(ruin) | Median |
|---|---|---|---|---|
| Model, odds settings, edge 1.0 | 10 of 21 (48%) | 0 | 14% (3) | 2.97x |
| Model, odds settings, edge 0.7 | 9 of 21 (43%) | 0 | 24% (5) | 1.71x |
| Model, preset settings, edge 1.0 and 0.7 | 12 of 21 (57%) | 0 | 43% (9) | 3.00x |
| Tester | 9 of 21 (43%) | 0 | 0% | 1.82x |
| `target_odds.py`, every weekday a round, scale 2.5 | 32% (0.7) to 43% (1.0) | | 16% / 12% | |
| Month-start rounds from 2010, odds settings | 28% (0.7) to 41% (1.0) | | | |

- **Pass on the goal measure.** 9 of 21 at 3x is inside every yardstick: the same-months model (9-12), `target_odds`
  (32-43%) and the month-start base rate (28-41%).
- Month by month, odds model at edge 1.0 against the tester: both reach 3x in 7 months (2024.03, 09, 12; 2025.01,
  02, 03, 09). Only the model: 2024.01, 2024.10, 2025.08. Only the tester: 2024.04, 2024.07. The preset model shares
  8 months; model only: 2024.01, 2024.10, 2025.07, 2025.08; tester only: 2025.02. Log correlation 0.29 / 0.35 (odds),
  0.58 / 0.60 (preset).
- **The ruin tail is narrower than the model's, as in j10b.** The model ruins 3-9 of 21 months (at 0.2x); the tester
  ruins none (lowest 0.27x, 2024.08, with an 86.8% equity drawdown). "Tester keeps X of model log growth" does not
  mean anything here: the model's ruins (clipped at 0.01x) take its log sum to 1.25 / -4.09 / -12.74 / -18.07, against
  the tester's 4.46. The cause is still not measured.
- 2024.10 (tester 0.57x, model 3.00x) and 2025.07 (tester 0.84x, preset model 3.00x) are again the largest misses, as
  in j10b. A daily-equity comparison of those two months is the open fidelity item (no tester time needed).
- **The script's 5x count is log pollution.** The tester's `summary.txt` for a day holds the lines of every run that
  day. `tools/months_summary.py` takes the first "goal round of <month> ended" line. For 2024.12 and 2025.09 that is
  j10b's 5.00x line from 04:33 and 05:04. j11b's own lines (06:37, 07:16) say 3.00x, goal 3.0x. True count at 5x: 0.
  `months_result.json`'s `goal` 5.0 is the script's default; `months.json` carries no goal. The tool fix is described
  in HANDOFF.
- For the mission: on these months, InpTarget=3 reaches 3x in 43% of rounds with no ruin. InpTarget=5 (j10b) reaches 5x
  in 10%. Nothing tuned on these months.

## Files

Per-month `result.json` and `tester.ini` are in each `..._t3b_2024MM` folder; `months.json` and `months_result.json`
in this folder. Source: `months_result.json`.
