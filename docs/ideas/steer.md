# Steer - 2026-11-15 (weekly portfolio review; data to 2025-10-10)

## The book (docs/book.json, docs/gaps.json)
- Sharpe from 2018 **3.29** (risk layer on; 2.91 full) - profitable months **81%** from 2018 (17 losing of 94) - FTMO payout within 12 months **87%** (77% at edge 70).
- 11 legs; Dual Thrust is now counted (IN_BOOK "integrated") and fix runs at SCALE 0.5 next to cross. By period: 2.52 / 3.61 / 2.94
  (to 2017 / 2018-21 / 2022-25). Worst month -7.3%.
- Risk by market: USDJPY 25%, dollar pairs 26%, yen crosses 16%, US indices 11%, gold 8%, AUDCAD 8%, EU/Asia indices 7%, EURUSD 0%.
  No group above 35%. 9 of 11 legs are intraday; days = grid, weeks+ = hold.
- No new queue item since 2026-11-03. The last 20 ideas were all rejected.

## Top 3 gaps, one example each
1. **New index markets: 7 FTMO index CFDs with no data and no leg** (UK100, EU50, FRA40, AUS200, HK50, US30, US2000; docs/ftmo_specs.json).
   The two index rules that passed (Dual Thrust k1 0.3 / k2 0.7, N=4, j18; the noise-boundary rule, Zarattini-Aziz-Barbon 2024)
   trade only US500/US100/GER40/JPN225. Example: first a data item for histdata M1 UKXGBP, ETXEUR, FRXEUR, AUXAUD, HKXHKD,
   then Dual Thrust with **the j18 parameters unchanged** on 3+ of them as one basket. Leave out the rollover (lesson 9) and use the FTMO
   swaps and spreads. Expect a high corr with the Dual Thrust leg, so book gain decides. No refit; one variant only.
2. **Days horizon that pays when the gold hold loses.** hold lost in 13 of the 18 losing months from 2018 (14% of the loss, the
   largest share). The losing pairs: 2023-02 to 2023-06 (hold, after, breakout, grid), 2021-02 (grid, morning, Dual Thrust, noise),
   2024-05 (breakout, hold, after). The index legs (noise, Dual Thrust) offset 2024-07. Aim: a days leg with corr <= 0.1 that gains
   in 2023-02..06 and 2021-11. No untried paper this week. Take one only from a paper read in full that has evidence after 2010.
   Do not crawl venues for it.
3. **Weeks+ (only hold) and the carry / volatility-premium styles: parked.** Carry (5 tests), VRP (4), FX value, trend, Halloween,
   lunar, and sentiment timing (aligned PLS, Fisher-Statman, AAII, industry correlation: 4 rejections 11-02..03) all failed.
   gaps.py still lists carry and the volatility premium. Treat both as closed until the owner reopens them.

## Legs to recheck or cut (proposals for the owner; no edit made)
- **No cut this week.** No leg's removal raises the book's Sharpe in both halves from 2018 (python, book_sim.combine/risk_layer, by period):
  - morning: without it 3.30 from 2018 (+0.01), split -0.25 (2018-21) / +0.30 (2022-25), -0.08 before 2018. Mixed: keep.
    It is the third week in a row with the same sign flip. If 2022-25 stays positive and 2018-21 negative at the 11-29 review, ask the owner for
    a down-weight test then.
  - fall: 2018-21 -0.34 / 2022-25 +0.13. Mixed: keep.
  - grid: +0.02 / -0.12. hold: -0.11 / -0.15 from 2018 but +0.27 before 2018. Keep both.
- breakout at the 25% cap (Sharpe 0.84): without it 2.35 / 3.57 / 2.83, a cost in every period. Keep. Frozen per owner a6; check on 2026-11-22.
- Breakout and Dual Thrust together hold 39% of the weight in one style (breakout). Their corr with the book is 0.01 / 0.07, so this is no cut. It is
  why gap 1 must pass book gain on its own.

## Stop bringing
- Carry, VRP, policy gap, FX value, TSMOM or trend of any kind, COT extremes, Halloween or seasonal months, pre-holiday, overnight holds (swap).
- Sentiment timing of indices (AAII, PLS, consumer confidence, industry correlation, Baker-Wurgler).
- FX calendar, time-of-day, fix/month-end flows on the majors; pre-FOMC/ECB drift; post-ECB drift; turn-of-month long.
- Index reversals of every kind: VIX-conditioned, Baltussen, IBS, Monday dip, MA200 pullback, RSI(2), gap fade, Iwanaga.
  Also index pairs, cross mean reversion/RSI, oil-to-index, commodity FX lead, opex week, gold-silver spread.
- ML overlays on existing legs (meta-labels, regime gates, bandit/HRP weights, vol-managed sizing).
- Near-miss rule variants: all 28 rows closed 2026-11-15 (trend 11, FX mean reversion 14, index/gold reversal 3). All three themes were on this list or merged
  before.

## Data ready (marketdata/, out of git; research only to 2025-10-10)
- 3-month interbank rates, monthly, fred/IR3TIB01{US,EZ,JP,GB,CA,AU,CH,NZ}M156N (2002-04 to 2025-10).
- Policy rates, daily: fred/DFF, ECBDFR, IUDSOIA. Treasury 10-year: fred/DGS10. 10-year yields, monthly: fred/IRLTLT01{US,EZ,JP,GB,AU,CA,DE}M156N.
- FX spot, daily: fred/DEX*; implied vol: fred/GVZCLS, VIXCLS, EVZCLS; volidx/ (GVZ, OVX, MOVE, SKEW); vixidx/ (VIX, VIX3M, VVIX).
- CFTC COT legacy, weekly: cot/. AAII sentiment, UMCSENT, French 48 industries daily (sentiment ideas closed).
- Index M1: histdata/SPXUSD, NSXUSD, GRXEUR, JPXJPY; WTIUSD, XAGUSD M1; daily futures in commod/ (ES, NQ, ZN, ZB, CL, GC).
- **Missing for gap 1:** UKXGBP, ETXEUR, FRXEUR, AUXAUD, HKXHKD M1 (histdata), plus the FTMO specs for those symbols (already in docs/ftmo_specs.json).
