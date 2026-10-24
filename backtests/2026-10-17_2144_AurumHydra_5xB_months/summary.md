# j8b: AurumHydra 5x month series, part 2 of 3 (2025.08 to 2026.02)

Preset AurumHydra_5x_month_FTMO.set, XAUUSD M15, a fresh 10,000 deposit each month, 1:500, real ticks.
Collected by the tester operator on 2026-10-17 22:30 (series ran 21:44 to about 22:30).

| Month | Multiple | Trades | Equity DD % |
|---|---|---|---|
| 2025.08 | 1.12x | 65 | 30.7 |
| 2025.09 | 2.43x | 47 | 19.1 |
| 2025.10 | 1.15x | 67 | 78.5 |
| 2025.11 | 1.54x | 70 | 48.3 |
| 2025.12 | 1.37x | 39 | 43.6 |
| 2026.01 | 5.00x | 46 | 16.8 |
| 2026.02 | 1.33x | 52 | 23.9 |

- 5x reached in 1 of 7 months (2026.01, 5.001x); median multiple 1.37x; 0 of 7 months below 0.5x; months with
  margin refusals 0.
- Against `expect` (about 9/21 at 5x over the three parts): with part 1 (0/7) the running count is 1 of 14. The
  final call waits for j8c.
- Check from `expect`: 2026.01 tester.ini has InpGold=XAUUSD, Deposit=10000, Leverage=500.
