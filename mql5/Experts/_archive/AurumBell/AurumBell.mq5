//+------------------------------------------------------------------+
//| AurumBell.mq5 - fades gold's last move into the New York 16:00   |
//| close (23:00 server time). At the bell the move of the last      |
//| InpLookMin minutes is compared with the average size of the same |
//| move over the previous InpDays days. When it is at least InpK    |
//| times that average, a position is opened against it: sell after  |
//| a rise, buy after a fall. It is closed InpHoldMin minutes later, |
//| or earlier at a stop InpStopMult averages away. One trade a day  |
//| at most, never held overnight.                                   |
//| The edge sits in the first minutes after the bell: an entry one  |
//| minute late loses most of it, so no order is sent later than     |
//| InpEntrySec after the bell.                                      |
//| Backtest: tools/backtest_bell.py                                 |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpBellHour       = 23;     // Bell, hour (server time; 23 = 16:00 New York)
input int    InpBellMinute     = 0;      // Bell, minute (multiple of 5)
input int    InpLookMin        = 15;     // Move is measured over this many minutes (multiple of 5)
input double InpK              = 1.5;    // Trade when the move is at least this many average moves
input int    InpDays           = 60;     // Days in the average
input int    InpHoldMin        = 10;     // Holding time, minutes

input group "Size and risk guard"
input double InpRiskPct        = 1.0;    // Loss at the stop, % of balance
input double InpStopMult       = 3.0;    // Stop distance, average moves
input double InpMaxSpread      = 0.30;   // No entry while spread is above this, price units
input int    InpEntrySec       = 20;     // No entry later than this after the bell, seconds

input group "Execution"
input long   InpMagic          = 245008; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

CTrade   g_trade;
datetime g_doneDay=0;      // day whose bell has been dealt with

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

// True when a trade of this EA was already opened since 'from' (covers a restart after the bell).
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

// Move into the bell of the day starting at 'day': price at the bell minus the price InpLookMin minutes earlier.
// False when that day has no bar at the bell.
bool BellMove(datetime day,double &move)
  {
   datetime bell=day+InpBellHour*3600+InpBellMinute*60;
   int b=iBarShift(_Symbol,PERIOD_M5,bell,true);
   if(b<0)
      return(false);
   int p=iBarShift(_Symbol,PERIOD_M5,bell-InpLookMin*60-300,false);
   if(p<=b || iTime(_Symbol,PERIOD_M5,p)<day)
      return(false);
   move=iOpen(_Symbol,PERIOD_M5,b)-iClose(_Symbol,PERIOD_M5,p);
   return(true);
  }

// Average size of the move into the bell over the InpDays trading days before 'today'; 0 while history is short.
double AverageMove(datetime today)
  {
   double sum=0.0,move;
   int n=0;
   for(int i=1; i<=2*InpDays+20 && n<InpDays; i++)
      if(BellMove(today-i*86400,move))
        {
         sum+=MathAbs(move);
         n++;
        }
   return(n>=InpDays/2 ? sum/n : 0.0);
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

// Closes the position once it has been held InpHoldMin minutes.
void Manage()
  {
   datetime opened;
   ulong t=Held(opened);
   if(t==0 || TimeCurrent()-opened<InpHoldMin*60)
      return;
   if(!g_trade.PositionClose(t,InpDeviation))
      PrintFormat("AurumBell: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpBellHour<0 || InpBellHour>23 || InpBellMinute<0 || InpBellMinute>55 || InpBellMinute%5!=0 || InpLookMin<5 ||
      InpLookMin%5!=0 || InpK<=0 || InpDays<2 || InpHoldMin<1 || InpRiskPct<=0 || InpStopMult<=0 || InpEntrySec<1)
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
   datetime bell=today+InpBellHour*3600+InpBellMinute*60;
   if(g_doneDay==today || now<bell)
      return;
   datetime opened;
   if(now-bell>=InpEntrySec || Held(opened)!=0 || TradedSince(bell))
     {
      g_doneDay=today;
      return;
     }
   double move;
   if(!BellMove(today,move))
      return;                  // the bar of the bell is not built yet, the next tick tries again
   double avg=AverageMove(today);
   if(avg<=0)
     {
      PrintFormat("AurumBell: fewer than %d days of M5 history, no trade today",InpDays/2);
      g_doneDay=today;
      return;
     }
   if(MathAbs(move)<InpK*avg)
     {
      PrintFormat("AurumBell: move %+.2f is below %.1f x average %.2f, no trade today",move,InpK,avg);
      g_doneDay=today;
      return;
     }
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpMaxSpread)
      return;                  // tried again until InpEntrySec after the bell
   int side=(move>0 ? -1 : 1);
   double spread=q.ask-q.bid;
   double dist=MathMax(InpStopMult*avg,SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point+spread);
   double lots=Lots(side,side>0 ? q.ask : q.bid,dist);
   if(lots<=0)
     {
      PrintFormat("AurumBell: balance too small for the minimum lot at a stop of %.2f, no trade today",dist);
      g_doneDay=today;
      return;
     }
   // the stop sits 'dist' from the bid on both sides, as in the backtest
   double sl=NormalizeDouble(q.bid-side*dist,_Digits);
   bool ok=(side>0 ? g_trade.Buy(lots,_Symbol,0.0,sl,0.0,"AurumBell") : g_trade.Sell(lots,_Symbol,0.0,sl,0.0,"AurumBell"));
   if(!ok || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumBell: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat("AurumBell: move %+.2f against average %.2f, %s %.2f lots at %.2f, stop %.2f, %d s after the bell",
               move,avg,side>0 ? "bought" : "sold",lots,g_trade.ResultPrice(),sl,(int)(now-bell));
   g_doneDay=today;
  }
//+------------------------------------------------------------------+
