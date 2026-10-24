//+------------------------------------------------------------------+
//| AurumBurst.mq5 - follows a sudden jump of gold for a fraction of |
//| a second. When the mid price has moved InpMove or more within    |
//| InpWindowMs, a market order is sent in the direction of the jump |
//| and closed InpHoldMs later. No stop or target is placed at the   |
//| broker: both are closer than its minimum stop distance.          |
//| The rule only pays when the order is filled at the quote that    |
//| gave the signal, so every order's execution time and slippage    |
//| are measured and printed, and the EA stops for good after        |
//| InpMaxLoss.                                                      |
//| Research: research/hft_feasibility.py                            |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpWindowMs       = 100;    // Jump is measured over this time, ms
input double InpMove           = 1.00;   // Jump of the mid price that triggers a trade, price units
input int    InpHoldMs         = 500;    // Holding time, ms

input group "Size and risk guard"
input double InpLots           = 0.01;   // Lots per trade
input double InpMaxSpread      = 0.30;   // No entry while spread is above this, price units
input int    InpMaxTradesDay   = 300;    // Trades per day, at most
input double InpMaxLoss        = 500.0;  // Stop for good after losing this much, account currency (cents on a cent account)

input group "Execution"
input long   InpMagic          = 245007; // Magic number
input int    InpDeviation      = 10;     // Max slippage, points
input int    InpTimerMs        = 10;     // Exit is checked this often between ticks, ms

#define TICKS 256          // quotes kept for the jump measurement
#define GAP_MS 60000       // quotes older than this are dropped (weekend, reopen)

CTrade   g_trade;
long     g_time[TICKS];    // server time of each kept quote, ms
double   g_mid[TICKS];
int      g_head=-1;        // newest kept quote
int      g_kept=0;
ulong    g_openTick=0;     // local clock when the position was opened, ms
long     g_day=0;
int      g_dayTrades=0;
int      g_trades=0;
double   g_net=0.0;        // realised result of all trades, account currency
double   g_sumExec=0.0;    // execution time of all entry orders, ms
double   g_sumSlip=0.0;    // slippage of all entry orders against the signal quote, price units
bool     g_halted=false;

// Ticket of the position held under the magic number, 0 if none; 'openedMsc' receives its server open time.
ulong Held(long &openedMsc)
  {
   openedMsc=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      openedMsc=PositionGetInteger(POSITION_TIME_MSC);
      return(t);
     }
   return(0);
  }

// Result of a closed position with commission and swap, account currency.
double PositionResult(ulong position)
  {
   double sum=0.0;
   if(!HistorySelectByPosition(position))
      return(0.0);
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d!=0)
         sum+=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_COMMISSION)+
              HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_FEE);
     }
   return(sum);
  }

// Closes the position once it has been held long enough. 'nowMsc' is the server time of the newest quote.
void Manage(long nowMsc)
  {
   long openedMsc;
   ulong t=Held(openedMsc);
   if(t==0)
      return;
   bool due=(g_openTick==0 || GetTickCount64()-g_openTick>=(ulong)InpHoldMs || nowMsc-openedMsc>=InpHoldMs);
   if(!due)
      return;
   if(!g_trade.PositionClose(t,InpDeviation))
     {
      PrintFormat("AurumBurst: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   g_net+=PositionResult(t);
   PrintFormat("AurumBurst: %d trades, net %.2f, entry orders took %.0f ms and slipped %.3f on average",
               g_trades,g_net,g_sumExec/MathMax(g_trades,1),g_sumSlip/MathMax(g_trades,1));
   if(InpMaxLoss>0 && g_net<=-InpMaxLoss)
     {
      PrintFormat("AurumBurst: loss limit %.2f reached, halting",InpMaxLoss);
      g_halted=true;
     }
  }

// Mid price move over the last InpWindowMs; 0 while there is no quote old enough.
double Jump()
  {
   long from=g_time[g_head]-InpWindowMs;
   for(int n=1; n<g_kept; n++)
     {
      int i=(g_head-n+TICKS)%TICKS;
      if(g_time[i]<=from)
         return(g_mid[g_head]-g_mid[i]);
     }
   return(0.0);
  }

void Enter(int side,double bid,double ask)
  {
   double quote=(side>0 ? ask : bid);
   ulong t0=GetMicrosecondCount();
   bool ok=(side>0 ? g_trade.Buy(InpLots,_Symbol,0.0,0.0,0.0,"AurumBurst") : g_trade.Sell(InpLots,_Symbol,0.0,0.0,0.0,"AurumBurst"));
   double ms=(GetMicrosecondCount()-t0)/1000.0;
   if(!ok || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumBurst: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   g_openTick=GetTickCount64();
   g_trades++;
   g_dayTrades++;
   g_sumExec+=ms;
   g_sumSlip+=side*(g_trade.ResultPrice()-quote);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpWindowMs<1 || InpMove<=0 || InpHoldMs<1 || InpLots<=0 || InpTimerMs<1 || InpMaxTradesDay<1)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   EventSetMillisecondTimer(InpTimerMs);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   if(g_head>=0)
      Manage(g_time[g_head]);
  }

void OnTick()
  {
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0)
      return;
   if(g_head>=0 && q.time_msc-g_time[g_head]>GAP_MS)
      g_kept=0;
   g_head=(g_head+1)%TICKS;
   g_time[g_head]=q.time_msc;
   g_mid[g_head]=(q.bid+q.ask)/2.0;
   g_kept=MathMin(g_kept+1,TICKS);
   Manage(q.time_msc);
   long day=q.time_msc/86400000;
   if(day!=g_day)
     {
      g_day=day;
      g_dayTrades=0;
     }
   long openedMsc;
   if(g_halted || g_dayTrades>=InpMaxTradesDay || q.ask-q.bid>InpMaxSpread || Held(openedMsc)!=0)
      return;
   double jump=Jump();
   if(MathAbs(jump)>=InpMove)
      Enter(jump>0 ? 1 : -1,q.bid,q.ask);
  }

double OnTester()
  {
   return(g_net);
  }
//+------------------------------------------------------------------+
