//+------------------------------------------------------------------+
//| AurumNoise.mq5 - noise-area intraday momentum on a US stock      |
//| index CFD (Zarattini, Aziz, Barbon 2025, "Beat the Market").     |
//| For each half hour of the New York session the average move from |
//| the 9:30 open over the previous InpDays sessions sets a band     |
//| around the open: upper = max(open, yesterday's 16:00 close) x    |
//| (1 + InpBandMult x average), lower = min(...) x (1 - ...). At    |
//| 10:00, 10:30, ... 15:30 New York the EA buys above the upper band|
//| and sells below the lower one; a long is closed when the price is|
//| under max(upper band, session average price), a short when it is|
//| over min(lower band, session average), and may turn at once.     |
//| Everything is closed at 16:00 New York; nothing is held overnight|
//| Size: equity x InpSizeMult x min(InpMaxLeverage, InpVolTargetPct |
//| / daily volatility of the last InpDays sessions) in notional.    |
//| The session average is the mean of the minute closes since 9:30  |
//| (the backtest has no volume, so not a VWAP).                     |
//| Backtest: research/noise_area_index.py. 2010-2026, at 0.75 bp a |
//| round trip: S&P 500 with InpBandMult 1.5 Sharpe 0.80, Nasdaq with|
//| 1.0 Sharpe 0.78; at 1.5 bp about 0.5. Spread decides it.         |
//| Attach to a US500.cash or US100.cash chart; one chart per index, |
//| each with its own InpMagic. The server clock is taken to follow  |
//| European summer time from UTC+InpServerUtc (FTMO: 2).            |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.01"

#include <Trade\Trade.mqh>

input group "Signal"
input double InpBandMult      = 1.0;    // Band width, multiple of the average move (S&P 500 1.5, Nasdaq 1.0)
input int    InpDays          = 14;     // Sessions in the average move and in the daily volatility
input bool   InpUseAverage    = true;   // Trailing stop also at the session average price

input group "Size"
input double InpVolTargetPct  = 2.0;    // Daily volatility the position is scaled to, %
input double InpMaxLeverage   = 4.0;    // Largest notional, multiple of equity
input double InpSizeMult      = 1.0;    // Multiplies the size

input group "Clock and execution"
input int    InpServerUtc     = 2;      // Server clock in winter, hours from UTC (European summer time adds one)
input bool   InpServerEuDst   = true;   // Server clock follows European summer time
input int    InpCheckSec      = 60;     // A half-hour check is done within this many seconds, else skipped
input double InpMaxSpreadBp   = 3.0;    // No entry while the spread is above this, basis points of price
input long   InpMagic         = 245200; // Magic number
input int    InpDeviation     = 50;     // Max slippage, points

#define OPEN_MIN   570                  // 9:30 New York
#define CLOSE_MIN  960                  // 16:00 New York
#define NCHECK     12                   // 10:00 ... 15:30

CTrade   g_trade;
datetime g_day=0;                       // New York date the arrays below belong to
double   g_sig[NCHECK];                 // average move from the open to each check time
double   g_hi=0,g_lo=0;                 // max and min of today's open and yesterday's close
double   g_lev=0;                       // notional per unit of equity for today
double   g_vol=0;                       // daily volatility of the last InpDays sessions
bool     g_ready=false;                 // today's bands are known
int      g_lastCheck=-1;                // index of the last check dealt with today
bool     g_closed=false;                // the 16:00 close has been done today

//--- clocks ----------------------------------------------------------
int      NthSunday(int year,int mon,int n)       // day of the month of the n-th Sunday (n=-1: last)
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

bool UsDst(datetime utc)                // US daylight saving: 2nd Sunday of March to 1st Sunday of November, 7:00 UTC
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

bool EuDst(datetime utc)                // European summer time: last Sunday of March to last Sunday of October, 1:00 UTC
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

// Hours to add to New York time to get server time at the UTC moment 'utc' (7 most of the year).
int Shift(datetime utc)
  {
   int server=InpServerUtc+((InpServerEuDst && EuDst(utc)) ? 1 : 0);
   int ny=(UsDst(utc) ? -4 : -5);
   return(server-ny);
  }

// Server time of New York date 'nyDay' (midnight) plus 'minute' minutes.
datetime ServerAt(datetime nyDay,int minute)
  {
   datetime approxUtc=nyDay+minute*60+5*3600;
   return(nyDay+minute*60+Shift(approxUtc)*3600);
  }

// New York date (midnight) and minute of the day of server time 'srv'.
datetime NyDay(datetime srv,int &minute)
  {
   datetime utc=srv-(InpServerUtc+1)*3600;              // close enough to pick the right offsets
   datetime ny=srv-Shift(utc)*3600;
   minute=(int)((ny%86400)/60);
   return(ny-ny%86400);
  }

//--- prices ----------------------------------------------------------
// Bid price at New York 'minute' of 'nyDay': the close of the M1 bar that opened a minute earlier,
// else the open of the bar at that minute. False when neither bar exists.
bool PriceAt(datetime nyDay,int minute,double &px)
  {
   datetime t=ServerAt(nyDay,minute);
   int b=iBarShift(_Symbol,PERIOD_M1,t-60,true);
   if(b>=0)
     {
      px=iClose(_Symbol,PERIOD_M1,b);
      return(px>0);
     }
   b=iBarShift(_Symbol,PERIOD_M1,t,true);
   if(b<0)
      return(false);
   px=iOpen(_Symbol,PERIOD_M1,b);
   return(px>0);
  }

// Mean of the minute prices from 9:30 to 'minute' today (the session average used as a trailing stop).
double SessionAverage(datetime nyDay,int minute)
  {
   double c[];
   datetime from=ServerAt(nyDay,OPEN_MIN-1),to=ServerAt(nyDay,minute-1);
   int n=CopyClose(_Symbol,PERIOD_M1,from,to,c);
   if(n<=0)
      return(0.0);
   double s=0.0;
   for(int i=0; i<n; i++)
      s+=c[i];
   return(s/n);
  }

// Bands for New York date 'today': average moves at the check times over the previous InpDays sessions,
// today's open and yesterday's close, and the day's leverage. False while history is short.
bool Prepare(datetime today)
  {
   double sum[NCHECK],closes[];
   ArrayInitialize(sum,0.0);
   ArrayResize(closes,0);
   int n=0;
   double prevClose=0.0;
   for(int k=1; k<=3*InpDays+15 && n<=InpDays; k++)
     {
      datetime d=today-k*86400;
      MqlDateTime t;
      TimeToStruct(d,t);
      if(t.day_of_week==0 || t.day_of_week==6)
         continue;
      double o,c;
      if(!PriceAt(d,OPEN_MIN,o) || !PriceAt(d,CLOSE_MIN,c))
         continue;                                       // a holiday or a gap in the history
      if(prevClose==0.0)
         prevClose=c;
      int m=ArraySize(closes);
      ArrayResize(closes,m+1);
      closes[m]=c;
      if(n<InpDays)
        {
         bool full=true;
         double mv[NCHECK];
         for(int j=0; j<NCHECK && full; j++)
           {
            double p;
            full=PriceAt(d,OPEN_MIN+30*(j+1),p);
            if(full)
               mv[j]=MathAbs(p/o-1.0);
           }
         if(!full)
            continue;
         for(int j=0; j<NCHECK; j++)
            sum[j]+=mv[j];
        }
      n++;
     }
   if(n<InpDays || ArraySize(closes)<InpDays+1)
      return(false);
   for(int j=0; j<NCHECK; j++)
      g_sig[j]=sum[j]/InpDays;
   // daily volatility from the last InpDays close-to-close returns (closes[] runs backwards in time)
   double r[],mean=0.0,var=0.0;
   ArrayResize(r,InpDays);
   for(int i=0; i<InpDays; i++)
     {
      r[i]=closes[i]/closes[i+1]-1.0;
      mean+=r[i];
     }
   mean/=InpDays;
   for(int i=0; i<InpDays; i++)
      var+=(r[i]-mean)*(r[i]-mean);
   double vol=MathSqrt(var/(InpDays-1));
   if(vol<=0)
      return(false);
   double open;
   if(!PriceAt(today,OPEN_MIN,open))
      return(false);
   g_hi=MathMax(open,prevClose);
   g_lo=MathMin(open,prevClose);
   g_lev=InpSizeMult*MathMin(InpMaxLeverage,InpVolTargetPct/100.0/vol);
   g_vol=vol;
   PrintFormat("AurumNoise: %s open %.2f, yesterday %.2f, daily volatility %.2f%%, notional %.2fx equity, band at 10:00 %.3f%%",
               TimeToString(today,TIME_DATE),open,prevClose,100*vol,g_lev,100*InpBandMult*g_sig[0]);
   return(true);
  }

//--- orders ----------------------------------------------------------
int Side()                              // +1 long, -1 short, 0 flat (positions of this EA on this symbol)
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
         PrintFormat("AurumNoise: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         ok=false;
        }
     }
   return(ok);
  }

// Lots for a notional of g_lev x equity; 0 below the minimum lot.
double Lots(int side,double price)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double pnl,margin;
   if(!OrderCalcProfit(type,_Symbol,1.0,price,price*(1.0+0.01*side),pnl) || pnl<=0)
      return(0.0);
   double notional=pnl/0.01;                             // account currency per lot
   double lots=AccountInfoDouble(ACCOUNT_EQUITY)*g_lev/notional;
   if(OrderCalcMargin(type,_Symbol,1.0,price,margin) && margin>0)
      lots=MathMin(lots,0.9*AccountInfoDouble(ACCOUNT_MARGIN_FREE)/margin);
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

void Open(int side,double ub,double lb)
  {
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<=0)
      return;
   if((q.ask-q.bid)/q.bid*1e4>InpMaxSpreadBp)
     {
      PrintFormat("AurumNoise: spread %.1f bp above %.1f, no entry",(q.ask-q.bid)/q.bid*1e4,InpMaxSpreadBp);
      return;
     }
   double lots=Lots(side,side>0 ? q.ask : q.bid);
   if(lots<=0)
     {
      Print("AurumNoise: equity too small for the minimum lot, no entry");
      return;
     }
   // a broker stop three daily volatilities away, only against a lost connection; the band and average exits trade
   double px=(side>0 ? q.ask : q.bid);
   double sl=NormalizeDouble(px*(1.0-side*3.0*g_vol),(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS));
   bool ok=(side>0 ? g_trade.Buy(lots,_Symbol,0.0,sl,0.0,"AurumNoise") : g_trade.Sell(lots,_Symbol,0.0,sl,0.0,"AurumNoise"));
   if(!ok || g_trade.ResultDeal()==0)
      PrintFormat("AurumNoise: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
   else
      PrintFormat("AurumNoise: %s %.2f lots at %.2f, bands %.2f / %.2f",side>0 ? "bought" : "sold",lots,g_trade.ResultPrice(),ub,lb);
  }

//--- main ------------------------------------------------------------
void Run()
  {
   datetime now=TimeCurrent();
   int minute;
   datetime today=NyDay(now,minute);
   if(today!=g_day)
     {
      g_day=today;
      g_ready=false;
      g_lastCheck=-1;
      g_closed=false;
     }
   if(minute>=CLOSE_MIN)
     {
      if(!g_closed && Side()!=0)
         g_closed=CloseAll();
      else
         g_closed=true;
      return;
     }
   if(minute<OPEN_MIN+30)
      return;
   int j=(minute-OPEN_MIN)/30-1;                        // index of the latest check time reached
   if(j<0 || j>=NCHECK || j<=g_lastCheck)
      return;
   datetime at=ServerAt(today,OPEN_MIN+30*(j+1));
   if(now-at>InpCheckSec)
     {
      g_lastCheck=j;                                    // too late for this check
      return;
     }
   if(!g_ready)
     {
      g_ready=Prepare(today);
      if(!g_ready)
        {
         PrintFormat("AurumNoise: not enough M1 history for %d sessions, no trading today",InpDays);
         g_lastCheck=NCHECK;
         return;
        }
     }
   g_lastCheck=j;
   MqlTick q;
   if(!SymbolInfoTick(_Symbol,q) || q.bid<=0)
      return;
   double px=q.bid;
   double ub=g_hi*(1.0+InpBandMult*g_sig[j]),lb=g_lo*(1.0-InpBandMult*g_sig[j]);
   double avg=(InpUseAverage ? SessionAverage(today,OPEN_MIN+30*(j+1)) : 0.0);
   int side=Side();
   if(side!=0)
     {
      double stop=(side>0 ? (avg>0 ? MathMax(ub,avg) : ub) : (avg>0 ? MathMin(lb,avg) : lb));
      if(!InpUseAverage)
         stop=(side>0 ? lb : ub);
      if((side>0 && px<stop) || (side<0 && px>stop))
        {
         if(!CloseAll())
            return;
         side=0;
        }
     }
   if(side==0)
     {
      if(px>ub)
         Open(1,ub,lb);
      else if(px<lb)
         Open(-1,ub,lb);
     }
  }

int OnInit()
  {
   if(InpBandMult<=0 || InpDays<5 || InpVolTargetPct<=0 || InpMaxLeverage<=0 || InpSizeMult<=0 || InpCheckSec<5 ||
      InpMaxSpreadBp<=0)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   iBars(_Symbol,PERIOD_M1);                             // starts loading the minute history
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
