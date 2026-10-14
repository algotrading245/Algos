# Handoff: where the two-EA project stands

For a session that picks this work up without the earlier conversation (for example a cloud session). Last updated
2026-10-14.

## Goal

Two MT5 expert advisors, and the work does not stop until both exist:

1. **5x EA**: turn $100 into $500 in a month with the highest probability. This is `mql5/Experts/AurumHydra/`.
2. **Funded-account EA**: pass a prop-firm challenge and keep the funded account with the highest probability. This is
   `mql5/Experts/AurumFunded/`.

The owner gave a free hand: any source (SSRN, Google Scholar, anything else), any prebuilt strategy or own idea, and
the choice of prop firm and challenge is ours. What stays with the owner: buying a challenge, attaching EAs in MT5,
running the Strategy Tester and demo, and a yes before each live or real-money step.

Rules of the work:

- Nothing goes into an EA unless it survives realistic costs in both halves of the data (to 2017, and 2018 on;
  `SPLIT` in the tools).
- When a paper is used, read the full paper first (definitions, tables), not the abstract, and say in reports which
  papers were read in full.
- Order: Python backtest, then MT5 Strategy Tester, then demo, then live.
- Commit and push to the session's working branch after each finished piece of work (earlier sessions:
  `claude/exciting-hopper-r6sdmc`; the cloud session of 2026-10-14: `claude/intelligent-turing-j0nrmf`).

## EA 2: AurumFunded (v1.00, compiles with 0 errors and 0 warnings, not yet run in the Strategy Tester)

Firm chosen: **FTMO 2-Step Challenge, Swing account**. Targets 10% then 5%, daily loss 5% of the initial balance
measured from the balance at midnight CE(S)T on equity, maximum loss 10% static, no time limit, at least 4 trading
days a phase, EAs allowed, Swing has no news or weekend restriction, leverage 1:30. Backup: **The5ers High Stakes**
(10% / 5%, 5% daily, 10% maximum, 3 profitable days a phase, 1:100, no orders within 2 minutes of high-impact news).
Rules were read on the firms' own pages on 2026-10-14; check them again before a challenge is bought.

The EA is AurumHydra v1.32 without its grid and gold hold, at half size (`InpSizeMult 0.5`), plus a guard
(`PropGuard` in the source): day stop at 3%, final stop at 8.5%, sizes shrink once equity is within 6.5% of the
final stop, stop at the target once the minimum trading days are done, a broker-side stop on each gold unit, and no
trading on days the server clock is not New York + 7 hours. State is kept in terminal global variables, so a restart
does not lose the day's starting balance. Presets for phase 1, phase 2 and the funded account are next to the source.

Simulated on daily leg results 2010-2026 (`python tools/backtest_prop.py`, legs in
`marketdata/hydra_legs_daily.csv.gz`). Daily data cannot see a day that dips below a limit and recovers, so these are
upper bounds:

| Edge assumed | Size | Shrink rule | Pass | Median days | Funded alive after 12 months | Paid in 12 months |
|---|---|---|---|---|---|---|
| as backtested | 0.5 | on | 100% | 124 | 100% | 33% |
| as backtested | 1.0 | on | 100% | 68 | 100% | 64% |
| half | 0.5 | off | 94% | 223 | 93% | 19% |
| half | 0.5 | on | 100% | 238 | 100% | 18% |
| a third | 0.5 | on | 92% | 287 | 100% | 13% |
| a third | 1.0 | on | 66% | 105 | 59% | 20% |

Open points for EA 2:

- Not yet run in the MT5 Strategy Tester. The symbol names in the inputs (`XAUUSD`, `US500.cash`, ...) are FTMO's as
  far as known and must be checked in the FTMO terminal.
- FTMO's server clock is assumed to follow European summer time (`InpEuClock true`). The EA checks the clock live and
  skips the day if it is off.
- At 1:30 (less on metals) the margin cap `InpMarginPct` may shrink the gold units; the tester run will show it.
- The gold-unit broker stop is not in the Python model.

## EA 1: AurumHydra (v1.32)

Eight legs: quartet (gold session dip, bell fade, Tokyo fixing, EUR/USD midday), AUD/CAD grid, gold hold, month-end
fix on dollar pairs, the same on yen crosses, stock-fall fix, Tokyo morning, day after a US holiday. Combined Sharpe
3.0 (2.6 to 2017, 3.4 from 2018), volatility 24.5% a year. With a Sharpe of 3 the best reachable chance of 5x in a
month is about 51%; the goal mode of the EA tests at 47% (preset `AurumHydra_5x_month.set`). More chance needs more
Sharpe, which means new legs that are uncorrelated with these.

Tested and rejected (do not repeat): Asian dip buy and shock fade, LBMA auction dip, burst fade, channel breakout,
deep and reinforcement learning replications, HFT, market intraday momentum (unconditional, both-agree, big-move),
minute slot scan, daily ML, noise-area momentum, session-open drift, overnight-intraday reversal, scalp concepts,
tick ML scalp, FX fixing reversals, pre-FOMC drift, overnight drift, FOMC cycle, FX local hours, pre-announcement
drift, turn of month, market return around the clock, Bitcoin intraday momentum, market intraday momentum under
short-gamma proxies (high VIX, falling or jump day), shorter last windows, next-day fade of the last half hour, crude oil
intraday momentum on EIA report days (Wen, Indriawan, Lien, Xu 2023; `research/oil_eia_intraday.py`),
time-series momentum on 20 daily futures (Sharpe 0.5 at best; `research/futures_tsmom.py`), time-series momentum on
Bitcoin and Ether (Sharpe 0.5 to 0.7 long-short since 2022 before CFD swap; `research/crypto_tsmom.py`), and in `research/daily_candidates.py`: SPY before holidays, SPY under
a VIX term-structure filter, gold/silver ratio fade, Monday after a falling Friday, SPY after VIX spikes, daily and
weekly reversal in US stocks, gold month-end flow; gold's London bias and weekend-gap fades (`research/gold_london_and_gaps.py`). Re-fitting the leg weights for the highest Sharpe does not hold
out of sample, so the EA's weights stay. The scans are in `research/`.

## Cloud sessions

The cloud container has no route to histdata.com, Dukascopy or Yahoo (the proxy refuses them), so the minute data
cannot be rebuilt there; only what is in the repository can be used (hourly gold and Hydra pairs from 2009, daily
futures, stocks, ETFs, volatility indices, crypto hourly from 2017). Allowing those hosts in the environment's network
settings would lift that.

## Tools and data

- `tools/backtest_hydra.py`: every Hydra leg on minute data. `tools/backtest_prop.py`: the challenge simulator.
- Minute data (`marketdata/histdata/*_M1.csv.gz`, 7 GB) is not on GitHub; `tools/` has the histdata.com downloader
  that rebuilds it. Without it the challenge simulator still runs from the cached daily leg results.
- Compiling: `metaeditor64.exe /compile:<file> /include:<terminal data folder>\MQL5 /log:<file>`; see
  `tools/run-backtest.ps1`.
