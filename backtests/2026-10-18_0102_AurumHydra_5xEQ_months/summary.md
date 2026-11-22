# Equivalence check: shared leg library (v1.34) against v1.33

Preset AurumHydra_5x_month_FTMO.set, Terminal 16, FTMO-Demo data, run 2026-10-18 01:02-01:20, before the tester moved to its own install.

| month | v1.34 multiple | trades | eq DD | v1.33 (j8b/j8c) |
|---|---|---|---|---|
| 2026.01 | 5.00x | 46 | 16.83% | 5.00x |
| 2026.02 | 1.33x | 52 | 23.85% | 1.33x, 52 trades, 23.85% |
| 2026.03 | 0.91x | 46 | 42.95% | 0.91x, 46 trades, 42.95% |

Identical: the refactor into Include/Aurum changed no trade. These months are in the holdout (after 2025.09); they were run before it existed and only to compare code versions.
