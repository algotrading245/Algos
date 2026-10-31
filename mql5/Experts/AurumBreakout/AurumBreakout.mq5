//+------------------------------------------------------------------+
//| AurumBreakout.mq5 - USD/JPY London breakout of the Asian range.  |
//| Hours are on the "virtual" clock New York + 7 (the histdata       |
//| server clock the backtest uses; a day runs 17:00-17:00 New York). |
//| Range = high and low of virtual 01:00-09:00 (New York 18:00-      |
//| 02:00). From virtual 10:00 a buy stop waits at the range high and |
//| a sell stop at the range low, each with its stop loss at the     |
//| range's other side. InpBothSides (default): each side trades once |
//| a day on its own; off: the first fill cancels the other. All is   |
//| closed and cancelled at virtual 18:00 (New York 11:00). If the    |
//| price is already outside the range at 10:00 the EA enters at      |
//| market in that direction. Days whose range is under InpMinRange or|
//| over InpMaxRange times the average of the last InpFilterDays      |
//| ranges are skipped. Size: InpRiskPct of equity lost at the stop.  |
//| Backtest: research/london_breakout.py. 2010-2026 at 0.8 bp a round|
//| trip: both sides 1.40 to 2017, 1.08 from 2018; first fill only    |
//| 0.96 / 0.98; 0.59 at 1.5 bp. Needs a hedging account.             |
//| The server clock is taken to follow European summer time from    |
//| UTC+InpServerUtc (FTMO: 2).                                       |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.01"

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpRangeFrom     = 1;      // Range start, virtual hour (New York + 7)
input int    InpRangeTo       = 9;      // Range end, virtual hour
input int    InpTradeFrom     = 10;     // Orders placed at this virtual hour
input int    InpTradeTo       = 18;     // Everything flat at this virtual hour
input int    InpFilterDays    = 60;     // Days in the average range
input double InpMinRange      = 0.25;   // Skip a range below this multiple of the average
input double InpMaxRange      = 3.0;    // Skip a range above this multiple of the average
input bool   InpBothSides     = true;   // Each side trades once a day on its own (false: first fill cancels the other)

input group "Size"
input double InpRiskPct       = 0.25;   // Equity lost at the stop, %

input group "Clock and execution"
input int    InpServerUtc     = 2;      // Server clock in winter, hours from UTC (European summer time adds one)
input bool   InpServerEuDst   = true;   // Server clock follows European summer time
input double InpMaxSpreadBp   = 3.0;    // No market entry while the spread is above this, basis points
input long   InpMagic         = 245300; // Magic number
input int    InpDeviation     = 30;     // Max slippage, points

#define VIRT 7                           // virtual clock = New York + 7 hours

CTrade   g_trade;
datetime g_vday=0;                       // virtual date being traded
bool     g_placed=false;                 // today's orders were placed (or the day was skipped)
bool     g_done=false;                   // today's trade is over (filled and closed, or flat time reached)
int      g_orders=0;                     // pending orders placed today; fewer left means one was filled
double   g_hi=0,g_lo=0;

//--- clocks ----------------------------------------------------------
int NthSunday(int year,int mon,int n)    // day of the month of the n-th Sunday (n=-1: last)
  {
   MqlDateTime t;
   ZeroMemory(t);
   t.year=year; t.mon=mon; t.day=1;
   datetime first=StructToTime(t);
   MqlDateTime f;
   TimeToStruct(first,f);
   int d=1+(7-f.day_of_week)%7;
   if(n>0)
      return(d+7*(n-1));
   int dim=(mon==2 ? 28 : (mon==4 || mon==6 || mon==9 || mon==11) ? 30 : 31);
   while(d+7<=dim)
      d+=7;
   return(d);
  }

bool UsDst(datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc,t);
   MqlDateTime a,b;
   ZeroMemory(a);
   ZeroMemory(b);
   a.year=b.year=t.year;
   a.mon=3;  a.day=NthSunday(t.year,3,2);  a.hour=7;
   b.mon=11; b.day=NthSunday(t.year,11,1); b.hour=6;
   return(utc>=StructToTime(a) && utc<StructToTime(b));
  }

bool EuDst(datetime utc)
  {
   MqlDateTime t;
   TimeToStruct(utc,t);
   MqlDateTime a,b;
   ZeroMemory(a);
   ZeroMemory(b);
   a.year=b.year=t.year;
   a.mon=3;  a.day=NthSunday(t.year,3,-1);  a.hour=1;
   b.mon=10; b.day=NthSunday(t.year,10,-1); b.hour=1;
   return(utc>=StructToTime(a) && utc<StructToTime(b));
  }

int Shift(datetime utc)                  // server time minus New York time, hours
  {
   int server=InpServerUtc+((InpServerEuDst && EuDst(utc)) ? 1 : 0);
   int ny=(UsDst(utc) ? -4 : -5);
   return(server-ny);
  }

datetime ServerOf(datetime vday,int minute)   // server time of virtual date 'vday' + 'minute'
  {
   datetime ny=vday+minute*60-VIRT*3600;
   return(ny+Shift(ny+5*3600)*3600);
  }

datetime VirtualDay(datetime srv,int &minute) // virtual date (midnight) and minute of server time 'srv'
  {
   datetime utc=srv-(InpServerUtc+1)*3600;
   datetime v=srv-Shift(utc)*3600+VIRT*3600;
   minute=(int)((v%86400)/60);
   return(v-v%86400);
  }

//--- range -----------------------------------------------------------
bool Range(datetime vday,double &hi,double &lo,double &last)
  {
   double h[],l[],c[];
   datetime from=ServerOf(vday,60*InpRangeFrom),to=ServerOf(vday,60*InpRangeTo)-60;
   int n=CopyHigh(_Symbol,PERIOD_M1,from,to,h);
   if(n<(InpRangeTo-InpRangeFrom)*35 || CopyLow(_Symbol,PERIOD_M1,from,to,l)!=n || CopyClose(_Symbol,PERIOD_M1,from,to,c)!=n)
      return(false);                                     // too little of the session in the history
   hi=h[ArrayMaximum(h)];
   lo=l[ArrayMinimum(l)];
   last=c[n-1];
   return(hi>lo && last>0);
  }

// Today's range relative to the average of the previous InpFilterDays ranges: inside the limits?
bool RangeOk(datetime vday,double width)
  {
   double sum=0.0;
   int n=0;
   for(int k=1; k<=2*InpFilterDays+20 && n<InpFilterDays; k++)
     {
      datetime d=vday-k*86400;
      MqlDateTime t;
      TimeToStruct(d,t);
      if(t.day_of_week==0 || t.day_of_week==6)
         continue;
      double h,l,c;
      if(!Range(d,h,l,c))
         continue;
      sum+=(h-l)/c;
      n++;
     }
   if(n<InpFilterDays/2)
     {
      Print("AurumBreakout: not enough M1 history for the range filter, no trade today");
      return(false);
     }
   double ratio=width/(sum/n);
   PrintFormat("AurumBreakout: range %.3f%%, %.2fx the %d-day average",100*width,ratio,n);
   return(ratio>=InpMinRange && ratio<=InpMaxRange);
  }

//--- orders ----------------------------------------------------------
int Side()
  {
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      return(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1);
     }
   return(0);
  }

int Pending()
  {
   int n=0;
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      ulong t=OrderGetTicket(i);
      if(t!=0 && OrderGetString(ORDER_SYMBOL)==_Symbol && OrderGetInteger(ORDER_MAGIC)==InpMagic)
         n++;
     }
   return(n);
  }

void CancelAll()
  {
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      ulong t=OrderGetTicket(i);
      if(t!=0 && OrderGetString(ORDER_SYMBOL)==_Symbol && OrderGetInteger(ORDER_MAGIC)==InpMagic)
         if(!g_trade.OrderDelete(t))
            PrintFormat("AurumBreakout: cancel failed, retcode %d",g_trade.ResultRetcode());
     }
  }

bool CloseAll()
  {
   bool ok=true;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(!g_trade.PositionClose(t,InpDeviation))
        {
         PrintFormat("AurumBreakout: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         ok=false;
        }
     }
   return(ok);
  }

// Lots that lose InpRiskPct of equity between 'entry' and 'stop'; 0 below the minimum lot.
double Lots(int side,double entry,double stop)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss;
   if(!OrderCalcProfit(type,_Symbol,1.0,entry,stop,loss) || loss>=0)
      return(0.0);
   double lots=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPct/100.0/(-loss);
   double margin;
   if(OrderCalcMargin(type,_Symbol,1.0,entry,margin) && margin>0)
      lots=MathMin(lots,0.9*AccountInfoDouble(ACCOUNT_MARGIN_FREE)/margin);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

void Place(datetime vday)
  {
   double last;
   g_placed=true;
   if(!Range(vday,g_hi,g_lo,last))
     {
      Print("AurumBreakout: no range for today, no trade");
      g_done=true;
      return;
     }
   if(!RangeOk(vday,(g_hi-g_lo)/last))
     {
      g_done=true;
      return;
     }
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0)
     {
      g_placed=false;                                    // try again on the next tick
      return;
     }
   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double hi=NormalizeDouble(g_hi,digits),lo=NormalizeDouble(g_lo,digits);
   double stopsLevel=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point;
   // already broken before the orders could be placed: enter at market, as the backtest fills at the bar's open
   if(q.bid>hi || q.ask<lo)
     {
      int side=(q.bid>hi ? 1 : -1);
      if((q.ask-q.bid)/q.bid*1e4>InpMaxSpreadBp)
        {
         PrintFormat("AurumBreakout: spread %.1f bp above %.1f, no market entry",(q.ask-q.bid)/q.bid*1e4,InpMaxSpreadBp);
         g_done=true;
         return;
        }
      double px=(side>0 ? q.ask : q.bid),sl=(side>0 ? lo : hi);
      double lots=Lots(side,px,sl);
      bool ok=(lots>0 && (side>0 ? g_trade.Buy(lots,_Symbol,0.0,sl,0.0,"AurumBreakout") :
                                   g_trade.Sell(lots,_Symbol,0.0,sl,0.0,"AurumBreakout")));
      PrintFormat("AurumBreakout: range %.3f-%.3f already broken, %s %.2f lots at market %s",lo,hi,side>0 ? "buy" : "sell",
                  lots,ok ? "done" : "failed");
      if(InpBothSides)                                   // the other side keeps its own order
        {
         double lo2=Lots(-side,side>0 ? lo : hi,side>0 ? hi : lo);
         bool ok2=(lo2>0 && (side>0 ? (q.bid-lo>stopsLevel) && g_trade.SellStop(lo2,lo,_Symbol,hi,0.0,ORDER_TIME_GTC,0,"AurumBreakout")
                                    : (hi-q.ask>stopsLevel) && g_trade.BuyStop(lo2,hi,_Symbol,lo,0.0,ORDER_TIME_GTC,0,"AurumBreakout")));
         PrintFormat("AurumBreakout: %s stop %.2f lots %s",side>0 ? "sell" : "buy",lo2,ok2 ? "placed" : "not placed");
         return;
        }
      g_done=true;                                       // that is the day's one trade
      return;
     }
   double lb=Lots(1,hi,lo),ls=Lots(-1,lo,hi);
   if(lb<=0 || ls<=0)
     {
      Print("AurumBreakout: equity too small for the minimum lot, no trade");
      g_done=true;
      return;
     }
   bool okb=(hi-q.ask>stopsLevel) && g_trade.BuyStop(lb,hi,_Symbol,lo,0.0,ORDER_TIME_GTC,0,"AurumBreakout");
   bool oks=(q.bid-lo>stopsLevel) && g_trade.SellStop(ls,lo,_Symbol,hi,0.0,ORDER_TIME_GTC,0,"AurumBreakout");
   PrintFormat("AurumBreakout: range %.3f-%.3f, buy stop %.2f lots %s, sell stop %.2f lots %s",lo,hi,lb,okb ? "placed" : "not placed",
               ls,oks ? "placed" : "not placed");
   g_orders=(okb ? 1 : 0)+(oks ? 1 : 0);
   if(g_orders==0)
      g_done=true;
  }

//--- main ------------------------------------------------------------
void Run()
  {
   int minute;
   datetime vday=VirtualDay(TimeCurrent(),minute);
   if(vday!=g_vday)
     {
      g_vday=vday;
      g_placed=false;
      g_done=false;
      g_orders=0;
     }
   if(minute>=60*InpTradeTo)
     {
      if(Pending()>0)
         CancelAll();
      if(Side()!=0)
         CloseAll();
      g_done=true;
      return;
     }
   if(minute<60*InpTradeFrom)
      return;
   MqlDateTime t;
   TimeToStruct(vday,t);
   if(t.day_of_week==0 || t.day_of_week==6)
      return;
   if(!g_placed)
     {
      Place(vday);
      return;
     }
   // one trade a day: once an order has filled (a position exists, or fewer orders are left than were placed,
   // even if the position was already stopped out between two checks) the other order goes
   if(InpBothSides)
      return;                                            // each order fires once; the rest waits for the flat time
   if(!g_done && (Side()!=0 || Pending()<g_orders))
      g_done=true;
   if(g_done && Pending()>0)
      CancelAll();
  }

int OnInit()
  {
   if(InpRangeFrom<0 || InpRangeTo<=InpRangeFrom || InpTradeFrom<InpRangeTo || InpTradeTo<=InpTradeFrom || InpTradeTo>24 ||
      InpFilterDays<10 || InpMinRange<0 || InpMaxRange<=InpMinRange || InpRiskPct<=0 || InpMaxSpreadBp<=0)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   iBars(_Symbol,PERIOD_M1);
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   Run();
  }

void OnTick()
  {
   Run();
  }
//+------------------------------------------------------------------+
