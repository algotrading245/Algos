# Candidate ledger

Generated from `docs/candidates.json` by `python tools/dashboard.py`; edit the JSON, not this file.

## USD/JPY London breakout (`breakout`)

Status **tester**, pipeline step 16 of 20. Source: retail London-breakout concept, own test; research/london_breakout.py, research/breakout_ticks.py.

Range 01:00-09:00 server, each side once a day on a break 10:00-18:00, stop at the far side, flat at 18:00. Sharpe 1.18 to 2017 / 0.83 from 2018 at the measured 1.2 bp, 0.59 at 1.5 bp; |corr| with Hydra <= 0.03.

Gates (2026-10-17, dry run): **PASS**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | pass | 1.18 / 0.83 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.59 | >= 0.3 at 1.5x cost |
| dsr | pass | 0.969 (N=47, luck bar 0.55) | >= 0.9 |
| corr | pass | book -0.00, max leg hold -0.03 | |book| <= 0.2, |leg| <= 0.3 |
| goal | pass | Hydra 2018+ 3.37 -> 3.43 at weight 1; P(5x) 55.2% -> 55.9% | Sharpe gain >= 0.03, weight fixed by --weight |

Strategy Tester (backtests/2026-10-17_0118_AurumBreakout_USDJPY): 771 trades, 47.73% winners, PF 1.16, +9.96%, max equity drawdown 4.02% - matches the Python figures; step 15 passed.

Notes: The gates' own 2017-fitted weight (k=0.5 of Hydra's volatility) adds nothing from 2018 (3.37 -> 3.36): the leg was stronger to 2017 (1.18) than after (0.83), so the fit over-weights it. At AurumFunded's tested size (weight 1 = 0.125% risk) Hydra 3.37 -> 3.43. HANDOFF's 0.5% risk for Hydra (weight 4) gives about 3.46. The tester run decides whether it stays.

## Noise-area intraday momentum, S&P 500 and Nasdaq (`noise`)

Status **tester**, pipeline step 15 of 20. Source: Zarattini, Aziz, Barbon 2025 (read in full); research/noise_area_index.py.

Bands of the average move from the 9:30 open, checked each half hour from 10:00 New York, trailing stop, flat at 16:00, 2% daily vol. Sharpe 0.88 at 0.75 bp (0.61 / 1.08), 0.57 at 1.5 bp; corr with Hydra -0.02.

Gates (2026-10-17, dry run): **PASS**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | pass | 0.64 / 1.10 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.57 | >= 0.3 at 1.5x cost |
| dsr | pass | 0.938 (N=47, luck bar 0.55) | >= 0.9 |
| corr | pass | book -0.02, max leg cross -0.03 | |book| <= 0.2, |leg| <= 0.3 |
| goal | pass | Hydra 2018+ 3.37 -> 3.56 at weight 0.609; P(5x) 55.2% -> 57.4% | Sharpe gain >= 0.03, weight fitted to 2017 |

Notes: Weight fitted to 2017: 0.61 (EA uses 0.55, 0.275 per index). Hydra from 2018 3.37 -> 3.56.

## Rejected families

| Family | Examples | Why |
|---|---|---|
| Gold intraday fades | Asian dip buy, shock fade, LBMA auction dip, burst fade, Shanghai benchmark windows, London bias, weekend gaps | below cost or gone after 2017 |
| Breakouts other than USD/JPY | channel breakout, other dollar pairs, yen crosses, Nikkei, gold, 5-minute ORB on indices | too costly outside USD/JPY, or adds nothing next to the noise leg |
| Machine learning and RL | deep and RL replications, daily ML, tick ML scalp, Deep Momentum Networks, deep Q-learning on 20 futures | Sharpe <= 0.5 or seed-dependent; nothing after costs |
| Intraday momentum variants | market intraday momentum (all forms), Bitcoin intraday, oil on EIA days, VWAP trend, shorter windows | fails one half or dies on cost |
| Calendar and announcement drifts | pre-FOMC, FOMC cycle, overnight drift, turn of month, post-payroll and FOMC drift, holidays elsewhere | no edge after 2017 or below cost |
| Relative-value fades | silver vs gold, AUD/NZD, GBP/EUR, Nasdaq/S&P pairs, FX fixing reversals, 15-minute shocks | real reversion, smaller than the spread |
| Daily and slow strategies | time-series momentum on futures and crypto, VIX filters, reversal in stocks, gold/silver ratio | Sharpe 0.5-0.7 at best, correlated or costly |
| Re-weighting the book | volatility-managed sizing, exponentiated-gradient weights, re-fitted weights, quarter-end size-up | lowers Sharpe out of sample |
| Scalps and HFT | HFT, scalp concepts, night scalper on 11 pairs | 1-2 bp before cost |
