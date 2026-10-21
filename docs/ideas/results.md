# Idea specs tested by tools/idea_engine.py

Best variant picked on the days before 2018; Sharpe at the real cost before 2018 / from 2018 to the holdout. Verdicts are tools/gates.py's.

| when | id | read | variants | best | Sharpe | verdict | DSR or note |
|---|---|---|---|---|---|---|---|
| 2026-10-21T17:10 | china_activity_aud | n/a | 12 | AUDUSD event+2 L8 long | 0.50 / -0.68 | FAIL at halves | 0.000 (N=26572, luck bar 6.17) |
| 2026-10-21T20:21 | ma_cross_fx_majors_1_5 | in full | 6 | USDJPY ma_cross fast=1 slow=5 L1 both | 0.30 / -0.15 | FAIL at halves | 0.000 (N=26578, luck bar 1.03) |
| 2026-10-21T20:21 | ma_cross_fx_majors_20_200 | in full | 6 | USDJPY ma_cross fast=20 slow=200 L1 both | 0.18 / -0.33 | FAIL at halves | 0.000 (N=26584, luck bar 1.03) |
| 2026-10-21T20:21 | ma_cross_fx_majors_5_20 | in full | 6 | USDJPY ma_cross fast=5 slow=20 L1 both | -0.25 / 0.44 | FAIL at halves | 0.000 (N=26590, luck bar 1.03) |
| 2026-10-21T20:21 | ma_cross_nzdusd_5_20 | in full | 1 | NZDUSD ma_cross fast=5 slow=20 L1 both | -0.49 / -0.10 | FAIL at halves | 0.000 (N=26591, luck bar 1.03) |
| 2026-10-21T21:51 | tsmom_hurst_fx | in full | 21 | USDJPY tsmom lookback=252 L21 both | 0.46 / 0.09 | FAIL at halves | 0.002 (N=26612, luck bar 1.03) |
| 2026-10-21T21:51 | tsmom_hurst_gold | in full | 3 | XAUUSD tsmom lookback=252 L21 both | 0.15 / 0.53 | FAIL at halves | 0.003 (N=26615, luck bar 1.03) |
