# j4 AurumHydra 5x, legs on (tag 5x_on)

XAUUSD M15, preset AurumHydra_5x_month.set, deposit 100, leverage 500, real ticks (99%), from 2024.01.01.
Overrides: InpGold=XAUUSD, InpYen=USDJPY, InpEuro=EURUSD, InpGridSymbol=AUDCAD, plus compare_set InpBreakRiskPct=0.5, InpNoiseMult=0.275.

- Goal round of 2024.01.01 ended on 2024.02.01 (one month, then the EA closes everything and stops).
- Net +14.79 (+14.79%), final balance 114.79, equity drawdown 33.71 (25.84%), balance drawdown 13.81%.
- 49 trades, win rate 55.10%, profit factor 1.32, Sharpe 2.19, recovery 0.44.
- Worst day 2024-01-23: -8.5%.
- By symbol: USDJPY +11.99, EURUSD +6.82, AUDCAD -4.02.
- By month: 2024-01 +15.72, 2024-02 -0.93.
- Log: "SP500.r / NAS100.r not available, the noise leg leaves it out" (the noise leg's own indices are the broker's names, so only the USDJPY breakout leg ran); "balance too small for the minimum lot" lines on EURUSD, USDJPY, XAUUSD and the grid. No "failed" lines.

## Legs on vs legs off

| | off | on | gap |
|---|---|---|---|
| Return | +9.47% | +14.79% | +5.32 points (about 1.56x) |
| Equity drawdown | 14.98% | 25.84% | +10.86 points |
| Profit factor | 1.58 | 1.32 | -0.26 |
| Trades | 32 | 49 | +17 |
| Worst day | -5.87% | -8.5% | |
| Return per unit of drawdown | 0.63 | 0.57 | |

Expectation (README test 3): legs on about a tenth more profit and a little more drawdown. Result: over half again the profit and drawdown up by about 11 points; return per unit of drawdown is slightly worse. The run is one month at 100 deposit, so minimum-lot rounding dominates. Judging is the orchestrator's.
