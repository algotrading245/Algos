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

The pass column above counts only challenges that ended; challenges still open at the 500-day limit are left out,
which flatters the small sizes. `python tools/prop_stress.py` counts open ones as not passed and adds a pessimistic
intraday stand-in (any day closing below -1.5% booked as a hit of the 3% day stop). At size 0.5, passed / failed
within 250 trading days: 96/0 at the backtested edge, 55/0 at half the edge, 46/0.2 at half with the stand-in, 37/0.4
at a third; within 500 days 100/0, 89/0, 82/4, 66/10. Size 1.0 within 250 days: 99/0, 74/15, 58/27, 52/31. FTMO has
no time limit, so size 0.5 stays the default: it keeps failures near zero, and larger sizes are faster only when
the edge holds. FTMO's 2-Step rules (10% / 5%, 5% daily on closed and open results, 10% static, 4 days, no time
limit) were checked again through third-party pages and FTMO's own 2-Step page on 2026-10-14.

**Strategy Tester, phase 1 (2026-10-15, owner's FTMO demo):** passed on 2024-10-25, 10 months after a 2024-01-01
start, equity drawdown at most 4.7%, worst day -1.6%, no day stop. All legs but the quartet's bell, Tokyo and midday
match the Python model; those three earned +2.0% against about 7% in the model. Details in
`backtests/2026-10-15_funded_phase1/summary.md`.
Phase 2 preset from the same 2024-01-01 start: passed (+5%) on 2024-02-20, drawdown 1.9%
(`backtests/2026-10-15_funded_phase2/summary.md`).
Funded-account preset, 2024-01-01 to 2026-10-14: +110% in 34 months, equity drawdown at most 4.1%, worst day -1.6%,
worst month -2.1%, mean month +2.25%, 23 of 34 months positive; about 70% of the Python model's log growth
(`backtests/2026-10-15_funded_account/summary.md`).

**v1.01 (2026-10-15): cushion sizing.** Size x (equity - final stop) / 8.5%, between 0.3 and 1.4: 1 at the start,
smaller toward the final stop, up to 1.4 with profit. On the path to the first payout (`tools/prop_sizing.py`, 70%
of the edge) the first payout comes within 9 months 46% of the time (old rule 37%), median 9.6 months (10.6), and
with half the edge and pessimistic intraday dips no path fails (7.8%). Not yet re-run in the Strategy Tester.
Firms (`tools/prop_firms.py`): an 8%/5% two-step (FundedNext Stellar, FundingPips) brings the first payout about a
month sooner than FTMO's 10%/5% (median 8.8-9.0 months against 9.8 at 70% of the edge); FTMO kept for its record.

**Fastest first payout: an instant account** (`tools/prop_instant.py`). FundedNext Stellar Instant (no challenge,
no daily limit, 6% trailing maximum loss, payout on the 14-day cycle, 70-80% share, $49.99 for 2K to $599.99 for 20K,
no refund, EAs need an add-on). With AurumFunded at size 0.3 and a guard 4.5% under the peak
(`AurumFunded_FundedNext_instant.set`): first payout within 1 month 43%, 3 months 74%, median 1.4 months, no
account lost (70% of the edge); half edge with pessimistic dips 59% within 3 months, 1.1% lost. The first claim is
about 1.7% of the account; the FTMO challenge pays far more per month but takes about 9.6 months to the first payout.

With AurumNoise added (0.55 of the S&P 500 + Nasdaq basket, 0.75 bp) the funded legs' Sharpe goes from 2.97 to 3.11,
the FTMO first payout within 6 months from 19% to 25% (median 9.6 -> 9.2 months), the instant account's within 3
months from 74% to 76%: worth having, but the challenge's speed is set by earning 15% at limited risk.

**Deadline sizing (`tools/prop_dp.py`, dynamic programming = what an RL agent would learn):** passes both phases
within 9 months 82% of the time at 70% of the edge with 1% failed (cushion rule 57%, 0%), but fails about 20% if the
live edge is only half. Use it only once live results confirm the edge; until then the cushion rule.
AurumFunded 1.02 has it as `InpPropFast` (off by default) in a safe form: the table only while equity is at or above
the phase's start, the cushion rule below - both phases within 9 months 67% (cushion rule 57%), median 7.3 months
(8.0), no failure even at half the edge with pessimistic dips. Not yet run in the Strategy Tester.

Open points for EA 2:

- Not yet run in the MT5 Strategy Tester; `tools/run-funded.ps1` runs it with a preset (written without PowerShell at
  hand, so untested). The symbol names in the inputs (`XAUUSD`, `US500.cash`, ...) are FTMO's as
  far as known and must be checked in the FTMO terminal.
- FTMO's server clock is assumed to follow European summer time (`InpEuClock true`). The EA checks the clock live and
  skips the day if it is off.
- Margin: FTMO Swing leverage is quoted (by a user on FTMO's feature board, not on FTMO's own page) as 1:30 on
  currencies, 1:9 on metals, 1:15 on indices. A gold unit at size 0.5 is about 1.2-1.5x equity at usual gold
  volatility and 3.1x at most (`InpMaxLeverage` 6.2 x 0.5), so 15-35% of equity in margin at 1:9, inside the
  per-order cap `InpMarginPct` (50% of free margin). The currency legs are far smaller. The tester run will confirm.
- The gold-unit broker stop is not in the Python model.

## EA 1: AurumHydra (v1.32)

Eight legs: quartet (gold session dip, bell fade, Tokyo fixing, EUR/USD midday), AUD/CAD grid, gold hold, month-end
fix on dollar pairs, the same on yen crosses, stock-fall fix, Tokyo morning, day after a US holiday. Combined Sharpe
3.0 (2.6 to 2017, 3.4 from 2018), volatility 24.5% a year. By calendar year the whole book's Sharpe is between 2.0 and 5.5 in every year
2010-2026 (AurumFunded's legs 1.9 to 5.3); 2023-2026 3.3; 2026 to date 2.0, with the quartet at 0.9, the weakest
year since 2023. With a Sharpe of 3 the best reachable chance of 5x in a
month is about 51%; the goal mode of the EA tests at 47% (preset `AurumHydra_5x_month.set`). If the live Sharpe is lower, the best chance falls with it: 34% at 1.5, 29% at 1.0, and 20% with no edge at all
(a fair bet sized to reach 5x does so one time in five), from P = N(N^-1(0.2) + Sharpe x sqrt(1/12)) (Browne 1999,
reaching a goal by a deadline). More chance needs more
Sharpe, which means new legs that are uncorrelated with these.

**Candidate leg (2026-10-15): noise-area intraday momentum on the S&P 500 and Nasdaq CFDs** (Zarattini, Aziz,
Barbon 2025, read in full; `research/noise_area_index.py`). Bands of the average move from the 9:30 open over 14
days, checked every half hour from 10:00 New York, trailing stop at the band or the session average price, flat
at 16:00, sized to 2% daily volatility. Half S&P 500 (band multiple 1.5), half Nasdaq (1.0): Sharpe 0.88 at 0.75
bp a round trip (0.61 to 2017, 1.08 from 2018), 0.57 at 1.5 bp; correlation with the Hydra legs -0.02. With the
weight fitted to 2017, Hydra from 2018 goes from 3.38 to 3.55 (0.75 bp) or 3.46 (1.5 bp). Standalone MQL5 version
`mql5/Experts/AurumNoise/` (presets for US500.cash and US100.cash), written without a compiler at hand: next is a
Strategy Tester run on FTMO's data, 2024-01 on, to see the real spread and slippage (Python on 2024-01 to 2026-10
from 10,000 at full size: US500 +1,550 before cost, +472 at 0.75 bp, drawdown 24-27%, 451 trades; US100 +5,352
before cost, +3,746 at 0.75 bp, +2,307 at 1.5 bp, drawdown 17-23%, 701 trades), then a merge into AurumHydra and
AurumFunded if it holds. DAX, FTSE, Nikkei,
currencies, oil, silver and gold do not add.

**Candidate leg (2026-10-15): USD/JPY London breakout** (the retail "London breakout" concept, own test;
`research/london_breakout.py`). Range = high and low of server 01:00-09:00; from 10:00 to 18:00 server follow the
first 5-minute break of it, stop at the range's other side, flat at 18:00. Sharpe 0.97 at 0.8 bp a round trip
(0.96 to 2017, 0.98 from 2018, positive in 16 of 17 years, 0.59 at 1.5 bp), every shifted window 0.73-1.17;
upside breaks carry it (t 4.4). Trading each side on its own (a buy and a sell stop that each fire once a day,
chosen on 2010-2017) gives 1.40 / 1.08 and is AurumBreakout 1.01's default; on real bid/ask ticks (2024-01 to
2026-09, `research/breakout_ticks.py`) fills cost ~1.2 bp all in, at which the leg is 1.18 / 0.83 and still lifts
AurumFunded 3.24 -> 3.30; the same breaks on the other dollar pairs do not earn, so it is a yen effect without a known cause. Correlation with the Hydra legs |r| <= 0.03. At 0.5% risk a trade Hydra 3.37 ->
3.48 from 2018 (3.66 with the noise leg), AurumFunded 3.24 -> 3.34; at AurumFunded's volatility 0.125% risk a
trade gives 3.30 with a lower drawdown (11.4% -> 10.8%). Gold, EUR/JPY and the other majors do not hold. Standalone
MQL5 version `mql5/Experts/AurumBreakout/` (uncompiled): a Strategy Tester run on USDJPY, 2024-01 on, comes next.

Both candidate legs in the prop simulators at AurumFunded's volatility (`tools/prop_candidates.py`, breakout on
both sides): FTMO first payout within 12 months 67% -> 72% (breakout), 72% (noise), 75% (both) at 70% of the edge,
no FTMO failures even at half the edge; the instant account's median 1.4 months unchanged; Sharpe from 2018 3.24 ->
3.51 with both. Neither enters the prop presets before its tester run. For AurumHydra's 5x month: Sharpe from 2018
3.37 -> 3.71 with both legs (breakout at 0.5% a trade, weight fitted to 2017), so P = N(N^-1(0.2) + S sqrt(1/12))
goes from 55% to 59%.

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
weekly reversal in US stocks, gold month-end flow; gold's London bias and weekend-gap fades (`research/gold_london_and_gaps.py`); hour-of-day returns of the hourly FX, gold and crypto
series (`research/hourly_seasonality.py`); drift after payrolls and FOMC decisions in the dollar pairs, gold and
the S&P 500 (`research/post_announcement_drift.py`); VWAP trend trading on the
Nasdaq and S&P 500 (Zarattini, Aziz 2023; dies on costs at 18 reversals a day, `research/vwap_trend_index.py`); front-running
pension rebalancing (Harvey, Mazzoleni, Melone 2025; month-end half holds after the paper but adds nothing to Hydra
in 2018-2023, `research/rebalancing_frontrun.py` - a lead to re-check); volatility-managed sizing of the legs (Moreira, Muir 2017; the legs earn in proportion to their volatility, so it only lowers the Sharpe, `research/vol_managed_legs.py`); the gold "Forecast-to-Fill" trend rule (Singha et al. 2025; its Sharpe 2.9 is same-close look-ahead, 0.5 when filled next day, `research/gold_forecast_to_fill.py`); Deep Momentum Networks (Lim, Zohren, Roberts 2019; Sharpe-optimised LSTM on the 20 futures, 2011-26 Sharpe 0.1 against 0.55 long only, `research/deep_momentum.py`); the AUDCAD grid on 15 other pairs (none holds after 2017, `research/grid_crosses.py`); the 5-minute opening range breakout on the Nasdaq and S&P 500 (Zarattini, Aziz 2023; 0.5-0.7 on true highs and lows, adds nothing next to the noise-area leg, `research/orb_index.py`); cross-session momentum in gold and silver (from the title of Wei 2026, the paper is behind SSRN; works only in the 2023-26 gold rally, `research/cross_session_metals.py`); the deep Q-learning trader of Zhang, Zohren, Roberts 2020 on the 20 futures (seeds give +0.54 to -0.17 at 2 bp, all <= 0 at 10 bp, `research/drl_futures.py`); a larger fix-leg size at quarter-ends (one-off check: quarter-end fixes earn the same as other month-ends, 64 vs 49 bp to 2017 and 84 vs 89 bp from 2018, and x2 at quarter-ends takes Hydra from 3.37 to 3.31 after 2017); the after-holiday leg for the yen and sterling (Japanese and English holidays: +2.9 bp t 1.3 and nothing, `research/after_holiday_other.py`); gold and silver in the month-end fix leg (one-off check with `fix(pairs=...)`: gold t 1.2, silver t 2.2 but correlated 0.35 with the fix leg, Hydra from 2018 3.37 -> 3.34-3.36); the "night scalper" fade of 15-minute Bollinger breaks after the New York rollover on 11 pairs (1-2 bp a trade before costs, -1.5 at 1 bp, `research/night_scalper.py`); gold around the Shanghai Gold Benchmark auctions, 10:15 and 14:15 Beijing (one-off check: windows of 15-120 minutes earn 0-1 bp, the same before the benchmark began in 2016 - the Asian-hours drift, below cost); an intraday Nasdaq / S&P 500 pairs fade (-2.8 bp a trade, the spread trends a little within the day but not enough to pay two legs, `research/index_pair_intraday.py`); fading 15-minute price shocks on 11 instruments (Grant, Wolf, Yu 2005; 0 bp before cost, `research/shock_reversal_fx.py`); online re-weighting of the legs by exponentiated gradient (Helmbold et al. 1998; 2.7 from 2018 against 3.37 fixed, `research/online_leg_weights.py`). Re-fitting the leg weights for the highest Sharpe does not hold
out of sample, so the EA's weights stay. The scans are in `research/`.

## Cloud sessions

The cloud container has no route to histdata.com, Dukascopy or Yahoo (the proxy refuses them), so the minute data
cannot be rebuilt there; only what is in the repository can be used (hourly gold and Hydra pairs from 2009, daily
futures, stocks, ETFs, volatility indices, crypto hourly from 2017). Allowing those hosts in the environment's network
settings would lift that. raw.githubusercontent.com and web search do work; no GitHub repository was found that holds
the minute data itself.

## Tools and data

- `tools/backtest_hydra.py`: every Hydra leg on minute data. `tools/backtest_prop.py`: the challenge simulator.
- Minute data (`marketdata/histdata/*_M1.csv.gz`, 7 GB) is not on GitHub; `tools/` has the histdata.com downloader
  that rebuilds it. Without it the challenge simulator still runs from the cached daily leg results.
- Compiling: `metaeditor64.exe /compile:<file> /include:<terminal data folder>\MQL5 /log:<file>`; see
  `tools/run-backtest.ps1`.
