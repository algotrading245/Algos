//+------------------------------------------------------------------+
//| AurumMeridian.mq5 - sells EUR/USD through the European midday    |
//| and closes before New York starts. At InpStartMin London time    |
//| (11:30) the pair is sold, at InpEndMin (13:00) it is bought      |
//| back, or earlier at a stop InpStopMult times the average size of |
//| the same window's move over the previous InpDays days. One trade |
//| a day on the chosen weekdays, never held past the window.        |
//| The window follows the London clock. The server clock is taken   |
//| to be New York time plus 7 hours, which is London plus 2 hours,  |
//| and plus 3 in the weeks when only the US is on summer time.      |
//| The edge is about one basis point before cost: it needs a raw    |
//| spread account, and the later days of the week carry most of it. |
//| Backtest: tools/backtest_meridian.py                             |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpStartMin       = 690;    // Entry, minutes after midnight London time (multiple of 5)
input int    InpEndMin         = 780;    // Exit, minutes after midnight London time (multiple of 5)
input int    InpSide           = -1;     // -1 sell, 1 buy
input int    InpDays           = 60;     // Days in the average
input bool   InpMonday         = true;   // Trade on Monday
input bool   InpTuesday        = true;   // Trade on Tuesday
input bool   InpWednesday      = true;   // Trade on Wednesday
input bool   InpThursday       = true;   // Trade on Thursday
input bool   InpFriday         = true;   // Trade on Friday

input group "Size and risk guard"
input double InpRiskPct        = 1.0;    // Loss at the stop, % of balance
input double InpStopMult       = 3.0;    // Stop distance, average window moves
input int    InpMaxSpread      = 15;     // No entry while spread is above this, points
input int    InpEntrySec       = 60;     // No entry later than this after the start, seconds

input group "Execution"
input long   InpMagic          = 245010; // Magic number
input int    InpDeviation      = 10;     // Max slippage, points

CTrade   g_trade;
datetime g_doneDay=0;      // day whose window has been dealt with

// Ticket of the position held under the magic number, 0 if none; 'opened' receives its open time.
ulong Held(datetime &opened)
  {
   opened=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      opened=(datetime)PositionGetInteger(POSITION_TIME);
      return(t);
     }
   return(0);
  }

// True when a trade of this EA was already opened since 'from' (covers a restart inside the window).
bool TradedSince(datetime from)
  {
   if(!HistorySelect(from,TimeCurrent()+60))
      return(false);
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d!=0 && HistoryDealGetString(d,DEAL_SYMBOL)==_Symbol && HistoryDealGetInteger(d,DEAL_MAGIC)==InpMagic &&
         HistoryDealGetInteger(d,DEAL_ENTRY)==DEAL_ENTRY_IN)
         return(true);
     }
   return(false);
  }

// The n-th Sunday of the month, n = -1 for the last one (months of 31 days only).
datetime Sunday(int year,int month,int n)
  {
   MqlDateTime s;
   ZeroMemory(s);
   s.year=year;
   s.mon=month;
   s.day=(n>0 ? 1 : 31);
   datetime d=StructToTime(s);
   TimeToStruct(d,s);
   return(n>0 ? d+(((7-s.day_of_week)%7)+7*(n-1))*86400 : d-s.day_of_week*86400);
  }

// Minutes the server clock is ahead of London time on 'day': 120, or 180 while only the US is on summer time.
int LondonOffset(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   int us=(day>=Sunday(s.year,3,2) && day<Sunday(s.year,11,1) ? 1 : 0);
   int uk=(day>=Sunday(s.year,3,-1) && day<Sunday(s.year,10,-1) ? 1 : 0);
   return(120+60*(us-uk));
  }

// Server time of the London minute 'londonMin' on 'day'.
datetime ServerTime(datetime day,int londonMin)
  {
   return(day+(londonMin+LondonOffset(day))*60);
  }

// Move through the window of the day starting at 'day' as a fraction of the price. False when that day has no
// bar at the start of the window.
bool WindowMove(datetime day,double &move)
  {
   datetime a=ServerTime(day,InpStartMin),b=ServerTime(day,InpEndMin);
   int s=iBarShift(_Symbol,PERIOD_M5,a,true);
   if(s<0)
      return(false);
   int e=iBarShift(_Symbol,PERIOD_M5,b-300,false);
   if(e<0 || e>s)
      return(false);
   double open=iOpen(_Symbol,PERIOD_M5,s);
   if(open<=0)
      return(false);
   move=iClose(_Symbol,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// Average size of the window's move over the InpDays trading days before 'today'; 0 while history is short.
double AverageMove(datetime today)
  {
   double sum=0.0,move;
   int n=0;
   for(int i=1; i<=2*InpDays+20 && n<InpDays; i++)
      if(WindowMove(today-i*86400,move))
        {
         sum+=MathAbs(move);
         n++;
        }
   return(n>=InpDays/2 ? sum/n : 0.0);
  }

// True when the EA trades on the weekday of 'day'.
bool TradingDay(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   switch(s.day_of_week)
     {
      case 1: return(InpMonday);
      case 2: return(InpTuesday);
      case 3: return(InpWednesday);
      case 4: return(InpThursday);
      case 5: return(InpFriday);
     }
   return(false);
  }

// Lots that lose InpRiskPct of the balance when price goes 'dist' against the position; 0 when below the minimum lot.
double Lots(int side,double price,double dist)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss,margin;
   if(!OrderCalcProfit(type,_Symbol,1.0,price,price-side*dist,loss) || loss>=0)
      return(0.0);
   double lots=AccountInfoDouble(ACCOUNT_BALANCE)*InpRiskPct/100.0/(-loss);
   if(OrderCalcMargin(type,_Symbol,1.0,price,margin) && margin>0)
      lots=MathMin(lots,0.5*AccountInfoDouble(ACCOUNT_MARGIN_FREE)/margin);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

// Closes the position at the end of the window of the day it was opened on.
void Manage()
  {
   datetime opened;
   ulong t=Held(opened);
   if(t==0 || TimeCurrent()<ServerTime(opened-opened%86400,InpEndMin))
      return;
   if(!g_trade.PositionClose(t,InpDeviation))
      PrintFormat("AurumMeridian: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpStartMin<0 || InpStartMin%5!=0 || InpEndMin%5!=0 || InpEndMin<InpStartMin+5 || InpEndMin>1250 ||
      (InpSide!=-1 && InpSide!=1) || InpDays<2 || InpRiskPct<=0 || InpStopMult<=0 || InpMaxSpread<0 || InpEntrySec<1)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   iBars(_Symbol,PERIOD_M5);   // starts loading the bars the average is built from
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   Manage();
  }

void OnTick()
  {
   Manage();
   datetime now=TimeCurrent();
   datetime today=now-now%86400;
   datetime start=ServerTime(today,InpStartMin);
   if(g_doneDay==today || now<start)
      return;
   datetime opened;
   if(!TradingDay(today) || now-start>=InpEntrySec || Held(opened)!=0 || TradedSince(start))
     {
      g_doneDay=today;
      return;
     }
   double avg=AverageMove(today);
   if(avg<=0)
     {
      PrintFormat("AurumMeridian: fewer than %d days of M5 history, no trade today",InpDays/2);
      g_doneDay=today;
      return;
     }
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpMaxSpread*_Point)
      return;                  // tried again until InpEntrySec after the start
   double spread=q.ask-q.bid;
   double dist=MathMax(InpStopMult*avg*q.bid,SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point+spread);
   double lots=Lots(InpSide,InpSide>0 ? q.ask : q.bid,dist);
   if(lots<=0)
     {
      PrintFormat("AurumMeridian: balance too small for the minimum lot at a stop of %.5f, no trade today",dist);
      g_doneDay=today;
      return;
     }
   // the stop sits 'dist' from the bid on both sides, as in the backtest
   double sl=NormalizeDouble(q.bid-InpSide*dist,_Digits);
   bool ok=(InpSide>0 ? g_trade.Buy(lots,_Symbol,0.0,sl,0.0,"AurumMeridian") : g_trade.Sell(lots,_Symbol,0.0,sl,0.0,"AurumMeridian"));
   if(!ok || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumMeridian: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat("AurumMeridian: average move %.1f bp, %s %.2f lots at %.5f, stop %.5f, closes at %s",
               1e4*avg,InpSide>0 ? "bought" : "sold",lots,g_trade.ResultPrice(),sl,
               TimeToString(ServerTime(today,InpEndMin),TIME_MINUTES));
   g_doneDay=today;
  }
//+------------------------------------------------------------------+
