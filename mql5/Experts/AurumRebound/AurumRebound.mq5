//+------------------------------------------------------------------+
//| AurumRebound.mq5 - gold Asian-session dip buy.                   |
//| When an M15 bar in the Asian hours closes with a drop of several |
//| standard deviations, buys the next bar open and closes after a   |
//| fixed hold. One position at a time, long only, no averaging.     |
//| Research: research/asia_dip_buy.py, tools/backtest_rebound.py    |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input double InpShockSigma     = 3.0;   // Drop of the closed M15 bar, in standard deviations
input int    InpVolBars        = 96;    // M15 returns used for the standard deviation
input int    InpHourFrom       = 1;     // First server hour in which the signal bar may open
input int    InpHourTo         = 8;     // Last server hour in which the signal bar may open
input int    InpHoldBars       = 4;     // Close this many M15 bars after entry
input int    InpEntryWindowSec = 60;    // Enter only within this many seconds of the new bar

input group "Size"
input double InpLeverage       = 3.0;   // Position notional as a multiple of equity
input double InpFixedLot       = 0.0;   // Fixed lot (0 = size from leverage)
input double InpMarginPct      = 50.0;  // Margin cap, % of free margin

input group "Risk guard"
input double InpStopPct        = 1.0;   // Protective stop, % below entry (0 = none)
input double InpMaxSpread      = 0.40;  // Skip the signal if spread is above this, price units
input double InpMaxDrawdownPct = 20.0;  // Stop trading after this equity drawdown from the peak, %

input group "Execution"
input long   InpMagic          = 245003; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

CTrade   g_trade;
datetime g_bar=0;          // open time of the last M15 bar seen
double   g_peak=0.0;
bool     g_halted=false;

bool FindPosition(ulong &ticket,datetime &opened)
  {
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      ticket=t;
      opened=(datetime)PositionGetInteger(POSITION_TIME);
      return(true);
     }
   return(false);
  }

// Log return of the last closed M15 bar divided by the sample standard deviation of the
// InpVolBars returns before it. Returns false while history is too short.
bool ShockZ(double &z,datetime &barOpen)
  {
   MqlRates r[];
   int need=InpVolBars+2;
   if(CopyRates(_Symbol,PERIOD_M15,1,need,r)!=need)
      return(false);
   // r[need-1] is the bar that just closed, r[0] the oldest.
   double sum=0.0,sum2=0.0;
   for(int i=1; i<need-1; i++)
     {
      if(r[i].close<=0 || r[i-1].close<=0)
         return(false);
      double x=MathLog(r[i].close/r[i-1].close);
      sum+=x;
      sum2+=x*x;
     }
   double var=(sum2-sum*sum/InpVolBars)/(InpVolBars-1);
   if(var<=0)
      return(false);
   z=MathLog(r[need-1].close/r[need-2].close)/MathSqrt(var);
   barOpen=r[need-1].time;
   return(true);
  }

double LotFor(const double ask)
  {
   double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(step<=0 || tickSize<=0 || tickValue<=0)
      return(0.0);
   double lot=InpFixedLot;
   if(lot<=0)
     {
      // Money value of one lot at the current price, in account currency.
      double notionalPerLot=ask/tickSize*tickValue;
      lot=AccountInfoDouble(ACCOUNT_EQUITY)*InpLeverage/notionalPerLot;
     }
   double margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,1.0,ask,margin) && margin>0)
      lot=MathMin(lot,AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin);
   lot=MathFloor(lot/step+1e-9)*step;
   if(lot<vmin)
      return(0.0);
   return(MathMin(lot,vmax));
  }

void Enter(const double z)
  {
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(ask<=0 || bid<=0)
      return;
   if(ask-bid>InpMaxSpread)
     {
      PrintFormat("AurumRebound: spread %.2f above %.2f, signal skipped",ask-bid,InpMaxSpread);
      return;
     }
   double lot=LotFor(ask);
   if(lot<=0)
     {
      Print("AurumRebound: balance too small for the minimum lot at this leverage, signal skipped");
      return;
     }
   double sl=0.0;
   if(InpStopPct>0)
     {
      double minDist=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
      sl=NormalizeDouble(MathMin(bid*(1.0-InpStopPct/100.0),bid-minDist),_Digits);
     }
   if(g_trade.Buy(lot,_Symbol,0.0,sl,0.0,"AurumRebound"))
      PrintFormat("AurumRebound: bought %.2f after a %.1f sigma drop",lot,-z);
   else
      PrintFormat("AurumRebound: buy failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpShockSigma<=0 || InpVolBars<10 || InpHoldBars<1 || InpEntryWindowSec<1 || InpHourFrom>InpHourTo ||
      (InpLeverage<=0 && InpFixedLot<=0))
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   // Starting mid-bar must not act on a bar that closed before the EA was attached.
   g_bar=iTime(_Symbol,PERIOD_M15,0);
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void Manage()
  {
   datetime now=TimeCurrent();
   ulong ticket; datetime opened;
   if(FindPosition(ticket,opened))
     {
      // Exit on the open of the bar InpHoldBars after the entry bar.
      datetime entryBar=opened-(opened%900);
      if(now>=entryBar+InpHoldBars*900)
         if(!g_trade.PositionClose(ticket,InpDeviation))
            PrintFormat("AurumRebound: close failed, retcode %d",g_trade.ResultRetcode());
      return;
     }
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(!g_halted && InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      g_halted=true;
      PrintFormat("AurumRebound: equity %.2f is %.1f%% below the peak %.2f, trading halted",eq,InpMaxDrawdownPct,g_peak);
     }
  }

void OnTimer()
  {
   Manage();
  }

void OnTick()
  {
   ulong ticket; datetime opened;
   // A bar that closes while a position is still open is not a signal, even if that
   // position is closed on this same tick.
   bool busy=FindPosition(ticket,opened);
   Manage();
   datetime bar=iTime(_Symbol,PERIOD_M15,0);
   if(bar==0 || bar==g_bar)
      return;
   g_bar=bar;
   if(busy || g_halted || TimeCurrent()-bar>InpEntryWindowSec)
      return;
   double z; datetime sigBar;
   if(!ShockZ(z,sigBar) || z>-InpShockSigma)
      return;
   MqlDateTime s,n;
   TimeToStruct(sigBar,s);
   TimeToStruct(bar,n);
   // Same server day only: the bar after the last one of a session opens the next day.
   if(s.hour<InpHourFrom || s.hour>InpHourTo || s.day!=n.day)
      return;
   Enter(z);
  }
//+------------------------------------------------------------------+
