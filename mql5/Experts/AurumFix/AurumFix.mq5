//+------------------------------------------------------------------+
//| AurumFix.mq5 - gold morning-auction dip.                         |
//| Every weekday sells shortly before the 10:30 London gold auction |
//| and buys back a few minutes after it. Times are London times and |
//| are converted to server time (server follows US daylight saving, |
//| London follows UK daylight saving). One position, short only.    |
//| Research: research/auction_dip.py, tools/backtest_fix.py         |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpEntryHour      = 10;    // Entry, London hour
input int    InpEntryMinute    = 20;    // Entry, London minute
input int    InpHoldMinutes    = 15;    // Close this many minutes after the entry time
input int    InpEntryWindowSec = 60;    // Enter only within this many seconds of the entry time
input int    InpServerWinterGMT= 2;     // Server GMT offset in US winter (summer is one more)

input group "Size"
input double InpLeverage       = 3.0;   // Position notional as a multiple of equity
input double InpFixedLot       = 0.0;   // Fixed lot (0 = size from leverage)
input double InpMarginPct      = 50.0;  // Margin cap, % of free margin

input group "Risk guard"
input double InpStopPct        = 0.3;   // Protective stop, % above entry (0 = none)
input double InpMaxSpread      = 0.30;  // Skip the day if spread is above this, price units
input double InpMaxDrawdownPct = 10.0;  // Stop trading after this equity drawdown from the peak, %

input group "Execution"
input long   InpMagic          = 245004; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

CTrade   g_trade;
datetime g_day=0;          // server day on which an entry was last attempted
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

// Midnight of the n-th Sunday of a month (n = 0 for the last one).
datetime SundayOf(const int year,const int month,const int n)
  {
   MqlDateTime s;
   s.year=year; s.mon=month; s.day=1; s.hour=0; s.min=0; s.sec=0;
   datetime first=StructToTime(s);
   TimeToStruct(first,s);
   datetime sunday=first+((7-s.day_of_week)%7)*86400;
   if(n>0)
      return(sunday+(n-1)*7*86400);
   MqlDateTime x;
   for(;;)
     {
      TimeToStruct(sunday+7*86400,x);
      if(x.mon!=month)
         return(sunday);
      sunday+=7*86400;
     }
  }

// Seconds to add to London time to get server time on this server day.
int LondonShift(const datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   bool us=(day>=SundayOf(s.year,3,2) && day<SundayOf(s.year,11,1));
   bool uk=(day>=SundayOf(s.year,3,0) && day<SundayOf(s.year,10,0));
   return((InpServerWinterGMT+(us?1:0)-(uk?1:0))*3600);
  }

// Server time of today's entry.
datetime EntryTime(const datetime now)
  {
   datetime day=now-(now%86400);
   return(day+InpEntryHour*3600+InpEntryMinute*60+LondonShift(day));
  }

double LotFor(const double bid)
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
      double notionalPerLot=bid/tickSize*tickValue;
      lot=AccountInfoDouble(ACCOUNT_EQUITY)*InpLeverage/notionalPerLot;
     }
   double margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_SELL,_Symbol,1.0,bid,margin) && margin>0)
      lot=MathMin(lot,AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin);
   lot=MathFloor(lot/step+1e-9)*step;
   if(lot<vmin)
      return(0.0);
   return(MathMin(lot,vmax));
  }

void Enter()
  {
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(ask<=0 || bid<=0)
      return;
   if(ask-bid>InpMaxSpread)
     {
      PrintFormat("AurumFix: spread %.2f above %.2f, day skipped",ask-bid,InpMaxSpread);
      return;
     }
   double lot=LotFor(bid);
   if(lot<=0)
     {
      Print("AurumFix: balance too small for the minimum lot at this leverage, day skipped");
      return;
     }
   double sl=0.0;
   if(InpStopPct>0)
     {
      double minDist=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
      sl=NormalizeDouble(MathMax(ask*(1.0+InpStopPct/100.0),ask+minDist),_Digits);
     }
   if(g_trade.Sell(lot,_Symbol,0.0,sl,0.0,"AurumFix"))
      PrintFormat("AurumFix: sold %.2f at %.2f, stop %.2f",lot,bid,sl);
   else
      PrintFormat("AurumFix: sell failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEntryHour<0 || InpEntryHour>23 || InpEntryMinute<0 || InpEntryMinute>59 || InpHoldMinutes<1 ||
      InpEntryWindowSec<1 || (InpLeverage<=0 && InpFixedLot<=0))
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

// Returns true while a position of this EA is open.
bool Manage()
  {
   datetime now=TimeCurrent();
   ulong ticket; datetime opened;
   if(FindPosition(ticket,opened))
     {
      // Exit InpHoldMinutes after the entry time of the day the position was opened.
      if(now>=EntryTime(opened)+InpHoldMinutes*60)
         if(!g_trade.PositionClose(ticket,InpDeviation))
            PrintFormat("AurumFix: close failed, retcode %d",g_trade.ResultRetcode());
      return(true);
     }
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(!g_halted && InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      g_halted=true;
      PrintFormat("AurumFix: equity %.2f is %.1f%% below the peak %.2f, trading halted",eq,InpMaxDrawdownPct,g_peak);
     }
   return(false);
  }

void OnTimer()
  {
   Manage();
  }

void OnTick()
  {
   if(Manage() || g_halted)
      return;
   datetime now=TimeCurrent();
   datetime day=now-(now%86400);
   if(day==g_day)
      return;
   datetime entry=EntryTime(now);
   if(now<entry)
      return;
   // One attempt per day, whether or not it is filled.
   g_day=day;
   MqlDateTime s;
   TimeToStruct(now,s);
   if(s.day_of_week==0 || s.day_of_week==6 || now-entry>InpEntryWindowSec)
      return;
   Enter();
  }
//+------------------------------------------------------------------+
