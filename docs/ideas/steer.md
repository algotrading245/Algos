# Steer - 2026-10-24 (owner session, before the first portfolio review)

The portfolio manager replaces this file at its Saturday 10:00 run. Keep the "Data ready" list.

## The book (gaps.py, data to 2025-10-10)
- Sharpe from 2018: 3.01 with the risk layer on. 10 legs. 19 losing months of 94.
- No leg on EURUSD. No carry or volatility premium style. Days and weeks+ horizons are thin. Dollar pairs are crowded (36% of risk).

## Top 3 gaps, with one example idea each
1. **Carry (FX).** Example: once a month, rank the G10 currencies by their 3-month rate (files below). Go long the 2-3
   highest-yielding and short the 2-3 lowest, through the FTMO pairs, and hold for a month. Sources: Lustig, Roussanov
   and Verdelhan (2011), "Common risk factors in currency markets"; Menkhoff, Sarno, Schmeling and Schrimpf (2012),
   "Carry trades and global FX volatility". Menkhoff et al. also cut carry when FX volatility jumps, which links gaps 1 and 2.
   Cost: at FTMO you earn the swap, not the rate gap. Swaps today (docs/ftmo_specs.json, points per lot per night):
   AUDJPY long +4.27, short -15.34; GBPJPY long +5.14, short -25.36. Estimate the broker's markup as today's rate gap
   minus today's swap, then subtract that markup from the rate gap in every past month. Long AUDJPY or GBPJPY adds to
   the yen crosses (20% of risk), so judge the idea by what it adds to the book.
2. **Volatility premium.** Example: implied volatility minus realized volatility over the last 22 days, for gold
   (GVZCLS minus XAUUSD realized), US500 (VIXCLS minus US500 realized) and EURUSD (EVZCLS minus EURUSD realized).
   Rule: when the gap is in its top third over the last year, go long the asset for 1-4 weeks. Source: Bollerslev,
   Tauchen and Zhou (2009), "Expected stock returns and variance risk premia", for equities. We have no options, so
   use the gap as a timing signal; we cannot sell volatility directly. Three markets with the same parameters.
3. **EURUSD, days to weeks.** Example: when the ECB-Fed policy gap moves (ECBDFR minus DFF, 3-month change), trade
   EURUSD in that direction for weeks. Run the same rule on GBPUSD (IUDSOIA minus DFF) and USDJPY. EVZ-based
   volatility premium on EURUSD (idea 2) also fills this gap.

## Data ready (in marketdata/fred/, out of git; research only to 2025-10-10)
- 3-month interbank rates, monthly, IR3TIB01{US,EZ,JP,GB,CA,AU,CH,NZ}M156N. Each starts between 1956 and 2002
  (JP 2002-04, CH 1999-07) and runs to 2026, so the common sample is 2002-04 to 2025-10.
- Daily policy rates: DFF (Fed funds, from 1954), ECBDFR (ECB deposit rate, from 1999), IUDSOIA (SONIA, from 1997).
- Implied volatility, daily: GVZCLS (gold, 2008-06 on), VIXCLS (US500, 1990 on), EVZCLS (euro, 2007-11 to
  2025-03-11; the series stops there). marketdata/volidx/ has GVZ, OVX, MOVE and SKEW; marketdata/vixidx/ has VIX, VIX3M and VVIX.
- No FX forward points: covered interest parity makes the forward discount equal to the rate gap, so the IR3TIB01
  files stand in for them.

## Legs to recheck or cut
- breakout: frozen while a6 is open (it failed the belief gate on 9 markets). The portfolio manager decides the rest.

## Stop bringing
- FX calendar, time-of-day and short-term reversal effects on the majors. The 10-22 and 10-23 ideas of this kind failed
  the halves gate: dao_weekend_gap (0.02/0.32), totm_us (-0.11/0.14), overreaction_fx (0.62/-0.00).
- Papers on single stocks only, and sources already logged in docs/ideas/sources.jsonl.
- Dropping a carry or volatility premium source because it "needs implied vols / forward points". The data is listed above.
