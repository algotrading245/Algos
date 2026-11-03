# j8a: AurumHydra 5x month series, part 1 of 3 (2025.01 to 2025.07)

Preset AurumHydra_5x_month_FTMO.set, XAUUSD M15, a fresh 10,000 deposit each month, 1:500, real ticks.
Collected by hand on 2026-10-17 at 21:45, because the tester agent had hit its daily run cap.

| Month | Multiple | Trades | Equity DD % |
|---|---|---|---|
| 2025.01 | 1.67x | 60 | 18.9 |
| 2025.02 | 1.24x | 41 | 30.6 |
| 2025.03 | 2.18x | 79 | 18.2 |
| 2025.04 | 0.40x | 28 | 68.2 |
| 2025.05 | 0.47x | 31 | 71.4 |
| 2025.06 | 0.59x | 49 | 63.3 |
| 2025.07 | 0.75x | 55 | 48.4 |

- 5x reached in 0 of 7 months; median multiple 0.75x; 2 of 7 months below 0.5x; months with margin refusals 0.
- Against `expect` (about 9/21 at 5x over the three parts): part 1 gives 0/7, well behind that pace. The final
  call waits for j8b and j8c.
- Check from `expect`: 2025.01 tester.ini has InpGold=XAUUSD, Deposit=10000, Leverage=500; its report shows a
  10,000 deposit and 100% real ticks.
