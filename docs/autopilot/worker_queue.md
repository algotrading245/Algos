# Worker queue

Open items ("- [ ]") for the worker (tools/autopilot/prompts/worker.md), top first. The worker takes one per run when
no candidate waits for a build and no idea in docs/ideas is unstarted, ticks it "- [x]" and adds " -> <outcome>".
The orchestrator and the owner add items here. Holdout: nothing from 2025-10-13 on.

## Items

- [x] Near-miss basket: take every spec in docs/ideas/near_miss.jsonl (failed a gate, both halves Sharpe > 0.3), rebuild each best variant's daily stream at real costs, scale each to the same target vol (past-only 60-day realised vol), equal-weight them into one basket and gate the basket (tools/gates.py). Count the basket and every weighting tried as trials; no picking members on the late half. -> rejected 2026-10-22 (6 members, halves 1.06/1.02, 1.5x cost 0.81, corr+goal pass, DSR 0.525 < 0.9 at N=27027; research/near_miss_basket.py)
- [x] Gold-silver ratio on H1: rerun gsr_meanrev on H1 bars (the 2026-10-22 run was D1 only), z-score of log(XAU/XAG), costs on both legs at the silver spread from the data request below (until it lands, the 4 bp round trip the scanners assume, and say so). Every lookback/threshold a trial. -> rejected 2026-10-22 (18 configs, all net Sharpe negative, best -0.19; assumed costs 2bp gold/10bp silver, silver spread not yet measured; research/gsr_meanrev_h1.py)
- [ ] Meta-label filter: LightGBM on AurumHydra's tester trades (features at entry: ATR, session, trend slope, spread, day of week) predicting win/loss; keep a trade only when p > threshold. Walk-forward, purge/embargo, 3 seeds. Gate the filtered trade stream.
- [x] Silver: port the gold legs to XAGUSD (same rules, silver costs). Check XAGUSD data in marketdata/ first; if missing, add a data request. -> rejected 2026-10-22 (bell/Tokyo/midday legs all negative net at 4-10 bp, halves -0.49/-1.02, DSR 0; assumed 4 bp since silver spread unmeasured; research/silver_legs_port.py)
- [x] Gold-silver ratio mean reversion: z-score of log(XAU/XAG) on H1 and D1, trade the spread back to the mean, costs on both legs. -> rejected 2026-10-22 (gsr_meanrev: D1 only, 18 configs, best Sharpe 0.07, FAIL halves/costs/DSR; H1 variant not run, same cost wall)
- [ ] Session and time-of-day scan on our own data: mean return and hit rate by hour and weekday for XAUUSD, USDJPY, EURUSD, US500, US100; Bonferroni over all cells; gate the survivors. -> done 2026-10-22 without US100 (no data): 5 survivors, 3 in the rollover, FAIL at goal (research/tod_weekday_scan.py)
- [x] Regime classifier (trend vs range: ADX, Hurst, realised-vol ratio; then a LightGBM version) that switches Hydra legs on and off; compare with all legs always on. -> rejected 2026-10-22 (walk-forward from 2014: rule 2018+ Sharpe 2.42 vs 2.57 always on, LightGBM 1.87 over 3 seeds, no leg improves; 504 trials; research/regime_switch.py)
- [x] Volatility forecast for sizing: HAR-RV vs GARCH(1,1) vs LightGBM on gold daily realised vol; size legs to a target vol; gate the resized stream against fixed size. -> rejected 2026-10-22 (forecasters tie on QLIKE; resizing a gold long adds +0.03 to +0.06 Sharpe, worse drawdown; halves 0.04/0.96, DSR 0.035; research/volforecast_sizing.py)
- [x] Index legs for AurumFunded: opening-range breakout and overnight drift on US500.cash / US100.cash under FTMO limits (5% daily, 10% total). -> rejected 2026-10-22 (SPX only, no US100 data; best overnight 01:00-16:30 halves 0.73/0.48, DSR 0.033, goal fail; ORB weaker; research/index_legs_funded.py)
- [x] Small neural net (1D CNN or LSTM, torch, CPU) on gold M15 returns for next-hour direction; must beat LightGBM and the baselines after costs, else reject. -> rejected 2026-10-22 (CNN/LGBM accuracy ~51-52%, net Sharpe -2.5/-2.7 at 2 bp, 12 flips a day; research/nn_gold_m15.py)
- [x] RL position sizing (PPO, stable-baselines3) on the Hydra leg mix: the agent picks each leg's size from 0 to 1 per day from past-only state (recent leg returns, drawdown, realised vol); reward is net return minus a drawdown penalty, costs charged on size changes. Walk-forward folds, 3+ seeds, every config a trial. Must beat equal fixed size and vol-targeted size, else reject. -> rejected 2026-10-22 (agent shrinks to mean size 0.11; Sharpe 1.03/1.67 vs fixed 1.95/2.57, worst seed 1.13; FAIL corr and goal; 36 trials; research/rl_leg_sizing.py)

## Data requests

- [ ] Silver spread: XAGUSD prices are in marketdata/histdata (M1 mid, 2009 on) but there is no spread. Get the XAGUSD spread and commission for FTMO (the tester install's symbol spec, or tick bid/ask exported from C:\MetaTrader 5 - Tester) and write it to docs/data/xagusd_costs.md with source and date, as bp per round trip. The scanners now assume 4 bp (research/atlas_scan.py COST, tools/backtest_legion.py 5.0); if the measured figure differs, say so there for the worker to update.

## For the owner
