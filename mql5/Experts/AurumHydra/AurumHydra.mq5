//+------------------------------------------------------------------+
//| AurumHydra.mq5 - eight kinds of trading on one account.          |
//| Day trades and scalps: the four legs of AurumQuartet with its    |
//| sizing model: gold dip (4 hours), bell fade (10 minutes),        |
//| Tokyo fixing (90 minutes), EUR/USD midday (90 minutes).          |
//| Grid: fades AUD/CAD away from its 5-day average, hourly closes.  |
//| Level k sits k steps from the average, one step = one day's      |
//| volatility. A level opens when reached and closes one step back. |
//| Beyond levels + 1 steps the whole grid is closed at a loss and   |
//| waits until the price is back within half a step of the average. |
//| Backtest 2010-2026 on AUD/CAD itself: Sharpe 1.0 to 2017 and 0.9 |
//| since. 19 other pairs, gold, silver and their ratio did not work.|
//| Martingale: InpGridMult sizes each further grid level as a       |
//| multiple of the one before, at the same loss at the stop-out; in |
//| the backtest 1.3 to 1.6 was about neutral. InpLossMult scales    |
//| a trade's size for each loss in a row, three at most. Above 1 it |
//| lowered every leg's result. 0.67 cut the worst drawdown of the   |
//| four day-trading legs from 23% to 17% at the same Sharpe ratio,  |
//| so it is the default; InpLossNorm 0.80 is the average of that    |
//| factor and keeps the average size where it was.                  |
//| Hold: long gold for weeks to months while the 20, 60, 120 and    |
//| 250-day returns are positive, sized to a volatility target. Weak |
//| before 2018, and the broker's swap on long gold is not tested.   |
//| Fast: a 2-minute fade of the last 5 minutes into the bell        |
//| (AurumSnap), off by default: it overlaps the bell leg and needs  |
//| an entry within 5 seconds at a spread near 0.1.                  |
//| Fix: on the last weekday of a month five dollar pairs are traded |
//| into the London 4pm fix, against the dollar when the stock index |
//| is up on the month and with it when down, and the other way      |
//| round for an hour after the fix. 12 days a year. The size grows  |
//| with the stock move: full at 3%, at most double (chosen on the   |
//| same data; every value tried helped). Sharpe 1.3 at a cost of    |
//| 1.2 basis points a round trip, 1.1 at 2.5; the broker's cost on  |
//| these pairs is not checked. USD/JPY went the other way and is    |
//| left out, also chosen on the same data. The trade after the fix  |
//| is worth nothing when entered minutes late. Off when the stock   |
//| index symbol is not found.                                       |
//| Three yen crosses (AUD/JPY, CAD/JPY, GBP/JPY) are traded on the  |
//| same day before the fix only: bought when the stock index is up  |
//| on the month, sold when down. Sharpe 1.2 in both halves at 2     |
//| basis points, 1.1 at 3.5; about 4% a year. Their cost at the     |
//| broker is not checked and they are half correlated with the      |
//| dollar pairs. EUR/JPY and EUR/GBP were tried and left out.       |
//| Fall: on every other weekday, when the stock index has lost more |
//| than 3% over the five trading days to yesterday's close, the     |
//| dollar is bought on the same five pairs an hour before the fix   |
//| and sold at it. About 15 days a year, most of them in sell-offs: |
//| 2020 alone made a quarter of the result. Sharpe 0.9 before 2018  |
//| and 1.1 after at 1.2 basis points; the hour was chosen on the    |
//| same data (30 to 120 minutes and falls of 2 to 4% all helped).   |
//| Morning: on a weekday after the stock index moved 1.5% or more   |
//| in a day, EUR/JPY, GBP/JPY and CAD/JPY are traded against that   |
//| move (sold after a rise, bought after a fall) from an hour before|
//| the 9:55 Tokyo fixing until an hour after it. About 28 days a    |
//| year, 4% a year, Sharpe 0.8 before 2018 and 1.1 after at 1.5 to  |
//| 1.8 basis points, 0.6 at double that; 0.7 since 2022. Pairs,     |
//| threshold and window were chosen on the same data. Unrelated to  |
//| every other module.                                              |
//| After: on the first weekday after a US federal holiday the dollar|
//| is bought on the five pairs of the fix leg from 9:05 to 15:00    |
//| server time (the London morning). About 10 days a year, 6 basis  |
//| points a trade after costs, Sharpe 0.9 before 2018 and 1.1 after |
//| at 0.8 to 1 basis point, 0.9 at double that or with an entry 25  |
//| minutes late. Nothing on ordinary Tuesdays or two days after.    |
//| Found among 300 holiday tests, so it may be chance.              |
//| At the default sizes the backtest of all modules gives about 73% |
//| a year with a worst drawdown of 14%. InpSizeMult scales all of   |
//| it. Resampled 2018-2026 results: at 4 the median year is 16x and |
//| 1 year in 170 halves the account on the way; at 8 the median is  |
//| 110x, 1 year in 10 halves it. No size makes 10x in a month       |
//| likely.                                                          |
//| Goal: with InpGoalMult above 1 the size is no longer fixed. It is|
//| the one that gives the best chance of multiplying the equity by  |
//| InpGoalMult within InpGoalDays weekdays: with x = equity / goal  |
//| and z the normal quantile of x,                                  |
//|    size = pdf(z) / (x * sqrt(days left)) / daily swing at size 1,|
//| never above InpGoalCap. It is large while the goal is far and the|
//| days are few and falls to nothing as the goal comes near. The    |
//| best chance any rule can have is cdf(quantile(1/goal) + Sharpe * |
//| sqrt(years)): 38% for 10x in a month at the backtest's Sharpe.   |
//| With the cap at 20 the resampled 2018-2026 results give 10x in a |
//| month 9% of the time, in three months 41%, in six 72%, in a year |
//| 95%, and a month that misses leaves 1.5x the stake in the middle |
//| case and less than a tenth of it 6% of the time.                 |
//| Solved exactly for daily steps (dynamic programming on the real  |
//| day results), a goal one month away is best chased at the cap    |
//| from the first day until it is reached: InpGoalBold. The limit is|
//| then the broker's margin. With InpGoalBold, InpGoalCap 50 and    |
//| InpMarginPct 30 the resampled 2018-2026 results give 3x in a     |
//| month 52% of the time, 5x 38%, 10x 24%; a 5x round ends below a  |
//| tenth of the stake 26% of the time and below the stake 44%.      |
//| InpGoalScale multiplies the goal size before the cap. The size is|
//| worked out again from the equity before every entry; resampled   |
//| that way on 2018-2026, 5x in a month came 38% of the time at     |
//| scale 1.5 and 40% at 2.5 with the cap at 30 (15% of rounds end   |
//| below a tenth of the stake), 44% and 47% with the cap at 50      |
//| (36%), against 29% and 33% at scale 1. Each 0.03 of a leg's daily|
//| swing lost to slippage costs about 5 points.                     |
//| InpMonthEndBoost (1 = off): the bell, Tokyo and both fix legs    |
//| earn a quarter of the book's profit on the last weekday of a     |
//| month; at 2 on that day, 2010-2026 calendar rounds started 1-3   |
//| weekdays before it reach 5x in 54-56% of rounds against 49% if   |
//| the doubled legs get their full size, about 50% against 47% with |
//| the 1:500 margin cap of an order estimated.                      |
//| InpBrakePct (off by default) multiplies every size by            |
//| InpBrakeCut while equity is that far under its peak: at 25% and  |
//| 0.5, size 6 resampled like size 5 with the halving risk of size  |
//| 4.5 (measured before the Fall leg was added). The peak is        |
//| counted from the moment the EA starts.                           |
//| Breakout (USD/JPY London range, InpBreakRiskPct 0.125) and the   |
//| noise-area index legs (S&P 500 and Nasdaq, InpNoiseMult 0.275)   |
//| are on by default since v1.34. The legs, sizing and handlers are |
//| in Include/Aurum (Inputs.mqh, Legs.mqh), shared with AurumFunded; |
//| this file only sets the defaults and the hooks.                  |
//| InpTarget (3, 4 or 5; 0 = off) aims each round at that multiple  |
//| with the goal scale that gave it the best odds in                |
//| tools/target_odds.py (2.5); it overrides InpGoalMult and         |
//| InpGoalScale. Presets: AurumHydra_target3x/4x/5x_FTMO.set.       |
//| Attach to a gold chart on a hedging account, server clock = New  |
//| York + 7 hours, raw spread. The grid has no stop at the broker:  |
//| its stop-out needs the terminal running.                         |
//| Backtest: tools/backtest_hydra.py, tools/backtest_quartet.py     |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.34"
#define AURUM_NAME "AurumHydra"
#include <Math\Stat\Normal.mqh>
#include <Trade\Trade.mqh>
#include <Aurum\Inputs.mqh>
#include <Aurum\Legs.mqh>

// No guard: full size, no broker stop on gold, every tick traded.
double AurumSize() { return(1.0); }
bool AurumGoldStop(double lots,double ask,double bid,double &sl) { sl=0.0; return(true); }
bool AurumGuard() { return(true); }
bool AurumInputsBad() { return(false); }
