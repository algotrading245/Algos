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

## scan_slot_EURUSD_s25_L4_short (`scan_slot_EURUSD_s25_L4_short`)

Status **rejected**, pipeline step 9 of 20. Source: -.



Gates (2026-10-17): **FAIL at dsr**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | pass | 0.97 / 0.69 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.41 | >= 0.3 at 1.5x cost |
| dsr | FAIL | 0.403 (N=4768, luck bar 0.89) | >= 0.9 |
| corr | FAIL | book +0.25, max leg quartet +0.31 | |book| <= 0.2, |leg| <= 0.3 |
| goal | FAIL | Hydra 2018+ 3.37 -> 3.36 at weight 1.03; P(5x) 55.2% -> 55.1% | Sharpe gain >= 0.03, weight fitted to 2017 |

Notes: Rejected 2026-10-18 (orchestrator housekeeping): gates.py 2026-10-17 failed DSR (0.403 against 0.9), correlation (book +0.25) and goal (Hydra 2018+ 3.37 -> 3.36); no flow or paper gives it a reason. The status 'testing' was stale.

## scan_slot_EURUSD_s21_L8_short (`scan_slot_EURUSD_s21_L8_short`)

Status **rejected**, pipeline step 9 of 20. Source: -.



Gates (2026-10-17): **FAIL at dsr**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | pass | 0.96 / 0.79 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.60 | >= 0.3 at 1.5x cost |
| dsr | FAIL | 0.471 (N=4769, luck bar 0.89) | >= 0.9 |
| corr | pass | book +0.20, max leg quartet +0.23 | |book| <= 0.2, |leg| <= 0.3 |
| goal | FAIL | Hydra 2018+ 3.37 -> 3.36 at weight 1.03; P(5x) 55.2% -> 55.2% | Sharpe gain >= 0.03, weight fitted to 2017 |

Notes: Rejected 2026-10-18 (orchestrator housekeeping): gates.py 2026-10-17 failed DSR (0.471 against 0.9) and goal (Hydra 2018+ 3.37 -> 3.36); no flow or paper gives it a reason. The status 'testing' was stale.

## scan_cal_wed_EURUSD_s25_L2_short (`scan_cal_wed_EURUSD_s25_L2_short`)

Status **rejected**, pipeline step 9 of 20. Source: -.



Gates (2026-10-17): **FAIL at halves**

| Gate | Result | Figure | Rule |
|---|---|---|---|
| halves | FAIL | 1.03 / 0.41 | >= 0.5 to 2017 and from 2018 |
| costs | pass | 0.50 | >= 0.3 at 1.5x cost |
| dsr | FAIL | 0.125 (N=26010, luck bar 2.23) | >= 0.9 |
| corr | pass | book +0.01, max leg quartet +0.03 | |book| <= 0.2, |leg| <= 0.3 |
| goal | FAIL | Hydra 2018+ 3.37 -> 3.33 at weight 11.5; P(5x) 55.2% -> 54.8% | Sharpe gain >= 0.03, weight fitted to 2017 |

Notes: Rejected 2026-10-18 (orchestrator housekeeping): gates.py 2026-10-17 failed halves (1.03 / 0.41), DSR (0.125 against 0.9) and goal (Hydra 2018+ 3.37 -> 3.33), as the scans record already said. The status 'testing' was stale.

## Round-number stop cascades (Osler) (`osler_round`)

Status **rejected**, pipeline step 7 of 20. Source: Osler, NY Fed Staff Reports 150 (2002, 'Stop-loss orders and price cascades') and 125 (2001, 'Currency orders and exchange-rate dynamics'), both read in full 2026-10-18; PDFs in marketdata/papers/.

After price crosses a 00 or 50 level (last two quoted digits) it keeps going for 1-2 hours, because stop-loss buys sit just above round numbers (01-10, 51-60) and stop-loss sells just below (90-99, 40-49), while take-profits sit exactly on 00. Touches without a cross reverse more often than at arbitrary levels. Test: enter in the cross's direction once price is k pips past the level, hold 15-120 minutes.

Notes: Paper facts. SR150 (Reuters minute quotes, USD/DEM, USD/JPY, GBP/USD, New York 9:00-16:00, 1996-98): 'reach' = within 0.01% of the level; 'cross' = beyond it 15 minutes after reaching it (ex post, not tradeable as defined); moves signed in the approach direction. Table V, average move 15 min after a cross, round vs arbitrary levels: DEM 6.08 vs 5.37 bp, JPY 6.89 vs 5.98, GBP 4.92 vs 4.59 (excess +0.3 to +0.9 bp). Table VI.A, crossing minus reversing episodes: JPY +1.30 bp at 15 min, +1.34 at 30, +1.26 at 1 h, +2.35 at 2 h; DEM +1.12/+0.89/+0.57/+0.85; GBP +0.77/+0.80/+0.27/+0.35; negative at 1-2 days. Stronger after 12:30 New York (thinner market), no buy/sell asymmetry, weaker on 00-only levels, survives dropping BoJ intervention months. Large cascades about once a week vs about 5 round-number crosses a day, so the average is mostly ordinary crosses. Reversal on touch: round 58-60% vs arbitrary 55-57%. Order book (RBS, 9,667 orders, 1999-2000): stop-loss buys 14.4% at 01-10 vs 7.4% at 90-99, about 17-18% at 51-60 vs 6% at 40-49 (SR125's Table I prints the 50 rows in the other order, but its difference row and SR150's Table III agree); take-profits cluster exactly at 00; stops of $50m and over are 62% within 10 points of 00. SR125 adds a simulation only (order flow calibrated to the book reproduces both effects) and says the papers are 'silent on market efficiency... no attempt to evaluate risk-adjusted profits'. SR125 quotes the actual 30-min excess after a failed bounce as 0.0014% (0.14 bp) over 0.0063% for arbitrary levels, smaller still than SR150's tables. Prior: low. The gross edge is 0.3-2.4 bp, measured with an ex post cross; our USD/JPY cost is about 1.2 bp; the data are 25+ years old, from before algorithmic stop-running. Step 5-7 test spec (quant-coder, research/osler_round.py): USDJPY and EURUSD histdata M1 2009-2026 (marketdata/histdata/*_M1.csv.gz, bid quotes, so add the spread on entry); levels at 00 and 50 (JPY xx.00/xx.50, EUR 1.xx00/1.xx50), a 00-only variant; entry at the first M1 close k = 1, 3, 5 or 10 pips beyond a level after the price was on the other side within the last 15 minutes (a real-time cross); direction = the cross; exit after 15, 30, 60 or 120 minutes, or at a stop k pips back through the level; one trade per level per hour; sessions: all hours, London, New York, New York after 12:30 ET, no entries 21:00-23:00 UTC (rollover). Null: the same rule on arbitrary levels (10,000 random level grids shifted off 00/50, as in the papers); report round minus arbitrary per trade in bp, per 10-day block win count (binomial), and the reversal rate on touch. Pass to step 8 only if round minus arbitrary is positive in both halves (to 2017, from 2018) and the net Sharpe at 1.2 bp is >= 0.5 in both halves; then gates.py with 1.5x cost. Check overlap: correlation of daily returns with the breakout leg (USD/JPY London 10:00-18:00 server) and how many trades share its hours; rejected list has 'channel breakout', so a result that is just the generic breakout in disguise (arbitrary levels as good) is a fail. Result 2026-10-18 (research/osler_round.py, full run 710 s, USDJPY and EURUSD M1 2009-01 to 2026-10, 512 variants = 2 pairs x 2 level sets x k 1/3/5/10 x hold 15/30/60/120 x stop on/off x 4 sessions, 300 arbitrary grids each, costs 1.2 / 0.8 bp; trials line osler_round:grid count 512): REJECTED at steps 5-7. Step 5 data clean (no duplicates, 96-98% of weekday minutes, volatility peak at server 15:00 = 8:30 ET, so the clock is NY+7). No variant has net Sharpe >= 0.5 in both halves (0 of 512); the median gross per trade is negative (-0.46 / -0.22 bp) and the median round minus arbitrary is negative in both halves (-0.14 / -0.09 bp), so round levels do no better than arbitrary ones. Chosen on data to 2017: USDJPY 00-only, k=1, hold 120, no stop, NY after 12:30 ET: net Sharpe -0.16 to 2017, -0.69 from 2018; round minus arbitrary +0.86 then -0.46 bp; 10-day blocks 194/372 (p 0.22); 1.5x cost -0.53; correlation with the breakout leg -0.003, no shared hours. Reference k=3 / 30 min: gross -0.4 to +0.1 bp in every session, round at the 1st-89th percentile of arbitrary grids. Touch reversal goes against the paper on both pairs and in both halves: round 56-60% vs arbitrary 58-61% (-0.9 to -2.9 pp). Whatever SR150 saw in 1996-98 is not in 2009-26 M1 data, before or after costs.

## Rejected families

| Family | Examples | Why |
|---|---|---|
| Gold intraday fades | Asian dip buy, shock fade, LBMA auction dip, burst fade, Shanghai benchmark windows, London bias, weekend gaps | below cost or gone after 2017 |
| Breakouts other than USD/JPY | channel breakout, other dollar pairs, yen crosses, Nikkei, gold, 5-minute ORB on indices | too costly outside USD/JPY, or adds nothing next to the noise leg |
| Round-number levels | Osler stop cascades after 00/50 crosses (USDJPY, EURUSD M1 2009-26, 512 variants), touch reversals at round levels | round levels no better than arbitrary ones; gross below cost |
| Machine learning and RL | deep and RL replications, daily ML, tick ML scalp, Deep Momentum Networks, deep Q-learning on 20 futures | Sharpe <= 0.5 or seed-dependent; nothing after costs |
| Intraday momentum variants | market intraday momentum (all forms), Bitcoin intraday, oil on EIA days, VWAP trend, shorter windows | fails one half or dies on cost |
| Calendar and announcement drifts | pre-FOMC, FOMC cycle, overnight drift, turn of month, post-payroll and FOMC drift, holidays elsewhere | no edge after 2017 or below cost |
| Relative-value fades | silver vs gold, AUD/NZD, GBP/EUR, Nasdaq/S&P pairs, FX fixing reversals, 15-minute shocks | real reversion, smaller than the spread |
| Daily and slow strategies | time-series momentum on futures and crypto, VIX filters, reversal in stocks, gold/silver ratio | Sharpe 0.5-0.7 at best, correlated or costly |
| Re-weighting the book | volatility-managed sizing, exponentiated-gradient weights, re-fitted weights, quarter-end size-up | lowers Sharpe out of sample |
| Scalps and HFT | HFT, scalp concepts, night scalper on 11 pairs | 1-2 bp before cost |
