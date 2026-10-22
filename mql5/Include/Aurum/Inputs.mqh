//+------------------------------------------------------------------+
//| Aurum/Inputs.mqh - the inputs of the legs shared by AurumHydra   |
//| and AurumFunded. A wrapper sets the AURUM_* macros below before  |
//| including this file to change a default (symbols of its broker, |
//| sizes); unset macros keep AurumHydra's defaults.                 |
//+------------------------------------------------------------------+
#ifndef AURUM_NAME
#define AURUM_NAME "AurumHydra"
#endif
#ifndef AURUM_GOLD
#define AURUM_GOLD "XAUUSD.pc"
#endif
#ifndef AURUM_YEN
#define AURUM_YEN "USDJPY.pc"
#endif
#ifndef AURUM_EURO
#define AURUM_EURO "EURUSD.pc"
#endif
#ifndef AURUM_GRIDSYM
#define AURUM_GRIDSYM "AUDCAD.pc"
#endif
#ifndef AURUM_SIZEMULT
#define AURUM_SIZEMULT 1.0
#endif
#ifndef AURUM_GRIDRISK
#define AURUM_GRIDRISK 3.5
#endif
#ifndef AURUM_HOLDVOL
#define AURUM_HOLDVOL 10.7
#endif
#ifndef AURUM_STOCKS
#define AURUM_STOCKS "SP500.r"
#endif
#ifndef AURUM_POUND
#define AURUM_POUND "GBPUSD.pc"
#endif
#ifndef AURUM_AUSSIE
#define AURUM_AUSSIE "AUDUSD.pc"
#endif
#ifndef AURUM_LOONIE
#define AURUM_LOONIE "USDCAD.pc"
#endif
#ifndef AURUM_SWISSY
#define AURUM_SWISSY "USDCHF.pc"
#endif
#ifndef AURUM_CROSS1
#define AURUM_CROSS1 "AUDJPY.pc"
#endif
#ifndef AURUM_CROSS2
#define AURUM_CROSS2 "CADJPY.pc"
#endif
#ifndef AURUM_CROSS3
#define AURUM_CROSS3 "GBPJPY.pc"
#endif
#ifndef AURUM_MORN1
#define AURUM_MORN1 "EURJPY.pc"
#endif
#ifndef AURUM_MORN2
#define AURUM_MORN2 "GBPJPY.pc"
#endif
#ifndef AURUM_MORN3
#define AURUM_MORN3 "CADJPY.pc"
#endif
#ifndef AURUM_BREAKRISK
#define AURUM_BREAKRISK 0.125
#endif
#ifndef AURUM_NOISEMULT
#define AURUM_NOISEMULT 0.275
#endif
#ifndef AURUM_NASDAQ
#define AURUM_NASDAQ "NAS100.r"
#endif
#ifndef AURUM_MAXDD
#define AURUM_MAXDD 35.0
#endif
#ifndef AURUM_MAGIC
#define AURUM_MAGIC 245020
#endif

input group "Symbols"
input string InpGold            = AURUM_GOLD; // Gold
input string InpYen             = AURUM_YEN; // USD/JPY
input string InpEuro            = AURUM_EURO; // EUR/USD
input string InpGridSymbol      = AURUM_GRIDSYM; // AUD/CAD (grid)

input group "Overall size"
input double InpSizeMult        = AURUM_SIZEMULT;   // Every size below is multiplied by this
input double InpBrakePct        = 0.0;   // Drawdown brake: equity this far under its peak, % (0 = off)
input double InpBrakeCut        = 0.5;   // ... multiplies every size by this until the drawdown is smaller
input double InpBrake2Pct       = 0.0;   // Second brake: equity this far under its peak, % (0 = off; plan: 20 with InpBrakePct 10)
input double InpBrake2Cut       = 0.25;  // ... multiplies every size by this instead of InpBrakeCut
input double InpAcctVolPct      = 0.0;   // Account vol target: size x this / annual swing of the daily closed P&L, % (0 = off; plan: 20)
input int    InpAcctVolDays     = 63;    // ... swing measured over this many weekdays (needs 20 with a trade)
input double InpAcctVolMax      = 2.0;   // ... largest multiple the vol target may apply
input double InpDayLossPct      = 0.0;   // Day-loss guard: equity this far under the day's start, %, closes all until the next day (0 = off)

input group "Goal (the size with the best chance of multiplying the equity by a deadline)"
input int    InpTarget          = 0;     // 3, 4 or 5: aim for this multiple each round at its best tested scale (0 = InpGoalMult, InpGoalScale)
input double InpGoalMult        = 0.0;   // Multiply the equity by this (0 = off, InpSizeMult is used)
input int    InpGoalDays        = 21;    // ... within this many weekdays
input double InpGoalCap         = 20.0;  // Largest size multiple the goal may ask for
input bool   InpGoalBold        = false; // Trade at InpGoalCap from the first day until the goal is reached
input double InpGoalScale       = 1.0;   // Multiplies the goal size before the cap (2.5 tested best for 5x in a month)
input double InpGoalDayVolPct   = 1.56;  // Daily swing of the account at size 1, %
input bool   InpGoalRepeat      = true;  // When a round ends, start the next from the equity of that moment
input bool   InpGoalStop        = true;  // Without InpGoalRepeat: when the round ends, close everything and stop trading
input int    InpGoalRound       = 1;     // Number of the round; change it to start a new round after one has ended
input double InpMonthEndBoost   = 1.0;   // On the last weekday of a month the bell, Tokyo and both fix legs trade this multiple of their size

input group "Size of each leg (0 switches the leg off)"
input double InpVolTargetPct    = 46.5;  // Gold: annual gold volatility one unit is scaled to, %
input double InpMaxLeverage     = 6.2;   // Gold: maximum notional of one unit, multiple of equity
input double InpBellRiskPct     = 2.7;   // Closing bell: loss at the stop, % of balance
input double InpTokyoRiskPct    = 2.0;   // Tokyo fixing: loss at the stop, % of balance
input double InpMeridianRiskPct = 1.0;   // Midday: loss at the stop, % of balance

input group "Gold session leg (server time)"
input int    InpEntryHHMM       = 105;   // Buy from this time, HHMM
input int    InpEntryMinutes    = 20;    // Stop trying to enter this many minutes later
input int    InpExitHHMM        = 900;   // Close at this time, HHMM
input bool   InpUseSession      = false; // Hold a unit through the whole session
input bool   InpUseDip          = true;  // Buy a unit after a sharp M15 fall
input double InpDipSigma        = 3.0;   // Fall of the M15 bar, standard deviations
input int    InpDipWindow       = 96;    // M15 returns used for the standard deviation
input int    InpDipFromHHMM     = 115;   // Earliest open time of the falling bar, HHMM
input int    InpDipToHHMM       = 745;   // Latest open time of the falling bar, HHMM
input int    InpDipHoldBars     = 16;    // Holding time of the dip unit, M15 bars
input int    InpVolSpan         = 30;    // Span of the exponentially weighted daily volatility

input group "Closing bell leg (23:00 server time)"
input int    InpBellLookMin     = 15;    // Move is measured over this many minutes (multiple of 5)
input double InpBellK           = 1.5;   // Trade when the move is at least this many average moves
input int    InpBellHoldMin     = 10;    // Holding time, minutes
input int    InpBellEntrySec    = 20;    // No entry later than this after the bell, seconds

input group "Tokyo fixing leg"
input int    InpTokyoHoldMin    = 90;    // Holding time after 9:55 Tokyo, minutes (multiple of 5)
input bool   InpGotobi          = true;  // Only on settlement days (5th, 10th, 15th, ...)
input int    InpTokyoEntrySec   = 20;    // No entry later than this after the fixing, seconds

input group "Midday leg (London time)"
input int    InpStartMin        = 690;   // Entry, minutes after midnight London time (multiple of 5)
input int    InpEndMin          = 780;   // Exit, minutes after midnight London time (multiple of 5)
input int    InpMeridianEntrySec= 60;    // No entry later than this after the start, seconds

input group "Grid (hourly closes of the grid symbol)"
input double InpGridRiskPct     = AURUM_GRIDRISK;   // Loss of the whole grid at its stop-out, % of balance (0 = off)
input int    InpGridLevels      = 4;     // Levels on each side of the average (1 to 8)
input int    InpGridMaDays      = 5;     // Days in the average the grid is centred on
input double InpGridStep        = 1.0;   // Distance between levels, daily volatilities
input int    InpGridVolDays     = 40;    // Days in the volatility estimate
input double InpGridMult        = 1.0;   // Size of each further level, multiple of the one before (martingale above 1)
input double InpGridPanic       = 1.0;   // Between hourly closes: stop out this many steps beyond the stop-out level (0 = off)
input int    InpGridMaxSpread   = 30;    // No new level while spread is above this, points

input group "Gold hold (weeks to months)"
input double InpHoldVolPct      = AURUM_HOLDVOL;  // Annual volatility the position is scaled to, % (0 = off)
input double InpHoldMaxLeverage = 3.0;   // Maximum notional, multiple of equity
input double InpHoldBand        = 0.25;  // Resize only when the size is off by more than this fraction
input int    InpHoldHHMM        = 105;   // Checked once a day from this time, HHMM

input group "Month-end fix (last weekday of the month, London 4pm)"
input double InpFixRiskPct      = 0.5;   // Loss of one pair at its stop, % of balance (0 = off)
input double InpFixScalePct     = 3.0;   // Stock move of the month at which a pair risks that much, % (0 = same size every month)
input double InpFixCap          = 2.0;   // Largest multiple of that risk after a large stock move
input string InpStocks          = AURUM_STOCKS; // Stock index the month's direction is read from
input string InpPound           = AURUM_POUND; // GBP/USD
input string InpAussie          = AURUM_AUSSIE; // AUD/USD
input string InpLoonie          = AURUM_LOONIE; // USD/CAD
input string InpSwissy          = AURUM_SWISSY; // USD/CHF
input int    InpFixBeforeMin    = 120;   // Enter this many minutes before the fix (multiple of 5)
input int    InpFixAfterMin     = 60;    // Hold the opposite trade this many minutes after the fix (multiple of 5, 0 = none)
input int    InpFixEntrySec     = 60;    // No entry later than this after a window opens, seconds
input double InpFixCrossRiskPct = 0.5;   // Yen crosses before the fix: loss of one at its stop, % of balance (0 = off)
input string InpFixCross1       = AURUM_CROSS1; // AUD/JPY
input string InpFixCross2       = AURUM_CROSS2; // CAD/JPY
input string InpFixCross3       = AURUM_CROSS3; // GBP/JPY
input int    InpCrossMaxSpread  = 30;    // No yen-cross entry while spread is above this, points

input group "Stock-fall fix (every other weekday, London 4pm, same pairs and stock index)"
input double InpFallRiskPct     = 0.5;   // Loss of one pair at its stop, % of balance (0 = off)
input double InpFallPct         = 3.0;   // Buy the dollar after the stock index lost more than this, %
input int    InpFallDays        = 5;     // ... over this many trading days to yesterday's close
input int    InpFallBeforeMin   = 60;    // Enter this many minutes before the fix (multiple of 5)

input group "Tokyo morning (yen crosses against a large move of the stock index)"
input double InpMornRiskPct     = 0.5;   // Loss of one pair at its stop, % of balance (0 = off)
input double InpMornPct         = 1.5;   // Trade after the stock index moved at least this in a day, %
input int    InpMornBeforeMin   = 60;    // Enter this many minutes before 9:55 Tokyo (multiple of 5)
input int    InpMornAfterMin    = 60;    // Close this many minutes after 9:55 Tokyo (multiple of 5)
input string InpMorn1           = AURUM_MORN1; // EUR/JPY
input string InpMorn2           = AURUM_MORN2; // GBP/JPY
input string InpMorn3           = AURUM_MORN3; // CAD/JPY

input group "After a US holiday (the five dollar pairs of the fix leg, server time)"
input double InpAfterRiskPct    = 1.0;   // Loss of one pair at its stop, % of balance (0 = off)
input int    InpAfterHHMM       = 905;   // Buy the dollar at this time, HHMM (minutes a multiple of 5)
input int    InpAfterExitHHMM   = 1500;  // Close at this time, HHMM (minutes a multiple of 5)
input int    InpAfterEntrySec   = 300;   // No entry later than this after the start, seconds

input group "USD/JPY London breakout (server time; research/london_breakout.py)"
input double InpBreakRiskPct    = AURUM_BREAKRISK;   // Loss of each side at its stop, % of balance (0 = off; 0.125 = a quarter of the fix leg)
input int    InpBreakFromHHMM   = 100;   // USD/JPY range from this time, HHMM
input int    InpBreakToHHMM     = 900;   // ... to this time, HHMM
input int    InpBreakStartHHMM  = 1000;  // Buy above the range high / sell below the low from this time, HHMM
input int    InpBreakExitHHMM   = 1800;  // Close both sides at this time, HHMM
input int    InpBreakFilterDays = 60;    // Days in the average range
input double InpBreakMinRange   = 0.25;  // No breakout when the range is below this multiple of its average
input double InpBreakMaxRange   = 3.0;   // ... or above this one

input group "Noise-area index momentum (New York session; research/noise_area_index.py)"
input double InpNoiseMult       = AURUM_NOISEMULT;   // Notional per index, multiple of min(4, 2% / daily volatility) x equity (0 = off; 0.275 tested)
input string InpNasdaq          = AURUM_NASDAQ; // Nasdaq 100 (the S&P 500 is InpStocks; check the broker's name)
input double InpNoiseBandSpx    = 1.5;   // Band width on the S&P 500, multiple of the average move
input double InpNoiseBandNdx    = 1.0;   // Band width on the Nasdaq
input double InpNoiseMaxSpreadBp= 3.0;   // No entry while the spread is above this, basis points of price

input group "Overnight drift (stock index after a weak US cash session, server time, no stop)"
input double InpDriftLev        = 0.0;   // Index position per unit of size, x equity (0 = off)
input double InpDriftMaxLev     = 150.0; // Largest index position, x equity
input int    InpDriftHHMM       = 100;   // Buy at this time, HHMM
input int    InpDriftExitHHMM   = 1000;  // Close at this time, HHMM
input int    InpDriftEntrySec   = 600;   // No entry later than this after the start, seconds
input double InpDriftMaxSpread  = 1.5;   // No entry while the index spread is above this, price units

input group "Fast leg (2-minute fade at the bell)"
input double InpSnapRiskPct     = 0.0;   // Loss at the stop, % of balance (0 = off)
input int    InpSnapLookMin     = 5;     // Move is measured over this many minutes (multiple of 5)
input double InpSnapK           = 1.5;   // Trade when the move is at least this many average moves
input int    InpSnapHoldSec     = 120;   // Holding time, seconds
input int    InpSnapEntrySec    = 5;     // No entry later than this after the bell, seconds

input group "Progression after losses"
input double InpLossMult        = 0.67;  // Size x this for each loss in a row, up to 3 (1 = off, below 1 cuts, above 1 martingale)
input double InpLossNorm        = 0.80;  // ... divided by this, the average of that factor (1 = no rescale)

input group "Stops and risk guard"
input int    InpDays            = 60;    // Days in the average move of each window
input double InpStopMult        = 3.0;   // Stop distance of the three stop legs, average moves
input double InpMarginPct       = 50.0;  // Margin cap of one order, % of free margin
input double InpGoldMaxSpread   = 0.30;  // No gold entry while spread is above this, price units
input int    InpFxMaxSpread     = 15;    // No currency entry while spread is above this, points
input double InpMaxDrawdownPct  = AURUM_MAXDD;  // Close everything and stop after this equity drawdown from the peak, %

input group "Sizing model"
input bool   InpUseModel        = true;  // Scale each trade by the model's score
input double InpModelTilt       = 0.5;   // Size runs from 1 - tilt to 1 + tilt times the leg's size (0 to 1)

input group "Execution"
input long   InpMagic           = AURUM_MAGIC; // First magic number: +0 session, +1 dip, +2 bell, +3 Tokyo, +4 midday, +5 fast, +6 hold, +11.. grid, +20 and +21 fix, +22 stock-fall fix, +23 Tokyo morning, +24 after a holiday, +25 overnight drift, +26 and +27 USD/JPY breakout, +28 and +29 noise-area index legs
input int    InpGoldDeviation   = 30;     // Max slippage on gold, points
input int    InpFxDeviation     = 10;     // Max slippage on the currency pairs, points
