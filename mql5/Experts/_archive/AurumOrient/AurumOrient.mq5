//+------------------------------------------------------------------+
//| AurumOrient.mq5 - long gold through the Asian session.           |
//| Session unit: bought a few minutes after the daily reopen, once  |
//| the reopening spread has narrowed, and closed at the London      |
//| morning. Dip unit: one more unit after an M15 bar falls by more  |
//| than InpDipSigma standard deviations during the session, closed  |
//| after InpDipHoldBars bars. Each unit is sized to a share of       |
//| gold's daily volatility. Long only, never held overnight, so no  |
//| swap is paid.                                                    |
//| Research: tools/backtest_orient.py                               |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Session unit (server time)"
input int    InpEntryHHMM      = 105;   // Buy from this time, HHMM
input int    InpEntryMinutes   = 20;    // Stop trying to enter this many minutes later
input int    InpExitHHMM       = 900;   // Close at this time, HHMM

input group "Dip unit"
input bool   InpUseDip         = true;  // Add a unit after a sharp M15 fall
input double InpDipSigma       = 3.0;   // Fall of the M15 bar, standard deviations
input int    InpDipWindow      = 96;    // M15 returns used for the standard deviation
input int    InpDipFromHHMM    = 115;   // Earliest open time of the falling bar, HHMM
input int    InpDipToHHMM      = 745;   // Latest open time of the falling bar, HHMM
input int    InpDipHoldBars    = 16;    // Holding time, M15 bars

input group "Size"
input double InpVolTargetPct   = 30.0;  // Annual gold volatility one unit is scaled to, %
input int    InpVolSpan        = 30;    // Span of the exponentially weighted daily volatility
input double InpMaxLeverage    = 4.0;   // Maximum notional of one unit as a multiple of equity

input group "Risk guard"
input double InpMarginPct      = 50.0;  // Margin cap, % of free margin
input double InpMaxSpread      = 0.30;  // No entry while spread is above this, price units
input double InpMaxDrawdownPct = 30.0;  // Close and stop after this equity drawdown from the peak, %

input group "Execution"
input long   InpMagic          = 245006; // Magic number of the session unit; the dip unit uses the next one
input int    InpDeviation      = 30;     // Max slippage, points

#define VOL_BARS 250       // daily returns used for the volatility estimate
#define DIP_LATE 300       // a dip signal is dropped this many seconds after its bar closed

CTrade   g_trade;
datetime g_day=0;          // day whose session entry has been handled
datetime g_bar=0;          // M15 bar whose dip signal has been handled
double   g_peak=0.0;
bool     g_halted=false;

int HHMM(datetime t)
  {
   MqlDateTime s;
   TimeToStruct(t,s);
   return(s.hour*100+s.min);
  }

datetime DayOf(datetime t)
  {
   return(t-t%86400);
  }

// Lots held under 'magic'; 'opened' receives the earliest open time.
double HeldLots(long magic,datetime &opened)
  {
   double lots=0.0;
   opened=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      lots+=PositionGetDouble(POSITION_VOLUME);
      datetime o=(datetime)PositionGetInteger(POSITION_TIME);
      if(opened==0 || o<opened)
         opened=o;
     }
   return(lots);
  }

// Closes every position under 'magic'. Returns false if a close failed.
bool CloseAll(long magic)
  {
   bool ok=true;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      if(!g_trade.PositionClose(t,InpDeviation))
        {
         PrintFormat("AurumOrient: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         ok=false;
        }
     }
   return(ok);
  }

// Leverage of one unit from completed daily bars; false while history is not available.
bool UnitLeverage(double &lev)
  {
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(_Symbol,PERIOD_D1,1,VOL_BARS+1,c)<VOL_BARS+1)
      return(false);
   // Exponentially weighted standard deviation of daily returns, newest first, with bias correction.
   double decay=1.0-2.0/(InpVolSpan+1.0);
   double w=1.0,sw=0.0,sw2=0.0,mean=0.0;
   for(int i=0; i<VOL_BARS; i++)
     {
      mean+=w*(c[i]/c[i+1]-1.0);
      sw+=w; sw2+=w*w;
      w*=decay;
     }
   mean/=sw;
   double var=0.0;
   w=1.0;
   for(int i=0; i<VOL_BARS; i++)
     {
      double r=c[i]/c[i+1]-1.0-mean;
      var+=w*r*r;
      w*=decay;
     }
   var=var/sw*(sw*sw)/(sw*sw-sw2);
   double vol=MathSqrt(var*252.0);
   if(vol<=0)
      return(false);
   lev=MathMin(InpMaxLeverage,InpVolTargetPct/100.0/vol);
   return(true);
  }

// Buys one unit under 'magic'. Returns true when nothing is left to do, false to try again on a later tick.
bool BuyUnit(long magic,string what)
  {
   double lev;
   if(!UnitLeverage(lev))
      return(false);
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   if(ask<=0 || bid<=0 || step<=0 || tickSize<=0 || tickValue<=0 || ask-bid>InpMaxSpread)
      return(false);
   // Money value of one lot at the current price, in account currency.
   double notionalPerLot=ask/tickSize*tickValue;
   double lots=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*lev/notionalPerLot/step+1e-9)*step;
   double margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,1.0,ask,margin) && margin>0)
      lots=MathMin(lots,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
   lots=MathMin(lots,vmax);
   if(lots<vmin)
     {
      PrintFormat("AurumOrient: balance too small for the minimum lot at leverage %.2f, no %s unit",lev,what);
      return(true);
     }
   g_trade.SetExpertMagicNumber(magic);
   if(!g_trade.Buy(lots,_Symbol,0.0,0.0,0.0,"AurumOrient "+what))
     {
      PrintFormat("AurumOrient: buy failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return(false);
     }
   PrintFormat("AurumOrient: %s unit, leverage %.2f, bought %.2f",what,lev,lots);
   return(true);
  }

// True when the last completed M15 bar is a dip signal.
bool DipSignal()
  {
   datetime bar=iTime(_Symbol,PERIOD_M15,1);
   int hm=HHMM(bar);
   if(bar==0 || DayOf(bar)!=DayOf(TimeCurrent()) || hm<InpDipFromHHMM || hm>InpDipToHHMM)
      return(false);
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(_Symbol,PERIOD_M15,1,InpDipWindow+2,c)<InpDipWindow+2)
      return(false);
   double mean=0.0,var=0.0;
   for(int i=1; i<=InpDipWindow; i++)
      mean+=MathLog(c[i]/c[i+1]);
   mean/=InpDipWindow;
   for(int i=1; i<=InpDipWindow; i++)
     {
      double r=MathLog(c[i]/c[i+1])-mean;
      var+=r*r;
     }
   double sd=MathSqrt(var/(InpDipWindow-1));
   return(sd>0 && MathLog(c[0]/c[1])<=-InpDipSigma*sd);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEntryHHMM>=InpExitHHMM || InpEntryMinutes<1 || InpDipWindow<10 || InpDipHoldBars<1 || InpDipSigma<=0 ||
      InpVolSpan<2 || InpVolTargetPct<=0 || InpMaxLeverage<=0)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   if(g_halted)
      return;
   datetime now=TimeCurrent();
   datetime day=DayOf(now);
   int hm=HHMM(now);
   datetime baseOpened,dipOpened;
   double baseLots=HeldLots(InpMagic,baseOpened);
   double dipLots=HeldLots(InpMagic+1,dipOpened);
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      PrintFormat("AurumOrient: equity %.2f is %.1f%% below the peak %.2f, closing and halting",eq,InpMaxDrawdownPct,g_peak);
      bool a=CloseAll(InpMagic),b=CloseAll(InpMagic+1);
      g_halted=(a && b);
      return;
     }
   // Session unit: closed at the exit time, and whenever it is found open outside the session.
   if(baseLots>0 && (hm>=InpExitHHMM || hm<InpEntryHHMM || DayOf(baseOpened)!=day))
      CloseAll(InpMagic);
   else if(baseLots<=0 && g_day!=day && hm>=InpEntryHHMM && hm<InpExitHHMM)
     {
      MqlDateTime s;
      TimeToStruct(now,s);
      if(s.hour*60+s.min>=InpEntryHHMM/100*60+InpEntryHHMM%100+InpEntryMinutes || BuyUnit(InpMagic,"session"))
         g_day=day;
     }
   else if(baseLots>0)
      g_day=day;
   // Dip unit: closed InpDipHoldBars bars after the bar it was bought on, or before the day ends.
   if(dipLots>0)
     {
      datetime entryBar=dipOpened-dipOpened%900;
      if(now>=entryBar+InpDipHoldBars*900 || DayOf(dipOpened)!=day || hm>=2350)
         CloseAll(InpMagic+1);
      return;
     }
   datetime bar=iTime(_Symbol,PERIOD_M15,0);
   if(!InpUseDip || bar==0 || bar==g_bar)
      return;
   if(now-bar>DIP_LATE || !DipSignal() || BuyUnit(InpMagic+1,"dip"))
      g_bar=bar;
  }
//+------------------------------------------------------------------+
