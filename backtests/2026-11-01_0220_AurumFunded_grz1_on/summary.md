# j19: AurumFunded grz1 on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-11-01 03:10: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_grz.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set none, compare_set ['InpGrzMult=0.5'].

## legs off (`2026-11-01_0143_AurumFunded_grz1_off`)

| Measure | Value |
|---|---|
| Net profit | +13,339.78 (+133.4%) |
| Trades / win rate | 2289.0 / 52.34% |
| Profit factor | 1.65 |
| Max equity drawdown (relative) | 7.06% |
| Worst day | 2024-07-25 -2.59% |
| Return per unit of drawdown | 18.9 |
| By year | 2024 +4,191, 2025 +9,149 |
| History quality | 99% real ticks |

## legs on (`2026-11-01_0220_AurumFunded_grz1_on`)

| Measure | Value |
|---|---|
| Net profit | +13,732.36 (+137.3%) |
| Trades / win rate | 2298.0 / 52.26% |
| Profit factor | 1.63 |
| Max equity drawdown (relative) | 7.75% |
| Worst day | 2024-07-25 -2.45% |
| Return per unit of drawdown | 17.7 |
| By year | 2024 +5,117, 2025 +8,616 |
| History quality | 99% real ticks |

## On against off

Return per unit of equity drawdown: off 18.9, on 17.7 (not higher with the legs on).

## Expected (from the job)

Step 15 for AurumFunded v1.21 (month-reversal leg, magics +36 S&P 500 / +37 Nasdaq). Preset = OFF run; compare_set adds InpGrzMult=0.5 (ON run). Python (research/graziani_reversal.py, US500+US100 equal weight, gross 1.0, 1x cost): +7.1% over 2024.01-2025.09, max DD -16%, about 216 held days; the EA at SizeMult 0.5 x 0.5 x min(3,10%/vol) holds about 1/3 of that gross, so expect about +2.4% (+240 USD, 67-87% of it in the tester per lesson 4), added DD about 5%, roughly 8-10 entries per index (about 40% of months, a trade is renewed without closing when the next month signals again). Rule: last trading day of the month at 22:30 server, buy if price is below the 4th-Friday D1 close, hold to the next month last trading day 22:30, broker stop 5% of equity. Lesson 21: the book CloseEverything (day stop, open-loss stop) can close a month-long hold early; the Python has no such exits, so spot off-schedule closes (empty comment except sl). Do not tune on this window.

## Log lines worth a look

- `2026-11-01_0220_AurumFunded_grz1_on`: OQ	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: LS	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0220_AurumFunded_grz1_on`: RR	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: DR	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US100.cash failed, retcode 10018 (market closed)
- `2026-11-01_0220_AurumFunded_grz1_on`: NQ	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: IR	0	02:53:32.250	Core 1	2024.10.28 00:05:11   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0220_AurumFunded_grz1_on`: GM	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: DN	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: OR	0	02:53:32.250	Core 1	2024.10.28 00:05:22   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0220_AurumFunded_grz1_on`: EM	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: QN	2	02:53:32.250	Core 1	2024.10.28 00:05:32   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0220_AurumFunded_grz1_on`: NR	0	02:53:32.250	Core 1	2024.10.28 00:05:32   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
