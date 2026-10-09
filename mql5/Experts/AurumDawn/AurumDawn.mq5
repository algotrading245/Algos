//+------------------------------------------------------------------+
//| AurumDawn.mq5 - gold session-open drift.                         |
//| Buys at the first quotes of the trading day and closes after a   |
//| fixed hold. One trade a day, long only, no averaging.            |
//| Research: research/session_open_drift.py, tools/backtest_dawn.py |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Timing"
input int    InpEntryWindowSec = 120;   // Enter only within this many seconds of the day's first quote
input int    InpHoldMinutes    = 120;   // Close this long after entry
input bool   InpTradeMonday    = true;  // Trade the Monday open
input bool   InpTradeFriday    = true;  // Trade the Friday open

input group "Size"
input double InpLeverage       = 3.0;   // Position notional as a multiple of equity
input double InpFixedLot       = 0.0;   // Fixed lot (0 = size from leverage)
input double InpMarginPct      = 50.0;  // Margin cap, % of free margin

input group "Risk guard"
input double InpStopPct        = 1.0;   // Protective stop, % below entry (0 = none)
input double InpMaxSpread      = 0.40;  // Skip the day if spread is above this, price units
input double InpMaxDrawdownPct = 20.0;  // Stop trading after this equity drawdown from the peak, %

input group "Execution"
input long   InpMagic          = 245002; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

CTrade   g_trade;
datetime g_day=0;          // server day of the last quote seen
datetime g_firstQuote=0;   // time of that day's first quote
datetime g_tradedDay=0;    // day an entry was already attempted
double   g_peak=0.0;
bool     g_halted=false;

datetime DayOf(const datetime t)
  {
   return(t-(t%86400));
  }

// The day's first quote is only trusted if the EA saw the session start: the current
// M1 bar must be the first one of the day, otherwise a restart at noon would trade.
bool SessionJustOpened(const datetime now)
  {
   return(Bars(_Symbol,PERIOD_M1,DayOf(now),now)<=1+InpEntryWindowSec/60);
  }

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

void Enter()
  {
   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   if(ask<=0 || bid<=0)
      return;
   if(ask-bid>InpMaxSpread)
     {
      PrintFormat("AurumDawn: spread %.2f above %.2f, no trade today",ask-bid,InpMaxSpread);
      return;
     }
   double lot=LotFor(ask);
   if(lot<=0)
     {
      Print("AurumDawn: balance too small for the minimum lot at this leverage, no trade today");
      return;
     }
   double sl=0.0;
   if(InpStopPct>0)
     {
      double minDist=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
      sl=NormalizeDouble(MathMin(bid*(1.0-InpStopPct/100.0),bid-minDist),_Digits);
     }
   if(!g_trade.Buy(lot,_Symbol,0.0,sl,0.0,"AurumDawn"))
      PrintFormat("AurumDawn: buy failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpHoldMinutes<1 || InpEntryWindowSec<1 || (InpLeverage<=0 && InpFixedLot<=0))
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   // Starting mid-session must not look like a session open.
   g_day=DayOf(TimeCurrent());
   g_firstQuote=0;
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
      if(now-opened>=InpHoldMinutes*60)
         if(!g_trade.PositionClose(ticket,InpDeviation))
            PrintFormat("AurumDawn: close failed, retcode %d",g_trade.ResultRetcode());
      return;
     }
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(!g_halted && InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      g_halted=true;
      PrintFormat("AurumDawn: equity %.2f is %.1f%% below the peak %.2f, trading halted",eq,InpMaxDrawdownPct,g_peak);
     }
  }

void OnTimer()
  {
   Manage();
  }

void OnTick()
  {
   datetime now=TimeCurrent();
   datetime day=DayOf(now);
   if(day!=g_day)
     {
      g_day=day;
      g_firstQuote=now;
     }
   Manage();
   if(g_halted || g_firstQuote==0 || g_tradedDay==day)
      return;
   if(now-g_firstQuote>InpEntryWindowSec || !SessionJustOpened(now))
      return;
   MqlDateTime dt;
   TimeToStruct(now,dt);
   if((dt.day_of_week==1 && !InpTradeMonday) || (dt.day_of_week==5 && !InpTradeFriday))
     {
      g_tradedDay=day;
      return;
     }
   ulong ticket; datetime opened;
   if(FindPosition(ticket,opened))
      return;
   g_tradedDay=day;      // one attempt a day, whatever the outcome
   Enter();
  }
//+------------------------------------------------------------------+
