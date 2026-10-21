# Worker queue

Open items ("- [ ]") for the worker (tools/autopilot/prompts/worker.md), top first. The worker takes one per run when
no candidate waits for a build and no idea in docs/ideas is unstarted, ticks it "- [x]" and adds " -> <outcome>".
The orchestrator and the owner add items here. Holdout: nothing from 2025-10-13 on.

## Items

- [ ] Meta-label filter: LightGBM on AurumHydra's tester trades (features at entry: ATR, session, trend slope, spread, day of week) predicting win/loss; keep a trade only when p > threshold. Walk-forward, purge/embargo, 3 seeds. Gate the filtered trade stream.
- [ ] Silver: port the gold legs to XAGUSD (same rules, silver costs). Check XAGUSD data in marketdata/ first; if missing, add a data request.
- [ ] Gold-silver ratio mean reversion: z-score of log(XAU/XAG) on H1 and D1, trade the spread back to the mean, costs on both legs.
- [ ] Session and time-of-day scan on our own data: mean return and hit rate by hour and weekday for XAUUSD, USDJPY, EURUSD, US500, US100; Bonferroni over all cells; gate the survivors.
- [ ] Regime classifier (trend vs range: ADX, Hurst, realised-vol ratio; then a LightGBM version) that switches Hydra legs on and off; compare with all legs always on.
- [ ] Volatility forecast for sizing: HAR-RV vs GARCH(1,1) vs LightGBM on gold daily realised vol; size legs to a target vol; gate the resized stream against fixed size.
- [ ] Index legs for AurumFunded: opening-range breakout and overnight drift on US500.cash / US100.cash under FTMO limits (5% daily, 10% total).
- [ ] Small neural net (1D CNN or LSTM, torch, CPU) on gold M15 returns for next-hour direction; must beat LightGBM and the baselines after costs, else reject.
- [ ] RL position sizing (PPO, stable-baselines3) on the Hydra leg mix: the agent picks each leg's size from 0 to 1 per day from past-only state (recent leg returns, drawdown, realised vol); reward is net return minus a drawdown penalty, costs charged on size changes. Walk-forward folds, 3+ seeds, every config a trial. Must beat equal fixed size and vol-targeted size, else reject.

## Data requests

## For the owner
