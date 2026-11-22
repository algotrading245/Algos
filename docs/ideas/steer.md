# Steer - 2026-11-22 (weekly portfolio review; data to 2025-10-10)

## The book (docs/book.json, docs/gaps.json)
- Sharpe from 2018 **3.29** (risk layer on; 2.91 full) - profitable months **81%** from 2018 (17 losing of 94) - FTMO payout within 12 months **87%** (77% at edge 70).
- Unchanged from 11-15: same 11 legs, no new queue item since 11-15 (only the index M1 data item, done). By period 2.52 / 3.61 / 2.94
  (to 2017 / 2018-21 / 2022-25). Worst month -7.3%.
- Risk by market: dollar pairs 26%, USDJPY 25%, yen crosses 16%, US indices 11%, gold 8%, AUDCAD 8%, EU/Asia indices 7%, EURUSD 0%.
  No group above 35%. 9 of 11 legs are intraday; days = grid, weeks+ = hold.

## Top 3 gaps, one example each
1. **New index markets: the data is now in marketdata/ - this is the item to bring this week.** UK100, FRA40, AUS200, HK50 M1 to 2026-11
   (EU50/ETXEUR only to 2019-03, so leave it out). Example: Dual Thrust with **the j18 parameters unchanged** (k1 0.3 / k2 0.7, N=4) on
   UK100 + FRA40 + AUS200 + HK50 as one equal-risk basket, FTMO spreads and swaps (docs/ftmo_specs.json), rollover out (lesson 9), research
   data through tools/holdout.py. One variant, no refit. Expect corr with the Dual Thrust leg; book gain (+0.03) decides.
   A second, separate item may test the noise-boundary rule (Zarattini-Aziz-Barbon 2024) on the same four with its published settings.
2. **Days horizon that pays when the gold hold loses.** The worst clusters: 2023-02..06 (hold, after, breakout, grid), 2021-02 (grid,
   morning, Dual Thrust, noise), 2021-11 and 2024-05 (breakout, hold, after). Aim: a days leg with corr <= 0.1 that gained in 2023-02..06.
   Only from a paper read in full with evidence after 2010; do not crawl venues for it.
3. **EURUSD has no leg (0% risk).** Only via a rule already proven on 3+ other markets (e.g. the breakout leg's rule on EURUSD as a
   portability check, same parameters), not a new EURUSD-only calendar/flow rule (those are on the stop list).
- Weeks+ and the carry / volatility-premium styles stay parked (carry 5 tests, VRP 4, FX value, trend, sentiment all failed) until the owner reopens them.

## Legs to recheck or cut (proposals for the owner; no edit made)
- **No cut this week.** Book Sharpe change without each leg, by period (to 2017 / 2018-21 / 2022-25; book_sim.combine + risk_layer):
  - morning: -0.08 / -0.25 / +0.30 (3.30 from 2018, +0.01). Mixed in the 2018+ halves: keep. Fourth week with the same split; the
    data has not changed since 11-15, so 11-29 will show the same. Recheck only when the data window moves.
  - fall: -0.06 / -0.34 / +0.13. Mixed: keep.
  - grid: -0.21 / +0.02 / -0.12. hold: +0.27 / -0.11 / -0.15. Both add from 2018: keep.
  - fix -0.09 / -0.05 / -0.09, cross -0.02 / -0.04 / -0.08: both add in every period.
- breakout at the 25% cap (Sharpe 0.84): without it -0.17 / -0.04 / -0.11, a cost in every period. Keep. The owner's a6 check (due 11-22) is done: keep frozen.
- Breakout + Dual Thrust hold 39% of the weight in one style. Corr with the book 0.01 / 0.07, so no cut; it is why gap 1 must pass book gain on its own.

## Stop bringing
- Carry, VRP, policy gap, FX value, TSMOM or trend of any kind, COT extremes, Halloween or seasonal months, pre-holiday, overnight holds (swap).
- Sentiment timing of indices (AAII, PLS, consumer confidence, industry correlation, Baker-Wurgler).
- FX calendar, time-of-day, fix/month-end flows on the majors; pre-FOMC/ECB drift; post-ECB drift; turn-of-month long.
- Index reversals of every kind: VIX-conditioned, Baltussen, IBS, Monday dip, MA200 pullback, RSI(2), gap fade, Iwanaga.
  Also index pairs, cross mean reversion/RSI, oil-to-index, commodity FX lead, opex week, gold-silver spread, betting-against-beta.
- ML overlays on existing legs (meta-labels, regime gates, bandit/HRP weights, vol-managed sizing).
- Refits of the Dual Thrust / noise parameters for the new indices (gap 1 is one fixed variant only).
- Near-miss rule variants: all 28 rows closed 2026-11-15; no new rows this week.

## Data ready (marketdata/, out of git; research only to 2025-10-10)
- 3-month interbank rates, monthly, fred/IR3TIB01{US,EZ,JP,GB,CA,AU,CH,NZ}M156N (2002-04 to 2025-10).
- Policy rates, daily: fred/DFF, ECBDFR, IUDSOIA. Treasury 10-year: fred/DGS10. 10-year yields, monthly: fred/IRLTLT01{US,EZ,JP,GB,AU,CA,DE}M156N.
- FX spot, daily: fred/DEX*; implied vol: fred/GVZCLS, VIXCLS, EVZCLS; volidx/ (GVZ, OVX, MOVE, SKEW); vixidx/ (VIX, VIX3M, VVIX).
- CFTC COT legacy, weekly: cot/. AAII sentiment, UMCSENT, French 48 industries daily (sentiment ideas closed).
- Index M1: histdata/SPXUSD, NSXUSD, GRXEUR, JPXJPY; WTIUSD, XAGUSD M1; daily futures in commod/ (ES, NQ, ZN, ZB, CL, GC).
- **New (done 2026-11-15, gap 1):** histdata M1 UKXGBP, FRXEUR, AUXAUD, HKXHKD (to 2026-11); ETXEUR only to 2019-03. FTMO specs in docs/ftmo_specs.json.
