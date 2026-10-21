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
| 2026-10-22T00:44 | f_tsmom_audcad | n/a | 3 | AUDCAD tsmom lookback=20 L1 both | -0.07 / -0.58 | FAIL at halves | 0.000 (N=26618, luck bar 1.03) |
| 2026-10-22T00:44 | f_tsmom_audusd | n/a | 3 | AUDUSD tsmom lookback=20 L1 both | -0.13 / -0.27 | FAIL at halves | 0.000 (N=26621, luck bar 1.03) |
| 2026-10-22T00:44 | f_tsmom_eurusd | n/a | 3 | EURUSD tsmom lookback=60 L1 both | 0.07 / -0.14 | FAIL at halves | 0.000 (N=26624, luck bar 1.03) |
| 2026-10-22T00:44 | f_tsmom_gbpusd | n/a | 3 | GBPUSD tsmom lookback=120 L1 both | -0.04 / -0.50 | FAIL at halves | 0.000 (N=26627, luck bar 1.03) |
| 2026-10-22T00:44 | f_tsmom_spxusd | n/a | 3 | SPXUSD tsmom lookback=120 L1 both | 0.38 / -0.08 | FAIL at halves | 0.000 (N=26630, luck bar 1.03) |
| 2026-10-22T00:44 | f_tsmom_usdcad | n/a | 3 | USDCAD tsmom lookback=120 L1 both | -0.33 / -0.58 | FAIL at halves | 0.000 (N=26633, luck bar 1.03) |
| 2026-10-22T00:45 | f_tsmom_usdchf | n/a | 3 | USDCHF tsmom lookback=60 L1 both | -0.25 / -0.54 | FAIL at halves | 0.000 (N=26636, luck bar 1.03) |
| 2026-10-22T00:45 | f_tsmom_usdjpy | n/a | 3 | USDJPY tsmom lookback=60 L1 both | 0.49 / 0.34 | FAIL at halves | 0.013 (N=26639, luck bar 1.03) |
| 2026-10-22T00:45 | f_tsmom_xagusd | n/a | 3 | XAGUSD tsmom lookback=20 L1 both | 0.51 / -0.04 | FAIL at halves | 0.003 (N=26642, luck bar 1.03) |
| 2026-10-22T00:45 | f_tsmom_xauusd | n/a | 3 | XAUUSD tsmom lookback=120 L1 both | 0.13 / 0.61 | FAIL at halves | 0.003 (N=26645, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_audjpy | n/a | 3 | AUDJPY tsmom lookback=120 L1 both | -0.23 / -0.18 | FAIL at halves | 0.000 (N=26648, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_audnzd | n/a | 3 | AUDNZD tsmom lookback=60 L1 both | 0.05 / -0.43 | FAIL at halves | 0.000 (N=26651, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_cadjpy | n/a | 3 | CADJPY tsmom lookback=60 L1 both | -0.06 / -0.10 | FAIL at halves | 0.000 (N=26654, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_euraud | n/a | 3 | EURAUD tsmom lookback=120 L1 both | 0.02 / -0.22 | FAIL at halves | 0.000 (N=26657, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_eurchf | n/a | 3 | EURCHF tsmom lookback=120 L1 both | 0.13 / -0.52 | FAIL at halves | 0.000 (N=26660, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_eurgbp | n/a | 3 | EURGBP tsmom lookback=120 L1 both | 0.26 / -0.78 | FAIL at halves | 0.000 (N=26663, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_eurjpy | n/a | 3 | EURJPY tsmom lookback=60 L1 both | 0.52 / -0.25 | FAIL at halves | 0.000 (N=26666, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_gbpchf | n/a | 3 | GBPCHF tsmom lookback=120 L1 both | -0.35 / -0.37 | FAIL at halves | 0.000 (N=26669, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_gbpjpy | n/a | 3 | GBPJPY tsmom lookback=120 L1 both | 0.30 / -0.49 | FAIL at halves | 0.000 (N=26672, luck bar 1.03) |
| 2026-10-22T00:47 | f_tsmom_nzdusd | n/a | 3 | NZDUSD tsmom lookback=60 L1 both | -0.18 / -0.47 | FAIL at halves | 0.000 (N=26675, luck bar 1.03) |
| 2026-10-22T00:47 | xsmom_fx_majors_12m | in full | 1 | EURUSD+GBPUSD+USDJPY+AUDUSD+USDCAD+USDCHF+NZDUSD xsmom lookback=252 top=1 L21 both | -0.28 / -0.46 | FAIL at halves | 0.000 (N=26676, luck bar 1.03) |
| 2026-10-22T00:48 | xsmom_xau_xag_wti_spx_12m | in full | 1 | XAUUSD+XAGUSD+WTIUSD+SPXUSD xsmom lookback=252 top=1 L21 both | 0.15 / 0.20 | FAIL at halves | 0.000 (N=26677, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_audcad | n/a | 2 | AUDCAD donchian lookback=20 L1 both | 0.02 / -0.31 | FAIL at halves | 0.000 (N=26680, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_eurusd | n/a | 2 | EURUSD donchian lookback=20 L1 both | 0.07 / -0.25 | FAIL at halves | 0.000 (N=26682, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_gbpusd | n/a | 2 | GBPUSD donchian lookback=55 L1 both | -0.20 / 0.21 | FAIL at halves | 0.000 (N=26684, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_spxusd | n/a | 2 | SPXUSD donchian lookback=55 L1 both | -0.08 / 0.19 | FAIL at halves | 0.000 (N=26686, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_usdjpy | n/a | 2 | USDJPY donchian lookback=55 L1 both | 0.31 / 0.48 | FAIL at halves | 0.016 (N=26688, luck bar 1.03) |
| 2026-10-22T00:51 | f_donchian_xauusd | n/a | 2 | XAUUSD donchian lookback=20 L1 both | 0.09 / 0.03 | FAIL at halves | 0.000 (N=26690, luck bar 1.03) |
| 2026-10-22T00:51 | f_tsmom_grxeur | n/a | 3 | GRXEUR tsmom lookback=120 L1 both | -0.05 / 0.50 | FAIL at halves | 0.000 (N=26693, luck bar 1.03) |
| 2026-10-22T00:51 | f_tsmom_jpxjpy | n/a | 3 | JPXJPY tsmom lookback=120 L1 both | 0.40 / -0.54 | FAIL at halves | 0.000 (N=26696, luck bar 1.03) |
| 2026-10-22T00:51 | f_tsmom_nzdcad | n/a | 3 | NZDCAD tsmom lookback=60 L1 both | -0.05 / -0.94 | FAIL at halves | 0.000 (N=26699, luck bar 1.03) |
| 2026-10-22T00:51 | f_tsmom_wtiusd | n/a | 3 | WTIUSD tsmom lookback=60 L1 both | 0.33 / -0.15 | FAIL at halves | 0.000 (N=26702, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_audjpy | n/a | 2 | AUDJPY donchian lookback=55 L1 both | -0.32 / -0.17 | FAIL at halves | 0.000 (N=26704, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_audusd | n/a | 2 | AUDUSD donchian lookback=20 L1 both | -0.12 / -0.15 | FAIL at halves | 0.000 (N=26706, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_cadjpy | n/a | 2 | CADJPY donchian lookback=55 L1 both | -0.20 / -0.24 | FAIL at halves | 0.000 (N=26708, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_eurgbp | n/a | 2 | EURGBP donchian lookback=55 L1 both | -0.47 / -0.64 | FAIL at halves | 0.000 (N=26710, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_eurjpy | n/a | 2 | EURJPY donchian lookback=55 L1 both | 0.40 / -0.39 | FAIL at halves | 0.000 (N=26712, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_gbpjpy | n/a | 2 | GBPJPY donchian lookback=55 L1 both | 0.09 / -0.42 | FAIL at halves | 0.000 (N=26714, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_nzdusd | n/a | 2 | NZDUSD donchian lookback=20 L1 both | -0.21 / -0.26 | FAIL at halves | 0.000 (N=26716, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_usdcad | n/a | 2 | USDCAD donchian lookback=55 L1 both | -0.55 / -0.51 | FAIL at halves | 0.000 (N=26718, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_usdchf | n/a | 2 | USDCHF donchian lookback=55 L1 both | -0.09 / -0.44 | FAIL at halves | 0.000 (N=26720, luck bar 1.03) |
| 2026-10-22T00:54 | f_donchian_xagusd | n/a | 2 | XAGUSD donchian lookback=20 L1 both | 0.28 / -0.47 | FAIL at halves | 0.000 (N=26722, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_audnzd | n/a | 2 | AUDNZD donchian lookback=55 L1 both | 0.03 / -0.84 | FAIL at halves | 0.000 (N=26724, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_euraud | n/a | 2 | EURAUD donchian lookback=20 L1 both | -0.10 / -0.15 | FAIL at halves | 0.000 (N=26726, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_eurchf | n/a | 2 | EURCHF donchian lookback=55 L1 both | 0.14 / -0.57 | FAIL at halves | 0.000 (N=26728, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_gbpchf | n/a | 2 | GBPCHF donchian lookback=20 L1 both | -0.54 / -0.57 | FAIL at halves | 0.000 (N=26730, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_grxeur | n/a | 2 | GRXEUR donchian lookback=20 L1 both | -0.06 / -0.07 | FAIL at halves | 0.000 (N=26732, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_jpxjpy | n/a | 2 | JPXJPY donchian lookback=20 L1 both | 0.11 / -0.35 | FAIL at halves | 0.000 (N=26734, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_nzdcad | n/a | 2 | NZDCAD donchian lookback=20 L1 both | 0.03 / -0.56 | FAIL at halves | 0.000 (N=26736, luck bar 1.03) |
| 2026-10-22T00:57 | f_donchian_wtiusd | n/a | 2 | WTIUSD donchian lookback=55 L1 both | 0.11 / -0.02 | FAIL at halves | 0.000 (N=26738, luck bar 1.03) |
| 2026-10-22T00:57 | f_ma_cross_usdjpy | n/a | 4 | USDJPY ma_cross fast=20 slow=100 L1 both | 0.04 / 0.01 | FAIL at halves | 0.000 (N=26742, luck bar 1.03) |
| 2026-10-22T00:57 | f_ma_cross_xauusd | n/a | 4 | XAUUSD ma_cross fast=20 slow=50 L1 both | 0.20 / 0.23 | FAIL at halves | 0.000 (N=26746, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_audcad | n/a | 4 | AUDCAD ma_cross fast=10 slow=50 L1 both | -0.25 / -0.24 | FAIL at halves | 0.000 (N=26750, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_audusd | n/a | 4 | AUDUSD ma_cross fast=20 slow=50 L1 both | 0.17 / -0.80 | FAIL at halves | 0.000 (N=26754, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_eurjpy | n/a | 4 | EURJPY ma_cross fast=10 slow=100 L1 both | 0.44 / -0.37 | FAIL at halves | 0.000 (N=26758, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_eurusd | n/a | 4 | EURUSD ma_cross fast=10 slow=50 L1 both | 0.15 / -0.03 | FAIL at halves | 0.000 (N=26762, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_gbpusd | n/a | 4 | GBPUSD ma_cross fast=10 slow=100 L1 both | 0.04 / 0.09 | FAIL at halves | 0.000 (N=26766, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_nzdusd | n/a | 4 | NZDUSD ma_cross fast=10 slow=50 L1 both | -0.37 / -0.30 | FAIL at halves | 0.000 (N=26770, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_spxusd | n/a | 4 | SPXUSD ma_cross fast=20 slow=100 L1 both | -0.06 / -0.02 | FAIL at halves | 0.000 (N=26774, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_usdcad | n/a | 4 | USDCAD ma_cross fast=20 slow=50 L1 both | -0.08 / -0.52 | FAIL at halves | 0.000 (N=26778, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_usdchf | n/a | 4 | USDCHF ma_cross fast=20 slow=100 L1 both | -0.28 / -0.34 | FAIL at halves | 0.000 (N=26782, luck bar 1.03) |
| 2026-10-22T01:00 | f_ma_cross_xagusd | n/a | 4 | XAGUSD ma_cross fast=10 slow=50 L1 both | -0.07 / -0.02 | FAIL at halves | 0.000 (N=26786, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_audjpy | n/a | 4 | AUDJPY ma_cross fast=10 slow=100 L1 both | -0.44 / 0.01 | FAIL at halves | 0.000 (N=26790, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_audnzd | n/a | 4 | AUDNZD ma_cross fast=10 slow=100 L1 both | -0.01 / -0.56 | FAIL at halves | 0.000 (N=26794, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_cadjpy | n/a | 4 | CADJPY ma_cross fast=20 slow=100 L1 both | -0.02 / -0.32 | FAIL at halves | 0.000 (N=26798, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_euraud | n/a | 4 | EURAUD ma_cross fast=20 slow=50 L1 both | 0.01 / -0.81 | FAIL at halves | 0.000 (N=26802, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_eurchf | n/a | 4 | EURCHF ma_cross fast=10 slow=50 L1 both | 0.11 / -0.72 | FAIL at halves | 0.000 (N=26806, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_eurgbp | n/a | 4 | EURGBP ma_cross fast=20 slow=50 L1 both | -0.13 / -0.87 | FAIL at halves | 0.000 (N=26810, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_gbpchf | n/a | 4 | GBPCHF ma_cross fast=20 slow=50 L1 both | -0.55 / -0.92 | FAIL at halves | 0.000 (N=26814, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_gbpjpy | n/a | 4 | GBPJPY ma_cross fast=10 slow=100 L1 both | 0.14 / -1.13 | FAIL at halves | 0.000 (N=26818, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_grxeur | n/a | 4 | GRXEUR ma_cross fast=10 slow=100 L1 both | -0.00 / -0.01 | FAIL at halves | 0.000 (N=26822, luck bar 1.03) |
| 2026-10-22T01:03 | f_ma_cross_nzdcad | n/a | 4 | NZDCAD ma_cross fast=10 slow=50 L1 both | 0.24 / -0.19 | FAIL at halves | 0.000 (N=26826, luck bar 1.03) |
| 2026-10-22T01:06 | f_ma_cross_jpxjpy | n/a | 4 | JPXJPY ma_cross fast=20 slow=100 L1 both | -0.13 / -0.48 | FAIL at halves | 0.000 (N=26830, luck bar 1.03) |
| 2026-10-22T01:06 | f_ma_cross_wtiusd | n/a | 4 | WTIUSD ma_cross fast=10 slow=50 L1 both | 0.30 / 0.30 | FAIL at halves | 0.002 (N=26834, luck bar 1.03) |
| 2026-10-22T01:06 | f_meanrev_audcad | n/a | 4 | AUDCAD meanrev lookback=10 z=2.0 L1 both | 0.36 / -0.17 | FAIL at halves | 0.000 (N=26838, luck bar 3.20) |
| 2026-10-22T01:06 | f_meanrev_audusd | n/a | 4 | AUDUSD meanrev lookback=10 z=2.0 L1 both | 0.24 / -0.46 | FAIL at halves | 0.000 (N=26842, luck bar 3.18) |
| 2026-10-22T01:06 | f_meanrev_eurusd | n/a | 4 | EURUSD meanrev lookback=10 z=1.5 L1 both | 0.16 / 0.35 | FAIL at halves | 0.000 (N=26846, luck bar 1.68) |
| 2026-10-22T01:06 | f_meanrev_gbpusd | n/a | 4 | GBPUSD meanrev lookback=10 z=1.5 L1 both | 0.26 / 0.56 | FAIL at halves | 0.007 (N=26850, luck bar 1.67) |
| 2026-10-22T01:06 | f_meanrev_spxusd | n/a | 4 | SPXUSD meanrev lookback=10 z=2.0 L1 both | 0.43 / 0.21 | FAIL at halves | 0.002 (N=26854, luck bar 3.24) |
| 2026-10-22T01:06 | f_meanrev_usdjpy | n/a | 4 | USDJPY meanrev lookback=10 z=2.0 L1 both | 0.34 / 0.06 | FAIL at halves | 0.000 (N=26858, luck bar 3.04) |
| 2026-10-22T01:06 | f_meanrev_xagusd | n/a | 4 | XAGUSD meanrev lookback=20 z=2.0 L1 both | -0.34 / -0.28 | FAIL at halves | 0.000 (N=26862, luck bar 2.48) |
| 2026-10-22T01:06 | f_meanrev_xauusd | n/a | 4 | XAUUSD meanrev lookback=20 z=1.5 L1 both | -0.31 / -0.61 | FAIL at halves | 0.000 (N=26866, luck bar 1.68) |
| 2026-10-22T01:09 | f_meanrev_audjpy | n/a | 4 | AUDJPY meanrev lookback=10 z=2.0 L1 both | -0.04 / -0.01 | FAIL at halves | 0.000 (N=26870, luck bar 3.13) |
| 2026-10-22T01:09 | f_meanrev_cadjpy | n/a | 4 | CADJPY meanrev lookback=20 z=1.5 L1 both | 0.08 / -0.04 | FAIL at halves | 0.000 (N=26874, luck bar 1.65) |
| 2026-10-22T01:09 | f_meanrev_euraud | n/a | 4 | EURAUD meanrev lookback=20 z=1.5 L1 both | -0.20 / 0.08 | FAIL at halves | 0.000 (N=26878, luck bar 1.65) |
| 2026-10-22T01:09 | f_meanrev_eurchf | n/a | 4 | EURCHF meanrev lookback=10 z=1.5 L1 both | 0.59 / -0.36 | FAIL at halves | 0.000 (N=26882, luck bar 1.74) |
| 2026-10-22T01:09 | f_meanrev_eurgbp | n/a | 4 | EURGBP meanrev lookback=20 z=1.5 L1 both | 0.06 / 0.30 | FAIL at halves | 0.000 (N=26886, luck bar 1.68) |
| 2026-10-22T01:09 | f_meanrev_eurjpy | n/a | 4 | EURJPY meanrev lookback=20 z=2.0 L1 both | -0.00 / -0.07 | FAIL at halves | 0.000 (N=26890, luck bar 2.52) |
| 2026-10-22T01:09 | f_meanrev_gbpjpy | n/a | 4 | GBPJPY meanrev lookback=10 z=2.0 L1 both | -0.19 / -0.18 | FAIL at halves | 0.000 (N=26894, luck bar 3.10) |
| 2026-10-22T01:09 | f_meanrev_nzdusd | n/a | 4 | NZDUSD meanrev lookback=10 z=1.5 L1 both | 0.47 / -0.07 | FAIL at halves | 0.000 (N=26898, luck bar 1.67) |
| 2026-10-22T01:09 | f_meanrev_usdcad | n/a | 4 | USDCAD meanrev lookback=10 z=1.5 L1 both | 0.25 / 0.14 | FAIL at halves | 0.000 (N=26902, luck bar 1.71) |
| 2026-10-22T01:09 | f_meanrev_usdchf | n/a | 4 | USDCHF meanrev lookback=20 z=2.0 L1 both | 0.49 / -0.14 | FAIL at halves | 0.001 (N=26906, luck bar 2.62) |
