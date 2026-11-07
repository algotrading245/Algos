# AurumFunded, FTMO phase 1 preset, Strategy Tester (FTMO-Demo, build 6230)

Run by the owner on 2026-10-15: XAUUSD M15, 2024-01-01 to 2026-10-14, every tick based on real ticks (99% real
ticks), random delay, 10,000 USD, 1:33, inputs of `AurumFunded_FTMO_phase1.set` (size 0.5, target 10%, day stop 3%,
final stop 8.5%). The phase preset stops the test at the target.

Result: **phase passed on 2024-10-25**, +1,000.17 (10.0%) after 199 trading days with a deal, 534 trades.
Equity drawdown at most 4.70% (balance 4.37%); worst day -1.6% (2024-07-25); the 3% day stop was never hit.
Commission 489 USD (FTMO charges 2.50 USD a lot a side on currencies, 0.46 bp a round trip on EUR/USD; 1.61 a lot
a side on gold), no swap (nothing held overnight).

By leg, % of the starting balance, against the Python model (`marketdata/hydra_legs_daily.csv.gz` x 0.5) on the
same dates, 2024-01-01 to 2024-10-25:

| Leg | Trades | Tester | Model |
|---|---|---|---|
| dip | 10 | +2.53 | quartet +10.23 (dip, bell, Tokyo, midday) |
| bell | 43 | +0.72 | |
| Tokyo | 54 | -0.05 | |
| midday | 198 | +1.30 | |
| fix + after fix (incl. yen crosses) | 104 | +2.70 | fix +3.10, cross -0.16 |
| stock fall | 40 | -1.05 | -0.80 |
| morning | 45 | +0.42 | +0.13 |
| after holiday | 40 | +3.44 | +3.41 |
| total | 534 | +10.00 | +15.92 (model reached 10% on 2024-06-28) |

The dip entries fall on the model's minutes (2024-01-29 01:45, 04-05 04:30, 04-23 04:45, 04-25 06:15, 05-24 05:30),
so the server clock and the gold leg agree with the model. The month-end, holiday, fall and morning legs agree too.
The bell, Tokyo and midday legs together earned +2.0% against a model share of about 7%; commission explains under
1% of that (FTMO's is below the 0.85 bp the model charges). Open: test those three legs alone, once with zero
latency and once with random delay, to see whether the gap is delay, spread at the entry minute or the period.
