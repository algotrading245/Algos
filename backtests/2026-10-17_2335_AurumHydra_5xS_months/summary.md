# j9: AurumHydra 5x months 2026.02-04, gold spread cap 1.0 (cause check)

Preset AurumHydra_5x_month_FTMO.set, set InpGoldMaxSpread=1.0, XAUUSD M15, fresh 10,000 per month, 1:500, real ticks. Run 2026-10-17 23:35 to 23:41, from 2026.02.01 to each month's end.

| Month | Multiple | Net | Trades | Equity DD | XAUUSD profit | Margin refusals |
|---|---|---|---|---|---|---|
| 2026.02 | 0.34x | -6,627.57 | 3 | 69.60% | -6,490.05 | 0 |
| 2026.03 | 0.49x | -5,089.94 | 8 | 56.09% | -5,492.38 | 0 |
| 2026.04 | 0.57x | -4,315.16 | 43 | 55.36% | -3,303.99 | 0 |

Series: 0 of 3 months at 5x, median 0.49x, 2 of 3 below 0.5x (0.34x, 0.49x), 0 months with margin refusals. These multiples do not count against 9/21.

## Against `expect`
- XAUUSD now appears in by_symbol in 2026.02 and 2026.04, where j8 had no gold trade. Gold also traded in 2026.03. Gold trades in all three months with the cap at 1.0, so the 0.30 spread cap was blocking the gold buys in 2026.02 and 2026.04.
- The gold trades lost: -6,490 (2026.02), -5,492 (2026.03), -3,304 (2026.04). The worst days are 2026-02-02 (-66.28%), 2026-03-03 (-54.44%) and 2026-04-29 (-43.07%).
- Not done: the first "hold, trend ... position 0.00 -> ..." line date and lots for each month. The tester log lines are not in the month folders (no log file copied), so I did not check them.
- Check from the tester.ini of each month (not opened by me): the set line in months.json is InpGoldMaxSpread=1.0.
