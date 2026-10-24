# Steer - 2026-10-24 (weekly portfolio review; data to 2025-10-10)

## The book (docs/book.json, docs/gaps.json)
- Sharpe from 2018 **3.01** (risk layer on; 2.68 full) - profitable months **80%** from 2018 (19 losing of 94) - FTMO payout within 12 months **92%** (69% at edge 70).
- 10 legs. No leg on EURUSD; no carry or volatility premium leg; 8 of 10 legs are intraday. Dollar pairs hold 36% of the risk (cap 35%).

## Top 3 gaps, one example each (all untried: memory search found no test)
1. **EURUSD, cross-asset, days to weeks.** Hau and Rey (2006), "Exchange rates, equity prices and capital flows"
   (RFS; NBER w9398, not SSRN). Foreign equity that beats US equity gets rebalanced, so its currency weakens. Rule: when
   DAX beat US500 by more than 1 sd over the last 20 days, short EUR against USD for 10 days, and the opposite when it lagged. Use the same
   rule for USDJPY (Nikkei against US500) and EURJPY (DAX against Nikkei). Data: GRXEUR, JPXJPY, SPXUSD M1 in histdata.
2. **US indices, days (4% of risk now).** Baltussen, van Bekkum and Da (2019), "Indexing and stock market serial
   dependence around the world" (JFE): since the 2000s, daily index returns have turned negatively autocorrelated in
   about 20 markets. Rule: after a down close, hold long to the next close (short after an up close, if the gates allow).
   Run it on US500 and US100, and check belief on DAX and Nikkei with the same parameters. The cost is the spread plus one night's swap (~2.5 bp).
   Not the same as their last-half-hour paper (noise-leg family).
3. **FX, weeks+, not carry.** Ang and Chen (2010), "Yield curve predictors of foreign exchange returns": the
   term-spread differential predicts monthly FX returns beyond the rate gap. Take the sign from the paper's tables after a full read.
   Run it monthly on EURUSD, USDJPY, GBPUSD, AUDUSD and USDCAD, net of FTMO swaps. It needs one data item (below).

## Legs to recheck or cut (proposals for the owner; no edit made)
- **fix + cross: give them one shared risk budget** (or halve cross). Their correlation is 0.61, but equal risk counts them as two
  independent legs, worth 26% of the risk together. Book Sharpe from 2018 without cross: 3.21 (gaps.py). Recheck on the same
  basis (book_sim, base 3.03): with fix+cross as one leg, 3.19. By period: to 2017 2.38->2.38, 2018-21 3.23->3.44, 2022-25
  2.81->2.90. Halving cross gives 3.21 (2.43 / 3.47 / 2.92). Cutting cross alone also lifts every period, but it throws away
  a leg with Sharpe 1.24. Cost: worst month -7.98% -> -8.62%; losing months stay at 19. It also brings the dollar pairs below the 35% cap.
- fix alone (3.08 without it): mixed, +0.19 in 2018-21 and -0.06 in 2022-25. Keep it; the merge above covers it.
- grid (3.04 without it: +0.08 / -0.01) and morning (3.04: -0.18 / +0.28): the gain does not hold in both halves. Keep both.
- breakout is at the 25% cap but adds little (2.98 without it). Halving it costs 0.06, so keep it. Still frozen while a6 is open.
- Losing months: hold (26% of the loss), after (24%), morning (21%) and fall (19%) carry most of it. No single leg
  drives them, and 2021-11 (-8.0%) and 2023-05 (-6.2%) were broad. A leg that offsets them has to be off-gold, off-intraday,
  and earn when the gold trend reverses. Gaps 1 and 3 aim there.
- Note for the owner: the gates quote the book at 3.34, but book_sim and gaps give 3.01. Align the baseline the gate's "book gain" uses.

## Stop bringing
- More carry, VRP or policy-gap variants. Each was tested once and failed the halves: fx_carry_g10_monthly_swapadj
  (-0.11/-0.16), vrp_gap_timing_3mkts (-0.03/0.39), policy_gap_eurusd_weeks (0.12/-0.44), bsic_vix_vxv (0.66/-0.25).
  Without options, volatility premium is not a reachable style. Leave it off the target list.
- TSMOM and trend, time-series or cross-sectional (futures_tsmom rejected; hold covers gold). COT extremes (cot_contrarian, -0.04/0.28).
- FX calendar, time-of-day and short reversal effects on the majors (dao_weekend_gap, totm_us, overreaction_fx,
  breedon_ranaldo). Pre-FOMC/ECB drift. Month-end or fix flows (fix and cross already trade them).
- Searches that return 0 ideas run after run (about 350 finder runs, 0 queued since 10-23). Take one of the 3 named papers to a full
  read and the queue before searching again. Never drop a simple rule on 3+ markets for "no costed paper": the builder
  measures the costs.

## Data ready (marketdata/, out of git; research only to 2025-10-10)
- 3-month interbank rates, monthly, fred/IR3TIB01{US,EZ,JP,GB,CA,AU,CH,NZ}M156N (common sample 2002-04 to 2025-10).
- Policy rates, daily: fred/DFF, ECBDFR, IUDSOIA. Treasury 10-year: fred/DGS10 (1962 on).
- FX spot, daily: fred/DEXUSEU (1999 on), DEXUSUK, DEXUSAL, DEXUSNZ, DEXJPUS, DEXCAUS, DEXSZUS (1971 on), with the FRED CPI files.
- Implied vol: fred/GVZCLS, VIXCLS, EVZCLS (stops 2025-03-11); volidx/ (GVZ, OVX, MOVE, SKEW); vixidx/ (VIX, VIX3M, VVIX).
- CFTC COT legacy futures-only, weekly: cot/{AUD,CAD,CHF,EUR,GBP,JPY,GOLD}.csv (done 2026-10-24).
- Index M1 for gaps 1 and 2: histdata/SPXUSD, NSXUSD, GRXEUR (DAX), JPXJPY (Nikkei); daily futures in commod/ (ES, NQ, ZN, ZB, CL, GC).
- **Needed for gap 3:** FRED IRLTLT01{US,EZ,JP,GB,AU,CA}M156N (monthly 10-year yields). Queue it as a data item.
