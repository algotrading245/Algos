# j4 AurumHydra 5x, legs off (tag 5x_off)

XAUUSD M15, preset AurumHydra_5x_month.set, deposit 100, leverage 500, real ticks (99%), from 2024.01.01.
Overrides: InpGold=XAUUSD, InpYen=USDJPY, InpEuro=EURUSD, InpGridSymbol=AUDCAD.

- Goal round of 2024.01.01 ended on 2024.02.01 (the round is one month, then the EA closes everything and stops).
- Net +9.47 (+9.47%), final balance 109.47, equity peak-to-trough drawdown 16.93 (14.98%), balance drawdown 7.81%.
- 32 trades, win rate 53.12%, profit factor 1.58, Sharpe 2.3, recovery 0.56.
- Worst day 2024-01-23: -5.87%.
- By symbol: EURUSD +11.43, AUDCAD -0.77, USDJPY -1.19.
- By month: 2024-01 +10.40, 2024-02 -0.93.
- Log: "balance too small for the minimum lot at leverage 208.34, no dip unit" appears (grid at 100 deposit); no "not found" or failed lines seen.

Expectation (README test 3): this is the legs-off base; the legs-on run follows (tag 5x_on) for the comparison.
Return per unit of drawdown, legs off: 9.47 / 14.98 = 0.63.
