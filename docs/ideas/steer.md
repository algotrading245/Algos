# Steer - 2026-10-31 (weekly portfolio review; data to 2025-10-10)

## The book (docs/book.json, docs/gaps.json)
- Sharpe from 2018 **3.11** (risk layer on; 2.75 full) - profitable months **78%** from 2018 (21 losing of 94) - FTMO payout within 12 months **91%** (67% at edge 70).
- 10 legs. No EURUSD leg, no carry or VRP leg, 8 of 10 legs intraday. Dollar pairs hold **35.3%** of the risk (cap 35%), USDJPY 25%.
- **The book leaves out a passed leg.** prebuilt_dual_thrust_four_indices_ew has status "integrated" (j18 PASS, AurumFunded v1.18).
  book_sim's IN_BOOK = tester/demo/live/ea, so it is not counted. With it: Sharpe from 2018 **3.26** (2.43 / 3.56 / 2.94 for
  to-2017 / 2018-21 / 2022-25, against 2.42 / 3.40 / 2.79), profitable months 82%, worst month -7.9%. The owner should add
  "integrated" to IN_BOOK in tools/book_sim.py (agents do not edit tools/). Gate 5 (book gain) probably uses the same baseline,
  so it is checked against a book that is too weak until then.

## Top 3 gaps, one example each
1. **The losing months (owner's target, 10-31), days horizon.** Split done this week (combine() weights, 21 losing months from 2018):
   the loss is spread out: after 16%, hold 14%, morning 13%, grid 11%, breakout 11%, fall 10%, noise 9%, quartet 8%, fix 6%,
   cross 2%. No leg or market drives them, so no single "hedge" exists. Any days leg with corr <= 0.1 lifts them.
   Example: Etula, Rinne, Suominen and Vaittinen (2020), "Dash for cash: monthly market impact of institutional liquidity
   needs" (RFS). Equities fall in the days before month-end payment dates and recover after. Take the **short** side of
   the pre-payment window (fixes the swap problem the long totm_us had) on US500, US100, GER40, JPN225, 1-3 day hold, with
   the window from the paper's tables after a full read. Not the same test as totm_us (long, turn-of-month, rejected).
2. **US/EU/Asian indices, 4% of the risk (before Dual Thrust is counted).** Example: the noise leg's rule (Zarattini, Aziz
   and Barbon 2024, "Beat the market", intraday momentum past the noise boundary) with **the same parameters** on GER40
   and JPN225 (histdata GRXEUR, JPXJPY M1). The noise leg trades only the US pair, and lesson 12 says its S&P half is weak.
   No test on DAX/Nikkei found in candidates.json. Leave the rollover out (lesson 9).
3. **Weeks+ horizon (only hold).** No untried example this week: fx_value_rer (-0.10/-0.53), carry, TSMOM and Ang-Chen all
   failed. Do not search for it until 1 and 2 are tested. EURUSD stays off the target list (owner 10-31, ~25 scans failed).

## Legs to recheck or cut (proposals for the owner; no edit made)
- **Halve fix as well: SCALE fix 0.5 next to cross 0.5** (one shared budget for the two fix-flow legs, corr 0.61).
  book_sim, same base: from 2018 3.11 -> **3.17**. By period 2.42 -> 2.54, 3.40 -> 3.47, 2.79 -> 2.82, so the gain holds in both
  halves and before 2018. Worst month -8.3% -> -8.0%, profitable months from 2018 77.7% -> 78.7%. It also brings the dollar
  pairs under the 35% cap. Cross 0.25 alone gives 3.19 (2.44 / 3.48 / 2.88) but leaves fix full. Caveat: picked on the same
  data as last week's cross halving; the gain is small. Recheck once Dual Thrust is counted.
- cross (3.21 without it, +0.10): +0.11 / +0.09 in 2018-21 / 2022-25 but -0.01 before 2018. Halving it is already in SCALE.
  Do not cut a Sharpe-1.24 leg; the fix 0.5 proposal covers most of it.
- grid (3.18 without, +0.07): +0.05 / +0.09 from 2018 but -0.15 before 2018. Mixed: keep.
- morning (3.18 without): -0.22 in 2018-21, +0.38 in 2022-25. Mixed: keep, recheck next week.
- fix (3.14 without): +0.08 / -0.01 from 2018. Mixed: the scale proposal above is the safer form.
- breakout at the 25% cap: 3.08 without it (-0.03 in total, -0.09 2018-21). Keep; frozen per owner a6, check 2026-11-22.

## Stop bringing
- Carry, VRP, policy gap, FX value (fx_value_rer), TSMOM/trend of any kind, COT extremes.
- FX calendar, time-of-day, fix/month-end flows on the majors; pre-FOMC/ECB drift; turn-of-month long (totm_us).
- VIX-conditioned index reversals (nagel, jones_pyun: two rejections), Baltussen reversal (daily and last 30 min), index
  pairs (thomakos), cross mean reversion/RSI (all near-miss themes closed), oil-to-index, commodity FX lead, opex week.
- ML overlays on existing legs (meta-labels, regime gates, bandit/HRP weights, vol-managed sizing): 12+ rejected 10-25..31.
- Searches that return 0 ideas. Take example 1 or 2 to a full read and the queue first.

## Data ready (marketdata/, out of git; research only to 2025-10-10)
- 3-month interbank rates, monthly, fred/IR3TIB01{US,EZ,JP,GB,CA,AU,CH,NZ}M156N (2002-04 to 2025-10).
- Policy rates, daily: fred/DFF, ECBDFR, IUDSOIA. Treasury 10-year: fred/DGS10. 10-year yields, monthly: fred/IRLTLT01{US,EZ,JP,GB,AU,CA,DE}M156N.
- FX spot, daily: fred/DEXUSEU, DEXUSUK, DEXUSAL, DEXUSNZ, DEXJPUS, DEXCAUS, DEXSZUS, with the FRED CPI files.
- Implied vol: fred/GVZCLS, VIXCLS, EVZCLS (stops 2025-03-11); volidx/ (GVZ, OVX, MOVE, SKEW); vixidx/ (VIX, VIX3M, VVIX).
- CFTC COT legacy, weekly: cot/{AUD,CAD,CHF,EUR,GBP,JPY,GOLD}.csv.
- Index M1 for gaps 1 and 2: histdata/SPXUSD, NSXUSD, GRXEUR (DAX), JPXJPY (Nikkei); daily futures in commod/ (ES, NQ, ZN, ZB, CL, GC).
- Gap 1 needs no new data (month-end calendar from the index files).
