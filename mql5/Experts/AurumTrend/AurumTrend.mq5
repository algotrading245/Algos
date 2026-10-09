//+------------------------------------------------------------------+
//| AurumTrend.mq5 - long-term managed gold exposure.                |
//| Once a day, after the daily bar opens: long while yesterday's    |
//| close is above its moving average, flat otherwise. Size targets  |
//| a fixed annual volatility and is only changed when it is far     |
//| enough from the target. Long only. Most of the return is the     |
//| gold price itself, not a separate edge.                          |
//| Research: research/open_spread_and_trend.py,                     |
//|           tools/backtest_trend.py                                |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpMaPeriod       = 50;    // Moving average of daily closes, days
input double InpVolTargetPct   = 10.0;  // Annual volatility target, %
input int    InpVolSpan        = 30;    // Span of the exponentially weighted daily volatility
input double InpMaxLeverage    = 2.0;   // Maximum position notional as a multiple of equity
input double InpRebalanceBand  = 0.25;  // Resize only when the target differs by this fraction

input group "Risk guard"
input double InpMarginPct      = 50.0;  // Margin cap, % of free margin
input double InpMaxSpread      = 0.50;  // Wait while spread is above this, price units
input double InpMaxDrawdownPct = 25.0;  // Close and stop after this equity drawdown from the peak, %

input group "Execution"
input long   InpMagic          = 245005; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

#define VOL_BARS 250       // daily returns used for the volatility estimate

CTrade   g_trade;
datetime g_bar=0;          // daily bar that has been handled
datetime g_retry=0;        // no new attempt before this time
double   g_peak=0.0;
bool     g_halted=false;

double HeldLots()
  {
   double lots=0.0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      lots+=PositionGetDouble(POSITION_VOLUME);
     }
   return(lots);
  }

// Closes up to 'lots' of this EA's positions. Returns false if a close failed.
bool Reduce(double lots)
  {
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   for(int i=PositionsTotal()-1; i>=0 && lots>step/2; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      double v=PositionGetDouble(POSITION_VOLUME);
      bool ok=(lots>=v-step/2) ? g_trade.PositionClose(t,InpDeviation) : g_trade.PositionClosePartial(t,lots,InpDeviation);
      if(!ok)
        {
         PrintFormat("AurumTrend: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         return(false);
        }
      lots-=MathMin(lots,v);
     }
   return(true);
  }

// Target leverage from completed daily bars; false while history is not available.
bool TargetLeverage(double &lev)
  {
   int need=MathMax(VOL_BARS+1,InpMaPeriod);
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(_Symbol,PERIOD_D1,1,need,c)<need)
      return(false);
   double ma=0.0;
   for(int i=0; i<InpMaPeriod; i++)
      ma+=c[i];
   ma/=InpMaPeriod;
   lev=0.0;
   if(c[0]<=ma)
      return(true);
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

// Brings the position to the day's target. Returns true when nothing is left to do for this bar.
bool Rebalance()
  {
   double lev;
   if(!TargetLeverage(lev))
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
   double held=HeldLots();
   // Money value of one lot at the current price, in account currency.
   double notionalPerLot=ask/tickSize*tickValue;
   double want=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*lev/notionalPerLot/step+1e-9)*step;
   if(want<vmin)
     {
      if(lev>0 && held<=0)
         Print("AurumTrend: balance too small for the minimum lot at this leverage, flat today");
      want=0.0;
     }
   want=MathMin(want,vmax);
   if(want<=0)
      return(held<=0 || Reduce(held));
   if(held>0 && MathAbs(want-held)<=InpRebalanceBand*held)
      return(true);
   if(want<held)
      return(Reduce(held-want));
   double add=want-held,margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,1.0,ask,margin) && margin>0)
      add=MathMin(add,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
   if(add<vmin)
      return(true);
   if(!g_trade.Buy(add,_Symbol,0.0,0.0,0.0,"AurumTrend"))
     {
      PrintFormat("AurumTrend: buy failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return(false);
     }
   PrintFormat("AurumTrend: target leverage %.2f, bought %.2f, now holding %.2f",lev,add,held+add);
   return(true);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpMaPeriod<2 || InpVolSpan<2 || InpVolTargetPct<=0 || InpMaxLeverage<=0 || InpRebalanceBand<0)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
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
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      PrintFormat("AurumTrend: equity %.2f is %.1f%% below the peak %.2f, closing and halting",eq,InpMaxDrawdownPct,g_peak);
      g_halted=Reduce(HeldLots());
      return;
     }
   datetime bar=iTime(_Symbol,PERIOD_D1,0);
   if(bar==0 || bar==g_bar || now<g_retry)
      return;
   if(Rebalance())
      g_bar=bar;
   else
      g_retry=now+60;
  }
//+------------------------------------------------------------------+
