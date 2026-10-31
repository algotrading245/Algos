//+------------------------------------------------------------------+
//| AurumTokyo.mq5 - sells USD/JPY at the Tokyo 9:55 fixing and buys |
//| it back InpHoldMin minutes later. Japanese banks set the day's   |
//| customer rate at 9:55 and importers buy their dollars at it, so  |
//| the pair tends to rise into the fixing and fall back after it.   |
//| The stop is InpStopMult times the average size of the same       |
//| window's move over the previous InpDays days. One trade a day on |
//| the chosen weekdays; InpGotobi 1 trades only the settlement days |
//| (dates divisible by five, or the Friday before one that falls on |
//| a weekend), where the pattern is about twice as large.           |
//| Japan keeps one clock all year. The server clock is taken to be  |
//| New York time plus 7 hours, so the fixing is at 02:55 server     |
//| time in the US winter and at 03:55 in the US summer.             |
//| The edge is about two basis points before cost and the first     |
//| minute carries a good part of it: it needs a raw spread account  |
//| and no order is sent later than InpEntrySec after the fixing.    |
//| Backtest: tools/backtest_tokyo.py                                |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpHoldMin        = 90;     // Exit, minutes after the fixing (multiple of 5)
input int    InpDays           = 60;     // Days in the average
input int    InpGotobi         = 1;      // 1 settlement days only, -1 the other days, 0 all
input bool   InpMonday         = true;   // Trade on Monday
input bool   InpTuesday        = true;   // Trade on Tuesday
input bool   InpWednesday      = true;   // Trade on Wednesday
input bool   InpThursday       = true;   // Trade on Thursday
input bool   InpFriday         = true;   // Trade on Friday

input group "Size and risk guard"
input double InpRiskPct        = 1.0;    // Loss at the stop, % of balance
input double InpStopMult       = 3.0;    // Stop distance, average window moves
input int    InpMaxSpread      = 15;     // No entry while spread is above this, points
input int    InpEntrySec       = 20;     // No entry later than this after the fixing, seconds

input group "Execution"
input long   InpMagic          = 245011; // Magic number
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

// Server time of 9:55 Tokyo time on 'day': 02:55, or 03:55 while the US is on summer time.
datetime FixTime(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   int us=(day>=Sunday(s.year,3,2) && day<Sunday(s.year,11,1) ? 1 : 0);
   return(day+(175+60*us)*60);
  }

// True on a settlement day: date divisible by five, or the Friday before one that falls on a weekend.
bool Gotobi(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   return(s.day%5==0 || (s.day_of_week==5 && ((s.day+1)%5==0 || (s.day+2)%5==0)));
  }

// Move through the window of the day starting at 'day' as a fraction of the price. False when that day has no
// bar at the start of the window.
bool WindowMove(datetime day,double &move)
  {
   datetime a=FixTime(day),b=a+InpHoldMin*60;
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

// True when the EA trades on 'day'.
bool TradingDay(datetime day)
  {
   if(InpGotobi!=0 && Gotobi(day)!=(InpGotobi>0))
      return(false);
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

// Closes the position InpHoldMin minutes after the fixing of the day it was opened on.
void Manage()
  {
   datetime opened;
   ulong t=Held(opened);
   if(t==0 || TimeCurrent()<FixTime(opened-opened%86400)+InpHoldMin*60)
      return;
   if(!g_trade.PositionClose(t,InpDeviation))
      PrintFormat("AurumTokyo: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpHoldMin<5 || InpHoldMin%5!=0 || InpHoldMin>1200 || InpGotobi<-1 || InpGotobi>1 || InpDays<2 || InpRiskPct<=0 || InpStopMult<=0 || InpMaxSpread<0 || InpEntrySec<1)
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
   datetime start=FixTime(today);
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
      PrintFormat("AurumTokyo: fewer than %d days of M5 history, no trade today",InpDays/2);
      g_doneDay=today;
      return;
     }
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpMaxSpread*_Point)
      return;                  // tried again until InpEntrySec after the fixing
   double spread=q.ask-q.bid;
   double dist=MathMax(InpStopMult*avg*q.bid,SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point+spread);
   double lots=Lots(-1,q.bid,dist);
   if(lots<=0)
     {
      PrintFormat("AurumTokyo: balance too small for the minimum lot at a stop of %.3f, no trade today",dist);
      g_doneDay=today;
      return;
     }
   // the stop sits 'dist' above the bid, as in the backtest
   double sl=NormalizeDouble(q.bid+dist,_Digits);
   if(!g_trade.Sell(lots,_Symbol,0.0,sl,0.0,"AurumTokyo") || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumTokyo: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat("AurumTokyo: average move %.1f bp, sold %.2f lots at %.3f, stop %.3f, %d s after the fixing, closes at %s",
               1e4*avg,lots,g_trade.ResultPrice(),sl,(int)(now-start),TimeToString(start+InpHoldMin*60,TIME_MINUTES));
   g_doneDay=today;
  }
//+------------------------------------------------------------------+
