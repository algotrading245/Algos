# j20: AurumFunded grz2 on XAUUSD M15

Written by tools/autopilot/tester_step.py 2026-11-01 04:17: figures only, the judge judges.
Preset `mql5/Experts/AurumFunded/AurumFunded_FTMO_phase1_grz2.set`, deposit 10000, leverage 1:33, 2024.01.01 to 2025.09.30, set none, compare_set ['InpGrzMult=0.5'].

## legs off (`2026-11-01_0310_AurumFunded_grz2_off`)

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

## legs on (`2026-11-01_0342_AurumFunded_grz2_on`)

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

Step 15 for AurumFunded v1.22 (month-reversal leg after the 11-01 review fixes; supersedes diagnostic j19). Preset = OFF run; compare_set adds InpGrzMult=0.5 (ON run). Python with FTMO swaps (US500 2.38, US100 2.91 bp/night, triple Friday), research/graziani_reversal.py: Sharpe 0.44/0.57 by half at 1x, 0.36 at 1.5x, 54 + 61 holds 2010-2025, about 40% of months. 2024.01-2025.09: roughly 7 (US500) + 10 (US100) held months, small size (mean notional 0.17-0.22 x equity) so expect about +1 to 2% (+100 to 200 USD, 67-87% in the tester), worst hold-to-date equity loss about -1.7%, worst day -0.85% (research/graziani_book_exits.py: broker stop 5% never reached on closes, no hold would hit the 3% day stop alone). Lesson 21: the book CloseEverything can still close a hold as a bystander, so spot off-schedule closes (empty comment other than sl). Good Friday 2024-03-29 must not be a month-end entry day (March 2024 last trading day is 03-28); renewals keep the hold open past day 40 of the first month.

## Log lines worth a look

- `2026-11-01_0310_AurumFunded_grz2_off`: OQ	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: LS	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0310_AurumFunded_grz2_off`: RR	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: DR	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US100.cash failed, retcode 10018 (market closed)
- `2026-11-01_0310_AurumFunded_grz2_off`: NQ	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: IR	0	02:53:32.250	Core 1	2024.10.28 00:05:11   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0310_AurumFunded_grz2_off`: GM	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: DN	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: OR	0	02:53:32.250	Core 1	2024.10.28 00:05:22   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0310_AurumFunded_grz2_off`: EM	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: QN	2	02:53:32.250	Core 1	2024.10.28 00:05:32   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0310_AurumFunded_grz2_off`: NR	0	02:53:32.250	Core 1	2024.10.28 00:05:32   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0342_AurumFunded_grz2_on`: OQ	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: LS	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0342_AurumFunded_grz2_on`: RR	2	02:53:32.250	Core 1	2024.10.28 00:05:01   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: DR	0	02:53:32.250	Core 1	2024.10.28 00:05:01   AurumFunded: close on US100.cash failed, retcode 10018 (market closed)
- `2026-11-01_0342_AurumFunded_grz2_on`: NQ	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: IR	0	02:53:32.250	Core 1	2024.10.28 00:05:11   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0342_AurumFunded_grz2_on`: GM	2	02:53:32.250	Core 1	2024.10.28 00:05:11   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: DN	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: OR	0	02:53:32.250	Core 1	2024.10.28 00:05:22   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
- `2026-11-01_0342_AurumFunded_grz2_on`: EM	2	02:53:32.250	Core 1	2024.10.28 00:05:22   failed market sell 0.09 US100.cash, close #1775 buy 0.09 US100.cash 19514.25 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: QN	2	02:53:32.250	Core 1	2024.10.28 00:05:32   failed market sell 0.49 US500.cash, close #1774 buy 0.49 US500.cash 5628.35 [Market closed]
- `2026-11-01_0342_AurumFunded_grz2_on`: NR	0	02:53:32.250	Core 1	2024.10.28 00:05:32   AurumFunded: close on US500.cash failed, retcode 10018 (market closed)
