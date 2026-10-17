# Candidate ledger

Generated from `docs/candidates.json` by `python tools/dashboard.py`; edit the JSON, not this file.

## USD/JPY London breakout (`breakout`)

Status **tester**, pipeline step 17 of 20. Source: retail London-breakout concept, own test; research/london_breakout.py, research/breakout_ticks.py.

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

Strategy Tester (backtests/2026-10-17_0535_AurumFunded_funded_on): 3468 trades, 50.09% winners, PF 1.5, +221.48%, max equity drawdown 8.28% - step 16 passed in AurumFunded: legs off +167.68% / 6.67% -> on +221.48% / 8.28%, return per drawdown 25.1 -> 26.7, against an expected +185-190% / 7.5-8%; USDJPY +3,179 -> +4,671. Day stops 17 -> 21 (same two in 2024; the extra ones come at 2.5x+ equity, where the 3%-of-initial stop is ~1.2% of equity). AurumHydra's step 16 is j5 (j4 was a set-up fault)..

Strategy Tester (backtests/2026-10-17_1116_AurumHydra_size1b_on): 4173 trades, 51.4% winners, PF 1.49, +1076.18%, max equity drawdown 15.54% - step 16 passed in AurumHydra: legs off +725.13% / 12.48% -> on +1076.18% / 15.54%, return per drawdown 58.1 -> 69.2 (model 110 -> 136); the tester kept 83% / 87% of the model's log growth. USDJPY +9,695 -> +25,860. Legs on, the deepest stretch is 2026-01 (breakout -1.0, noise -3.9 points); legs off it is 2024-07/08, which the legs offset (research/hydra_j6_compare.py)..

Notes: The gates' own 2017-fitted weight (k=0.5 of Hydra's volatility) adds nothing from 2018 (3.37 -> 3.36): the leg was stronger to 2017 (1.18) than after (0.83), so the fit over-weights it. At AurumFunded's tested size (weight 1 = 0.125% risk) Hydra 3.37 -> 3.43. HANDOFF's 0.5% risk for Hydra (weight 4) gives about 3.46. The tester run decides whether it stays. Step 16 base: j3 legs off (AurumFunded 1.03, backtests/2026-10-17_0505_AurumFunded_funded_off) +167.7%, 6.67% eq DD, 17 day stops - matches the model once the 1.4 cushion cap of 1.01 is counted (research/funded_tester_gap.py). The legs-on run (both candidates) should give about +185-190% and 7.5-8% DD; well under the base's growth would count against the legs. Legs-on run (2026-10-17 07:10): +221.5% / 8.28%, step 16 passed in AurumFunded. j4 (AurumHydra 5x preset) was a set-up fault: 12 of 16 symbol inputs on another broker's names, one goal round at a 100 deposit; j5 reruns Hydra at size 1 from 10,000 on FTMO names (preset AurumHydra_FTMO_size1.set; model legs off +1184% / 10.7%, on +1574% / 11.5%, research/hydra_tester_expect.py). Step 17 (demo with the legs on) needs the owner: a3. j5 (2026-10-17 10:05): no valid pair - the tester kept j4's inputs that the size1 preset left out, so both runs had the legs on plus InpMonthEndBoost=2 and no halt: +1460.44% / 13.11% eq DD both times (return per DD 111, ~97% of the legs-on model's log growth). The preset now pins those inputs at the EA defaults; j6 reruns the pair and decides Hydra's step 16. j6 (2026-10-17 13:10): step 16 passed in AurumHydra too (off +725.1% / 12.48% -> on +1076.2% / 15.54%, return per DD 58.1 -> 69.2), USDJPY 9,695 -> 25,860; the breakout lost about 1 point in 2026-01, the legs-on run's deepest month, and gave +4.1 points in 2024-07, the legs-off run's. Step 16 done in both EAs; step 17 (demo forward test) waits on the owner's a3.

## Noise-area intraday momentum, S&P 500 and Nasdaq (`noise`)

Status **tester**, pipeline step 17 of 20. Source: Zarattini, Aziz, Barbon 2025 (read in full); research/noise_area_index.py.

Bands of the average move from the 9:30 open, checked each half hour from 10:00 New York, trailing stop, flat at 16:00, 2% daily vol. Sharpe 0.88 at 0.75 bp (0.61 / 1.08), 0.57 at 1.5 bp; corr with Hydra -0.02.

Gates (2026-10-17, dry run): **PASS**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | pass | 0.64 / 1.10 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.57 | >= 0.3 at 1.5x cost |
| dsr | pass | 0.938 (N=47, luck bar 0.55) | >= 0.9 |
| corr | pass | book -0.02, max leg cross -0.03 | |book| <= 0.2, |leg| <= 0.3 |
| goal | pass | Hydra 2018+ 3.37 -> 3.56 at weight 0.609; P(5x) 55.2% -> 57.4% | Sharpe gain >= 0.03, weight fitted to 2017 |

Strategy Tester (backtests/2026-10-17_0457_AurumNoise_US500): 452 trades, 39.6% winners, PF 1.0, -0.68%, max equity drawdown 26.09% - matches the Python figures (return 2.0 points under, drawdown 2.5 under, trades 452 vs 451); the S&P half was already weak in 2024-26 in Python and is flat here (2024 +17%, 2025 and 2026 losing).

Strategy Tester (backtests/2026-10-17_0500_AurumNoise_US100): 697 trades, 40.75% winners, PF 1.18, +39.93%, max equity drawdown 16.41% - matches the Python figures (return 4.8 points under, drawdown 2.1 under, trades 697 vs 701; every year positive); step 15 passed for both indices, step 16 = j3 and j4 legs on vs off.

Strategy Tester (backtests/2026-10-17_0535_AurumFunded_funded_on): 3468 trades, 50.09% winners, PF 1.5, +221.48%, max equity drawdown 8.28% - step 16 passed in AurumFunded (see the breakout's entry): return per drawdown 25.1 -> 26.7. The noise leg's own share: US100.cash +976.53, US500.cash -56.81 - the S&P half flat for the second time on 2024-26 data. AurumHydra's step 16 is j5..

Strategy Tester (backtests/2026-10-17_1116_AurumHydra_size1b_on): 4173 trades, 51.4% winners, PF 1.49, +1076.18%, max equity drawdown 15.54% - step 16 passed in AurumHydra (see the breakout's entry): return per drawdown 58.1 -> 69.2. The noise leg's own share (no index trades with the legs off): US100.cash +4,181.31, US500.cash -1,092.30 - the S&P half negative for the third time on 2024-26 data, not refitted..

Notes: Weight fitted to 2017: 0.61 (EA uses 0.55, 0.275 per index). Hydra from 2018 3.37 -> 3.56. Step 16 base: j3 legs off +167.7%, 6.67% eq DD, 17 day stops - matches (see the breakout's note); legs on expected about +185-190%, 7.5-8% DD. Legs-on run: +221.5% / 8.28%, step 16 passed in AurumFunded; US500.cash -57 there, flat again - look at it once Hydra's j5 is in, without refitting weights on the tester window. j4 did not test the noise leg (SP500.r / NAS100.r not found); j5 did, but legs on in both runs (inherited inputs, see the breakout's note): by symbol US100.cash +5,890, US500.cash -1,036 there (all of Hydra's legs on those symbols together, with the month-end boost, so not the noise leg's own share). j6 decides Hydra's step 16. j6 (2026-10-17 13:10): step 16 passed in AurumHydra (return per DD 58.1 -> 69.2, see the breakout's note). The legs-off run has no US100/US500 trades, so the on run's US100.cash +4,181 and US500.cash -1,092 are the noise leg's own share: the S&P half negative for the third time, but on the same 2024-26 window that Python already had flat (+1.3%), so not new evidence and the weights stay. The noise leg cost about 3.9 points in 2026-01 (the legs-on run's deepest month) and gave +3.5 in 2024-07. Step 17 waits on the owner's a3.

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
