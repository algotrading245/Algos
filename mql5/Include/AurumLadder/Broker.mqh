//+------------------------------------------------------------------+
//| Broker.mqh - symbol and account specifications, read at run time.|
//+------------------------------------------------------------------+
#ifndef AURUMLADDER_BROKER_MQH
#define AURUMLADDER_BROKER_MQH

struct BrokerSpec
  {
   string            symbol;
   int               digits;
   double            tickSize;
   double            v;          // money per 1.00 lot per 1.00 price move
   double            vmin;
   double            vmax;
   double            step;
   int               lotDigits;
   double            stopsDist;  // broker minimum stop distance, price units
  };

bool AL_LoadBroker(const string symbol,BrokerSpec &b)
  {
   b.symbol   =symbol;
   b.digits   =(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
   b.tickSize =SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
   double tv  =SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
   b.vmin     =SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
   b.vmax     =SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
   b.step     =SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
   double pt  =SymbolInfoDouble(symbol,SYMBOL_POINT);
   b.stopsDist=(double)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL)*pt;
   if(b.tickSize<=0 || tv<=0 || b.step<=0 || b.vmin<=0)
      return(false);
   b.v=tv/b.tickSize;
   b.lotDigits=(int)MathMax(0,MathCeil(-MathLog10(b.step)-1e-9));
   return(true);
  }

bool AL_IsHedging()
  {
   return((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)
          ==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
  }

double AL_NormPrice(const BrokerSpec &b,const double price)
  {
   return(NormalizeDouble(MathRound(price/b.tickSize)*b.tickSize,b.digits));
  }

double AL_NormLot(const BrokerSpec &b,const double lot)
  {
   return(NormalizeDouble(lot,b.lotDigits));
  }

// Margin for 1.00 lot at the current price (the larger of buy and sell).
double AL_MarginPerLot(const BrokerSpec &b)
  {
   double mb=0.0,ms=0.0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY,b.symbol,1.0,SymbolInfoDouble(b.symbol,SYMBOL_ASK),mb))
      return(-1.0);
   if(!OrderCalcMargin(ORDER_TYPE_SELL,b.symbol,1.0,SymbolInfoDouble(b.symbol,SYMBOL_BID),ms))
      return(-1.0);
   return(MathMax(mb,ms));
  }

// Seconds after midnight at which Friday's last trade session ends, or -1.
long AL_FridayCloseSeconds(const string symbol)
  {
   long     latest=-1;
   datetime from,to;
   for(uint i=0; SymbolInfoSessionTrade(symbol,FRIDAY,i,from,to); i++)
      latest=MathMax(latest,(long)to);
   return(latest);
  }

#endif
//+------------------------------------------------------------------+
