//+------------------------------------------------------------------+
//| AurumFunded.mq5 - AurumHydra for a prop-firm account.            |
//| Passes a challenge and keeps the funded account: the trading is  |
//| that of AurumHydra v1.32 without its grid and its gold hold (off |
//| by default here), at half its size, under a rule guard.          |
//| Legs: gold session dip, bell fade, Tokyo fixing, EUR/USD midday, |
//| month-end fix (dollar pairs and yen crosses), stock-fall fix,    |
//| Tokyo morning, day after a US holiday. See AurumHydra.mq5 for    |
//| what each one does and how it tested.                            |
//| Guard, all in % of the initial balance:                          |
//| - Day stop: once equity is InpPropDayStopPct below the balance   |
//|   at the firm's day start, everything is closed and nothing is   |
//|   opened until the firm's next day.                              |
//| - Final stop: once equity is InpPropMaxStopPct below the initial |
//|   balance (or the highest day-start balance, if the firm's limit |
//|   trails), everything is closed and the EA halts for good.       |
//| - Target: once equity is InpPropTargetPct up and the minimum     |
//|   number of trading days is done, everything is closed and the   |
//|   EA halts. While days are missing it trades on at               |
//|   InpPropCoast times its size. 0 = no target (funded account).   |
//| - Cushion sizing: every size is multiplied by (equity - final    |
//|   stop) / InpPropRoomPct, at least InpPropMinSize and at most     |
//|   InpPropCap. With the room equal to the final stop (8.5) the    |
//|   size is 1 at the start, shrinks toward the final stop and grows|
//|   with profit up to 1.4x at +3.4%. On the path from buying the   |
//|   challenge to the first payout (tools/prop_sizing.py, 70% of the|
//|   backtested edge) the first payout came within 9 months 46% of  |
//|   the time against 37% with the old rule (room 6.5, cap 1),      |
//|   median 9.6 months against 10.6, and with half the edge and a   |
//|   pessimistic intraday stand-in no path failed against 7.8%.     |
//| - Fast sizing (InpPropFast, off by default): while equity is at  |
//|   or above the phase's start, size follows a table solved by     |
//|   dynamic programming for passing both phases within 9 months    |
//|   (tools/prop_dp.py); below the start the cushion rule sizes. On |
//|   the historical paths at 70% of the edge both phases passed     |
//|   within 9 months 67% of the time (cushion rule alone 57%),      |
//|   median 7.3 months (8.0), and no path failed, with half the edge|
//|   and pessimistic intraday dips none either. Switch it on only   |
//|   after live results confirm the edge.                           |
//| - Each gold unit carries a stop at the broker that loses         |
//|   InpGoldStopPct of equity, for when the terminal is down; every |
//|   other leg already has one.                                     |
//| - Clock: the times assume a server clock of New York + 7 hours.  |
//|   Live, a server clock that is not where it should be stops the  |
//|   day's trading. In the tester, which cannot measure the clock,  |
//|   InpEuClock says the server follows European summer time, and   |
//|   on the days the two differ (about three weeks a year) nothing  |
//|   is traded.                                                     |
//| Backtest of the leg set on daily results 2010-2026               |
//| (tools/backtest_prop.py; a day that dips and recovers is not     |
//| seen, so these are upper bounds): Sharpe 3.0, 2.7 before 2018    |
//| and 3.2 after. Two phases of 10% and 5% under a 5% daily and a   |
//| 10% static limit, started on every day: at size 0.5 all passed,  |
//| in 124 trading days in the middle case; with half the edge 94%   |
//| passed in 223 days, with a third 81%. Size 1.0: 97% in 65 days,  |
//| 71% with half the edge. A funded account at 0.5 was alive after  |
//| twelve months every time and paid 34% of its balance.            |
//| v1.04: the legs come from Include/Aurum, shared with AurumHydra. |
//| Breakout and noise-area index legs are on at half Hydra's size   |
//| (InpBreakRiskPct 0.0625, InpNoiseMult 0.1375).                   |
//| v1.05: logs the account leverage and 1-lot margins once a day.   |
//| v1.06: logs the day start, day stop and final stop once a firm   |
//| day (the trailing floor was not visible in any log).             |
//| v1.07: an order answered DONE with deal 0 counts as a fill (FTMO |
//| reports the deal moments later).                                 |
//| v1.08: no late breakout after an attach or restart: a side whose |
//| level was passed before the EA started is skipped that day.      |
//| v1.09: the grid sends no new level until the last one shows among|
//| the positions or 10 seconds pass (FTMO reports the deal moments  |
//| later).                                                          |
//| v1.10: risk layer, all off by default: a second drawdown brake   |
//| (InpBrake2Pct/Cut), an account vol target from the daily closed  |
//| P&L (InpAcctVolPct/Days/Max) and a day-loss guard that closes    |
//| all and pauses to the next day (InpDayLossPct, set it under      |
//| InpPropDayStopPct so it acts first).                             |
//| v1.12: the breakout rounds its lots to the nearest step, not     |
//| down: at 10k it is 1-3 steps and skipped its widest stops. At    |
//| most 2x its risk at one step, so a size cut (brake, coast, the   |
//| cushion floor) to under a step can round back up to one step.    |
//| v1.13: variance-premium leg (InpVrpMult, off by default, magic   |
//| +30 S&P 500 / +31 Nasdaq): Monday, VIX^2 minus realised variance |
//| in the top third of 252 days -> long 10 trading days, broker     |
//| stop, signal day kept in a global variable. Needs a VIX symbol.  |
//| v1.14: VRP fixes: hold counted in D1 bars, a signal on the exit  |
//| day extends, no US-holiday Monday, stale-VIX check.              |
//| v1.15: VRP leg: NYSE holiday list (Columbus and Veterans Day     |
//| Mondays trade), stale-VIX limit 3 weekdays, VIX from the broker  |
//| symbol or else the file vixcls.csv in the common Files folder    |
//| (InpVrpVixFile), source and VIX level logged each Monday.        |
//| v1.16: each closing deal of the EA's magics is printed live with |
//| its P/L, for tools/demo_check.py. The clock skip stays: the      |
//| tester skips the same days, so the demo matches the test.        |
//| (decision 2026-10-27)                                            |
//| v1.17: live, only the measured server clock stops a day; the     |
//| InpEuClock skip acts in the tester only, and is off by default.  |
//| FTMO's server stayed GMT+3 through Europe's 10-25 change, so the |
//| skip paused the demo for nothing (owner 2026-10-27). Live trades |
//| on the skipped days have no tester match.                        |
//| Defaults: FTMO 2-Step Challenge, Swing account (no news or       |
//| weekend rule, 1:30). Phase 2: InpPropTargetPct 5, InpPropRound 2.|
//| Funded: InpPropTargetPct 0, InpPropRound 3. The initial balance  |
//| and the day's start are kept in the terminal's global variables. |
//| Attach to a gold chart on a hedging account.                     |
//| Backtest: tools/backtest_prop.py, tools/backtest_hydra.py        |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.17"
#define AURUM_NAME "AurumFunded"
#define AURUM_GOLD "XAUUSD"
#define AURUM_YEN "USDJPY"
#define AURUM_EURO "EURUSD"
#define AURUM_GRIDSYM "AUDCAD"
#define AURUM_STOCKS "US500.cash"
#define AURUM_POUND "GBPUSD"
#define AURUM_AUSSIE "AUDUSD"
#define AURUM_LOONIE "USDCAD"
#define AURUM_SWISSY "USDCHF"
#define AURUM_CROSS1 "AUDJPY"
#define AURUM_CROSS2 "CADJPY"
#define AURUM_CROSS3 "GBPJPY"
#define AURUM_MORN1 "EURJPY"
#define AURUM_MORN2 "GBPJPY"
#define AURUM_MORN3 "CADJPY"
#define AURUM_NASDAQ "US100.cash"
#define AURUM_SIZEMULT 0.5
#define AURUM_GRIDRISK 0.0
#define AURUM_HOLDVOL 0.0
#define AURUM_MAXDD 0.0
#define AURUM_MAGIC 245100
#define AURUM_BREAKRISK 0.0625
#define AURUM_NOISEMULT 0.1375
#include <Math\Stat\Normal.mqh>
#include <Trade\Trade.mqh>

input group "Funded account rules (% of the initial balance)"
input double InpPropStart       = 0.0;   // Initial balance of the account (0 = the balance when the EA first starts)
input double InpPropTargetPct   = 10.0;  // Profit target of the phase (0 = none, funded account)
input int    InpPropMinDays     = 4;     // Trading days the firm asks for before the phase can end
input double InpPropDayStopPct  = 3.0;   // Day stop: close everything for the day at this loss (the firm's limit is 5)
input double InpPropMaxStopPct  = 8.5;   // Final stop: close everything and halt at this loss (the firm's limit is 10)
input bool   InpPropTrailing    = false; // The firm's maximum loss trails the highest day-start balance
input double InpPropLockPct     = 0.0;   // Lock: once equity is this far up, % of the initial balance, the final stop moves (0 = off; Instant Funding 5)
input double InpPropLockStopPct = 3.5;   // ... to this loss, % of the initial balance (Instant Funding's limit becomes 5)
input double InpPropFloatPct    = 0.0;   // Floating-loss stop: open positions this far in loss together, % of the initial balance, close all for the day (0 = off)
input double InpPropRoomPct     = 8.5;   // Cushion sizing: size x (equity - final stop) / this, % of the initial balance (0 = off)
input double InpPropMinSize     = 0.3;   // ... but not below this share
input double InpPropCap         = 1.4;   // ... and not above this multiple
input bool   InpPropFast        = false; // Fast sizing while in profit (tools/prop_dp.py); only once live results confirm the edge
input datetime InpPropFastStart = 0;     // ... day the challenge was bought, counts the 9 months (0 = the phase's start)
input int    InpPropFastDays    = 189;   // ... trading days in which both phases are aimed for
input double InpPropCoast       = 0.1;   // Size multiple while the target is reached and trading days are missing
input int    InpPropResetHHMM   = 100;   // The firm's day starts at this server time (FTMO: midnight CE(S)T = 01:00)
input bool   InpEuClock         = false; // Tester only: server clock follows European summer time (false = New York + 7 hours all year)
input double InpGoldStopPct     = 2.5;   // Broker stop of a gold unit: its loss in % of equity (0 = none)
input int    InpPropRound       = 1;     // Number of the phase; a new number starts a new count

#include <Aurum\Inputs.mqh>
#include <Aurum\Legs.mqh>

double   g_propStart=0.0;      // initial balance the limits are measured from
double   g_propDayBal=0.0;     // balance at the start of the firm's day
double   g_propPeak=0.0;       // highest day-start balance
bool     g_propLocked=false;   // equity has reached InpPropLockPct: the final stop is at InpPropLockStopPct
datetime g_propDay=0;          // the firm's day g_propDayBal belongs to
datetime g_propSince=0;        // when the phase was started
bool     g_propDayStop=false;  // the day stop was hit on g_propDay
bool     g_propCoast=false;    // the target is reached and trading days are missing
int      g_propClose=0;        // 1 final stop, 2 target: everything is being closed
datetime g_propNote=0;         // day on which the clock last reported a problem

string PropKey(string name)
  {
   return("AurumFunded."+IntegerToString(InpMagic)+".phase"+IntegerToString(InpPropRound)+"."+name);
  }

// Equity under which the final stop closes everything.
double PropFloor()
  {
   if(g_propLocked)
      return(g_propStart-g_propStart*InpPropLockStopPct/100.0);
   return((InpPropTrailing ? g_propPeak : g_propStart)-g_propStart*InpPropMaxStopPct/100.0);
  }

// Fast sizing (InpPropFast): size by 21-day block of days left (row 0 = the last block) and 0.5% step of equity
// from -8.5%, solved by tools/prop_dp.py (9-month deadline, a failure counts -3, sizes up to 1.0, 70% of the edge).
// Used only while equity is at or above the phase's start; below it the cushion rule sizes.
const double FAST_P1[9][38]=
  {
   {0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.40,0.60,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.40,0.50,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.70,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.50,0.60,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.85,0.60,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.50,0.60,0.70,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.85,0.70,0.60,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.50,0.60,0.70,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.85,0.70,0.50,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.50,0.60,0.60,0.70,0.70,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.70,0.60,0.50,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.40,0.50,0.60,0.60,0.70,0.70,0.70,0.70,0.85,0.85,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.85,0.70,0.70,0.60,0.40,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.40,0.50,0.50,0.60,0.60,0.60,0.70,0.70,0.70,0.70,0.70,0.85,1.00,1.00,0.85,0.85,0.85,1.00,1.00,0.85,0.85,0.85,0.85,0.85,0.85,0.70,0.70,0.60,0.40,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.40,0.40,0.50,0.50,0.60,0.60,0.60,0.70,0.70,0.70,0.70,0.70,0.70,0.70,0.85,0.85,0.85,0.70,0.70,0.85,0.85,0.70,0.70,0.70,0.70,0.70,0.70,0.60,0.40,0.20}
  };
const double FAST_P2[9][28]=
  {
   {0.20,0.20,0.20,0.20,0.20,0.30,0.50,0.70,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.60,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.30,0.50,0.60,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.85,0.70,0.50,0.30,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.50,0.60,0.70,0.70,0.70,0.70,0.85,0.85,0.85,0.85,0.85,0.85,0.70,0.70,0.70,0.60,0.60,0.50,0.40,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.40,0.50,0.50,0.60,0.60,0.60,0.60,0.70,0.70,0.70,0.60,0.60,0.60,0.60,0.50,0.50,0.40,0.40,0.30,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.40,0.40,0.40,0.50,0.50,0.50,0.50,0.60,0.60,0.60,0.60,0.50,0.50,0.50,0.40,0.40,0.40,0.30,0.20,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.40,0.40,0.40,0.40,0.50,0.50,0.50,0.50,0.50,0.50,0.50,0.40,0.40,0.40,0.40,0.30,0.30,0.20,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.30,0.30,0.20,0.20,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.30,0.30,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.30,0.30,0.30,0.20,0.20,0.20,0.20},
   {0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.20,0.30,0.30,0.30,0.30,0.40,0.40,0.40,0.40,0.40,0.40,0.40,0.30,0.30,0.30,0.30,0.20,0.20,0.20,0.20,0.20}
  };
// Instant Funding first payout (tools/prop_dp_instantfunding.py): size by 21-day block of the InpPropFastDays left
// (row 0 = the last block) and 0.5% step of equity from -8.5%; used while equity is at or above the start and the lock
// is not in (static -10% floor, payout at +5%). Solved for 42 days, 70% of the edge, a lost account counting -3.
const double FAST_IF[2][27]=
  {
   {1.00,0.20,0.20,0.20,0.20,0.40,0.50,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.60},
   {1.00,0.20,0.20,0.20,0.20,0.30,0.50,0.50,0.70,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,1.00,0.70,0.50,0.30}
  };

// Size the fast table asks for (absolute, as InpSizeMult), or -1 when it does not apply: not enabled, a funded
// account, or equity below the phase's start.
double FastSize()
  {
   if(!InpPropFast || g_propStart<=0 || (InpPropTargetPct<=0 && InpPropLockPct<=0))
      return(-1.0);
   double eq=(AccountInfoDouble(ACCOUNT_EQUITY)/g_propStart-1.0)*100.0;
   if(eq<0)
      return(-1.0);
   datetime from=(InpPropFastStart>0 ? InpPropFastStart : g_propSince);
   int left=InpPropFastDays-Weekdays(DayOf(from),DayOf(TimeCurrent()));
   if(InpPropTargetPct<=0)                     // instant account with a lock: until the lock, the FAST_IF table
     {
      if(g_propLocked)
         return(-1.0);
      int b=MathMax(0,MathMin(1,(MathMax(left,1)-1)/21));
      int c=(int)MathRound((MathMin(eq,4.5)+8.5)/0.5);
      return(FAST_IF[b][MathMax(0,MathMin(26,c))]);
     }
   bool first=(InpPropTargetPct>=10.0);
   int blk=MathMax(0,MathMin(8,(MathMax(left,1)-1)/21));
   int cols=(first ? 38 : 28);
   int k=(int)MathRound((MathMin(eq,0.5*(cols-1)-8.5)+8.5)/0.5);
   k=MathMax(0,MathMin(cols-1,k));
   return(first ? FAST_P1[blk][k] : FAST_P2[blk][k]);
  }

// Size multiple of the guard: the cushion above the final stop over InpPropRoomPct, between InpPropMinSize and
// InpPropCap, and InpPropCoast while only trading days are missing.
double PropSize()
  {
   double f=(g_propCoast ? InpPropCoast : 1.0);
   double fast=FastSize();
   if(fast>0 && InpSizeMult>0)
      return(f*fast/InpSizeMult);
   if(InpPropRoomPct>0 && g_propStart>0)
      f*=MathMax(InpPropMinSize,MathMin(InpPropCap,(AccountInfoDouble(ACCOUNT_EQUITY)-PropFloor())/(g_propStart*InpPropRoomPct/100.0)));
   return(f);
  }


// 1 while Europe is on summer time on 'day', else 0.
int EuSummer(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   return(day>=Sunday(s.year,3,-1) && day<Sunday(s.year,10,-1) ? 1 : 0);
  }

// False on a day the server clock is not New York + 7 hours: every leg would trade an hour off.
bool ClockOk()
  {
   datetime today=DayOf(TimeCurrent());
   string why="";
   if(MQLInfoInteger(MQL_TESTER))
     {
      if(InpEuClock && EuSummer(today)!=UsSummer(today))
         why="European and US summer time differ";
     }
   else
     {
      double hours=(double)(TimeTradeServer()-TimeGMT())/3600.0;
      if(MathAbs(hours-(2+UsSummer(today)))>0.34)
         why=StringFormat("the server clock is %.1f hours ahead of GMT, %d expected",hours,2+UsSummer(today));
     }
   if(why=="")
      return(true);
   if(g_propNote!=today)
     {
      Print("AurumFunded: no trading today, ",why);
      g_propNote=today;
     }
   return(false);
  }

// Days since the phase started on which the EA opened a trade.
int PropDays()
  {
   static datetime at=0;
   static int days=0;
   if(at>0 && TimeCurrent()<at+60)
      return(days);
   if(!HistorySelect(g_propSince,TimeCurrent()+60))
      return(days);
   at=TimeCurrent();
   days=0;
   datetime last=0;
   for(int i=0; i<HistoryDealsTotal(); i++)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0 || HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN)
         continue;
      long magic=HistoryDealGetInteger(d,DEAL_MAGIC);
      if(magic<InpMagic || magic>InpMagic+DRIFT_MAGIC)
         continue;
      datetime day=DayOf((datetime)HistoryDealGetInteger(d,DEAL_TIME)-HHMMSec(InpPropResetHHMM));
      if(day!=last)
         days++;
      last=day;
     }
   return(days);
  }

// The firm's rules. Returns false while nothing may be traded: after the day stop, the final stop or the target,
// and on a day the clock is off. Everything open is closed then.
bool PropGuard()
  {
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   double bal=AccountInfoDouble(ACCOUNT_BALANCE);
   if(g_propStart<=0)
     {
      if(GlobalVariableCheck(PropKey("start")))
        {
         g_propStart=GlobalVariableGet(PropKey("start"));
         g_propSince=(datetime)GlobalVariableGet(PropKey("since"));
         g_propPeak=GlobalVariableGet(PropKey("peak"));
         g_propDay=(datetime)GlobalVariableGet(PropKey("day"));
         g_propDayBal=GlobalVariableGet(PropKey("daybal"));
         g_propDayStop=(GlobalVariableGet(PropKey("daystop"))>0);
         g_propLocked=(GlobalVariableCheck(PropKey("lock")) && GlobalVariableGet(PropKey("lock"))>0);
        }
      else
        {
         g_propStart=(InpPropStart>0 ? InpPropStart : bal);
         g_propSince=TimeCurrent();
         g_propPeak=g_propStart;
         GlobalVariableSet(PropKey("start"),g_propStart);
         GlobalVariableSet(PropKey("since"),(double)g_propSince);
         GlobalVariableSet(PropKey("peak"),g_propPeak);
         PrintFormat("AurumFunded: phase %d started, initial balance %.2f, target %.2f, day stop %.2f, final stop at %.2f",
                     InpPropRound,g_propStart,g_propStart*(1.0+InpPropTargetPct/100.0),g_propStart*InpPropDayStopPct/100.0,PropFloor());
        }
      if(g_propStart<=0)
         return(false);
     }
   datetime day=DayOf(TimeCurrent()-HHMMSec(InpPropResetHHMM));
   if(day!=g_propDay)
     {
      g_propDay=day;
      g_propDayBal=MathMax(bal,eq);
      g_propPeak=MathMax(g_propPeak,g_propDayBal);
      g_propDayStop=false;
      GlobalVariableSet(PropKey("day"),(double)g_propDay);
      GlobalVariableSet(PropKey("daybal"),g_propDayBal);
      GlobalVariableSet(PropKey("peak"),g_propPeak);
      GlobalVariableSet(PropKey("daystop"),0.0);
      // Once a firm day the levels the guard works with, so a demo or tester log can be set against the firm's own.
      PrintFormat("AurumFunded: firm day %s, day start %.2f (balance %.2f, equity %.2f), day stop at %.2f, highest day start %.2f, final stop at %.2f (%s)",
                  TimeToString(day,TIME_DATE),g_propDayBal,bal,eq,g_propDayBal-g_propStart*InpPropDayStopPct/100.0,g_propPeak,PropFloor(),
                  g_propLocked ? "locked" : (InpPropTrailing ? "trailing" : "static"));
     }
   if(!g_propLocked && InpPropLockPct>0 && eq>=g_propStart*(1.0+InpPropLockPct/100.0))
     {
      g_propLocked=true;
      GlobalVariableSet(PropKey("lock"),1.0);
      PrintFormat("AurumFunded: equity %.2f is %.1f%% up, the final stop moves to %.2f for good",eq,InpPropLockPct,PropFloor());
     }
   double target=g_propStart*(1.0+InpPropTargetPct/100.0);
   bool reached=(InpPropTargetPct>0 && eq>=target);
   g_propCoast=(reached && PropDays()<InpPropMinDays);
   if(g_propClose==0 && eq<=PropFloor())
     {
      g_propClose=1;
      PrintFormat("AurumFunded: equity %.2f is at the final stop %.2f, closing everything and halting",eq,PropFloor());
     }
   if(g_propClose==0 && reached && !g_propCoast)
     {
      g_propClose=2;
      PrintFormat("AurumFunded: equity %.2f has reached the target %.2f after %d trading days, closing everything",eq,target,PropDays());
     }
   if(g_propClose==0 && !g_propDayStop && eq<=g_propDayBal-g_propStart*InpPropDayStopPct/100.0)
     {
      g_propDayStop=true;
      GlobalVariableSet(PropKey("daystop"),1.0);
      PrintFormat("AurumFunded: equity %.2f is %.1f%% of the initial balance under the day's start %.2f, closing everything until the firm's next day",
                  eq,InpPropDayStopPct,g_propDayBal);
     }
   if(g_propClose==0 && !g_propDayStop && InpPropFloatPct>0 && eq-bal<=-g_propStart*InpPropFloatPct/100.0)
     {
      g_propDayStop=true;
      GlobalVariableSet(PropKey("daystop"),1.0);
      PrintFormat("AurumFunded: open positions are %.2f in loss together (%.1f%% of the initial balance), closing everything until the firm's next day",
                  bal-eq,InpPropFloatPct);
     }
   bool clock=ClockOk();
   if(g_propClose==0 && !g_propDayStop && clock)
      return(true);
   static datetime tried=0;     // a close that fails, as in a closed market, is tried again every ten seconds
   if(TimeCurrent()<tried+10)
      return(false);
   tried=TimeCurrent();
   if(!CloseEverything() || g_propClose==0)
      return(false);
   if(g_propClose==2 && AccountInfoDouble(ACCOUNT_BALANCE)<target)
     {
      PrintFormat("AurumFunded: balance %.2f after closing is under the target %.2f, trading on",AccountInfoDouble(ACCOUNT_BALANCE),target);
      g_propClose=0;
      return(false);
     }
   g_halted=true;
   Print(g_propClose==2 ? "AurumFunded: the phase is passed. Start the next one with a new InpPropRound and its target" :
         "AurumFunded: halted at the final stop. Nothing more is traded in this phase");
   if(MQLInfoInteger(MQL_TESTER))
      TesterStop();
   return(false);
  }

// Hooks of Include/Aurum/Legs.mqh.
double AurumSize() { return(PropSize()); }

// A stop at the broker, so that a unit cannot lose more than InpGoldStopPct of equity while the EA is offline.
bool AurumGoldStop(double lots,double ask,double bid,double &sl)
  {
   sl=0.0;
   double loss=0.0;
   if(InpGoldStopPct>0)
     {
      if(!OrderCalcProfit(ORDER_TYPE_BUY,InpGold,lots,ask,0.99*ask,loss) || loss>=0)
         return(false);
      double dist=0.01*ask*AccountInfoDouble(ACCOUNT_EQUITY)*InpGoldStopPct/100.0/(-loss);
      sl=NormalizeDouble(bid-dist,(int)SymbolInfoInteger(InpGold,SYMBOL_DIGITS));
     }
   return(true);
  }

bool AurumGuard() { return(PropGuard()); }

bool AurumInputsBad()
  {
   return(InpPropStart<0 || InpPropTargetPct<0 || InpPropMinDays<0 || InpPropDayStopPct<=0 || InpPropMaxStopPct<=0 ||
          InpPropLockPct<0 || InpPropLockStopPct<=0 || InpPropFloatPct<0 || InpPropRoomPct<0 || InpPropMinSize<=0 || InpPropMinSize>1 || InpPropCap<1 || InpPropFastDays<21 || InpPropCoast<=0 || InpPropCoast>1 || InpPropResetHHMM<0 ||
          InpPropResetHHMM>2359 || InpPropResetHHMM%100>59 || InpGoldStopPct<0);
  }
