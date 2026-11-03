//+------------------------------------------------------------------+
//|                                                  AurumLegion.mq5 |
//| Six bots in one EA, each over its own list of symbols:           |
//|   1 GRID       fades the distance of the hourly close from a     |
//|                moving average, one level per step, with a        |
//|                stop-out beyond the last level                    |
//|   2 MARTINGALE fades a large M15 bar and adds larger levels      |
//|                while price keeps going against it                |
//|   3 TICK       trades a burst of a few seconds and holds for     |
//|                seconds                                           |
//|   4 SCALP      fades an M5 close outside its band, exits at the  |
//|                average                                           |
//|   5 DAY        timed windows, each "symbol, clock, start, end,   |
//|                side, days, risk"                                 |
//|   6 HOLD       long (or short) with the trend of the daily       |
//|                closes, held for weeks to months                  |
//| A bot whose symbol list is empty or whose size is 0 is off.      |
//+------------------------------------------------------------------+
#property copyright "AurumLegion"
#property version   "1.00"
#property description "Grid, martingale, tick, scalp, day and hold bots over lists of symbols."

#include <Trade\Trade.mqh>

input group "Overall"
input long   InpMagic           = 772000; // First magic number (6000 numbers are used)
input double InpSizeMult        = 1.0;    // Every size below is multiplied by this
input double InpMarginPct       = 50.0;   // Margin cap of one order, % of free margin
input double InpMaxSpreadBp     = 3.0;    // No entry while spread is above this, 1/100 % of price
input int    InpDeviation       = 30;     // Largest slippage of an order, points
input double InpMaxDrawdownPct  = 35.0;   // Close everything and stop after this equity drawdown from the peak, %

input group "1 Grid (hourly closes)"
input string InpGridSymbols     = "AUDCAD.pc"; // Symbols, comma separated (empty = off)
input double InpGridRiskPct     = 3.5;    // Loss of one symbol's grid at its stop-out, % of balance (0 = off)
input int    InpGridLevels      = 4;      // Levels on each side of the average (1 to 8)
input int    InpGridMaDays      = 5;      // Days in the average the grid is centred on
input double InpGridStep        = 1.0;    // Distance between levels, daily volatilities
input int    InpGridVolDays     = 40;     // Days in the volatility estimate
input double InpGridMult        = 1.0;    // Size of each further level, multiple of the one before (martingale above 1)
input double InpGridPanic       = 1.0;    // Between hourly closes: stop out this many steps beyond the stop-out level (0 = off)

input group "2 Martingale (fade of a large M15 bar)"
input string InpMartSymbols     = "";     // Symbols, comma separated (empty = off)
input double InpMartRiskPct     = 1.0;    // Loss of one basket at its stop-out, % of balance (0 = off)
input double InpMartSigma       = 3.0;    // Size of the bar that starts a basket, standard deviations
input int    InpMartWindow      = 96;     // M15 returns used for the standard deviation
input int    InpMartLevels      = 3;      // Levels of a basket (1 to 8)
input double InpMartStep        = 2.0;    // Distance between levels, standard deviations
input double InpMartMult        = 1.5;    // Size of each further level, multiple of the one before
input int    InpMartHoldBars    = 16;     // Longest life of a basket, M15 bars
input bool   InpMartLongOnly    = true;   // Only buy after a fall
input int    InpMartFromHour    = 2;      // Earliest hour of the bar, server time
input int    InpMartToHour      = 21;     // Latest hour of the bar, server time

input group "3 Tick (bursts of seconds)"
input string InpTickSymbols     = "";     // Symbols, comma separated (empty = off)
input double InpTickRiskPct     = 0.25;   // Loss at the stop, % of balance (0 = off)
input int    InpTickWindowSec   = 10;     // The burst is measured over this many seconds
input double InpTickK           = 5.0;    // Trade when the burst is at least this many average moves
input bool   InpTickFollow      = false;  // true: trade with the burst, false: against it
input int    InpTickHoldSec     = 60;     // Holding time, seconds
input double InpTickStop        = 1.0;    // Stop distance, multiples of the burst
input double InpTickMaxSpreadBp = 0.6;    // No entry while spread is above this, 1/100 % of price

input group "4 Scalp (M5 band)"
input string InpScalpSymbols    = "";     // Symbols, comma separated (empty = off)
input double InpScalpRiskPct    = 0.5;    // Loss at the stop, % of balance (0 = off)
input int    InpScalpBars       = 20;     // M5 closes in the average and the band
input double InpScalpK          = 2.5;    // Trade when the close is this many standard deviations from the average
input double InpScalpStop       = 2.0;    // Stop distance, standard deviations
input int    InpScalpHoldBars   = 12;     // Longest holding time, M5 bars
input int    InpScalpFromHour   = 9;      // Earliest hour of an entry, server time
input int    InpScalpToHour     = 20;     // Latest hour of an entry, server time

input group "5 Day (timed windows)"
// symbol, clock (S server, L London, T Tokyo), start HHMM, end HHMM, side (B buy, S sell),
// days (A every weekday, G settlement days 5th, 10th, ...), loss at the stop in % of balance
input string InpDayWindows      = "USDJPY.pc,T,955,1125,S,G,2.0;EURUSD.pc,L,1130,1300,S,A,1.0"; // Windows, separated by ;
input int    InpDayAvgDays      = 60;     // Days in the average move of a window
input double InpDayStop         = 3.0;    // Stop distance, average moves of the window
input int    InpDayEntrySec     = 60;     // No entry later than this after a window opens, seconds

input group "6 Hold (weeks to months)"
input string InpHoldSymbols     = "XAUUSD.pc"; // Symbols, comma separated (empty = off)
input double InpHoldVolPct      = 10.7;   // Annual volatility one position is scaled to, % (0 = off)
input double InpHoldMaxLeverage = 3.0;    // Maximum notional of one position, multiple of equity
input double InpHoldBand        = 0.25;   // Resize only when the size is off by more than this fraction
input bool   InpHoldLongOnly    = true;   // Never hold short
input int    InpHoldHHMM        = 105;    // Checked once a day from this time, HHMM server time

#define GRID   0
#define MART   1
#define TICK   2
#define SCALP  3
#define DAY    4
#define HOLD   5
#define BOTS   6
#define MAXS   12            // symbols of one bot, and day windows
#define LV_MAX 8             // levels of a grid or basket
#define RING   512           // mid prices kept per symbol by the tick bot
#define VOL_BARS 250

struct Window
  {
   string            sym;
   int               clock;   // 0 server, 1 London, 2 Tokyo
   int               start;   // minutes after midnight on that clock
   int               end;
   int               side;
   bool              gotobi;
   double            risk;
   datetime          done;    // day that has been dealt with
  };

CTrade   g_trade;
double   g_peak=0.0;
bool     g_halted=false;
string   g_sym[BOTS][MAXS];
int      g_n[BOTS];
datetime g_note[BOTS][MAXS];   // day of the last problem report
// grid
datetime g_gBar[MAXS];         // H1 bar whose close has been dealt with
bool     g_gSet[MAXS];         // a target has been worked out since the start
int      g_gTarget[MAXS];      // levels the grid should hold, + long, - short
double   g_gMa[MAXS];          // average of the log price at the last hourly close
double   g_gStep[MAXS];        // one step at the last hourly close, in log price
// martingale and scalp
datetime g_mBar[MAXS];         // M15 bar that has been dealt with
datetime g_sBar[MAXS];         // M5 bar that has been dealt with
// tick
long     g_tT[MAXS][RING];     // time of each kept mid price, ms
double   g_tP[MAXS][RING];
int      g_tHead[MAXS];        // samples written so far
double   g_tAvg[MAXS];         // running average of the absolute move over one window
int      g_tSeen[MAXS];        // windows in that average
long     g_tMark[MAXS];        // time of the last update of the average, ms
// day and hold
Window   g_win[MAXS];
int      g_wins=0;
datetime g_hDay[MAXS];         // day whose hold check is done

int HHMM(datetime t)
  {
   MqlDateTime s;
   TimeToStruct(t,s);
   return(s.hour*100+s.min);
  }

datetime DayOf(datetime t)
  {
   return(t-t%86400);
  }

long Magic(int bot,int i,int level)
  {
   return(InpMagic+bot*1000+i*10+level);
  }

string Key(string sym,string what)
  {
   return(StringFormat("AurumLegion.%I64d.%s.%s",InpMagic,sym,what));
  }

// One report a day at most for each bot and symbol.
void Note(int bot,int i,string text)
  {
   datetime day=DayOf(TimeCurrent());
   if(g_note[bot][i]==day)
      return;
   g_note[bot][i]=day;
   Print("AurumLegion: ",text);
  }

// Points the trade object at one symbol and magic number.
void Prepare(string sym,long magic)
  {
   g_trade.SetExpertMagicNumber(magic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(sym);
  }

// Lots held on 'sym' under 'magic', negative for a short; 'opened' receives the earliest open time.
double HeldLots(string sym,long magic,datetime &opened)
  {
   double lots=0.0;
   opened=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      lots+=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1.0 : -1.0)*PositionGetDouble(POSITION_VOLUME);
      datetime o=(datetime)PositionGetInteger(POSITION_TIME);
      if(opened==0 || o<opened)
         opened=o;
     }
   return(lots);
  }

// Closes every position on 'sym' with a magic number from 'from' to 'to'. Returns false if a close failed.
bool CloseRange(string sym,long from,long to)
  {
   bool ok=true;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0)
         continue;
      string s=PositionGetString(POSITION_SYMBOL);
      long m=PositionGetInteger(POSITION_MAGIC);
      if(m<from || m>to || (sym!="" && s!=sym))
         continue;
      Prepare(s,m);
      if(!g_trade.PositionClose(t))
        {
         PrintFormat("AurumLegion: close on %s failed, retcode %d (%s)",s,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         ok=false;
        }
     }
   return(ok);
  }

bool CloseAll(string sym,long magic)
  {
   return(CloseRange(sym,magic,magic));
  }

// True when a trade was already opened on 'sym' under 'magic' since 'from' (covers a restart inside a window).
bool TradedSince(string sym,long magic,datetime from)
  {
   if(!HistorySelect(from,TimeCurrent()+60))
      return(false);
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d!=0 && HistoryDealGetString(d,DEAL_SYMBOL)==sym && HistoryDealGetInteger(d,DEAL_MAGIC)==magic &&
         HistoryDealGetInteger(d,DEAL_ENTRY)==DEAL_ENTRY_IN)
         return(true);
     }
   return(false);
  }

// Highest level of bot 'bot' on symbol number 'i' that holds a position, + for long, - for short;
// 'last' receives the open price of that level, 'profit' the result of all levels, 'opened' the earliest open time.
int Levels(int bot,int i,double &last,double &profit,datetime &opened)
  {
   int n=0,side=0;
   last=0.0;
   profit=0.0;
   opened=0;
   for(int p=PositionsTotal()-1; p>=0; p--)
     {
      ulong t=PositionGetTicket(p);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=g_sym[bot][i])
         continue;
      long k=PositionGetInteger(POSITION_MAGIC)-Magic(bot,i,0);
      if(k<1 || k>LV_MAX)
         continue;
      profit+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      datetime o=(datetime)PositionGetInteger(POSITION_TIME);
      if(opened==0 || o<opened)
         opened=o;
      if(k>n)
        {
         n=(int)k;
         last=PositionGetDouble(POSITION_PRICE_OPEN);
        }
      side=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1);
     }
   return(side*n);
  }

// 'lots' rounded down to the volume step and cut to the margin cap; 0 when below the minimum lot.
double Round(string sym,int side,double price,double lots)
  {
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP),margin=0.0;
   if(step<=0)
      return(0.0);
   if(OrderCalcMargin(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,sym,1.0,price,margin) && margin>0)
      lots=MathMin(lots,AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

// Lots that lose 'riskPct' of the balance when price goes 'dist' against the position, before rounding.
double RawLots(string sym,int side,double price,double dist,double riskPct)
  {
   double loss;
   if(!OrderCalcProfit(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,sym,1.0,price,price-side*dist,loss) || loss>=0)
      return(0.0);
   return(AccountInfoDouble(ACCOUNT_BALANCE)*InpSizeMult*riskPct/100.0/(-loss));
  }

double RiskLots(string sym,int side,double price,double dist,double riskPct)
  {
   return(Round(sym,side,price,RawLots(sym,side,price,dist,riskPct)));
  }

// The current quote of 'sym'; false when there is none or the spread is above 'maxBp' (0 = any spread).
bool Quote(string sym,double maxBp,MqlTick &q)
  {
   if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0)
      return(false);
   return(maxBp<=0 || (q.ask-q.bid)/q.bid*1e4<=maxBp);
  }

bool Open(string sym,long magic,int side,double lots,double sl,string note)
  {
   Prepare(sym,magic);
   bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,"AurumLegion "+note) : g_trade.Sell(lots,sym,0.0,sl,0.0,"AurumLegion "+note));
   if(!ok || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumLegion: %s order on %s failed, retcode %d (%s)",note,sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return(false);
     }
   PrintFormat("AurumLegion: %s %s %.2f %s at %s",note,side>0 ? "bought" : "sold",lots,sym,
               DoubleToString(g_trade.ResultPrice(),(int)SymbolInfoInteger(sym,SYMBOL_DIGITS)));
   return(true);
  }

// Stop price 'dist' from the bid, never closer than the broker allows.
double StopPrice(string sym,int side,MqlTick &q,double &dist)
  {
   dist=MathMax(dist,SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(sym,SYMBOL_POINT)+q.ask-q.bid);
   return(NormalizeDouble(q.bid-side*dist,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS)));
  }

//--- 1 grid ----------------------------------------------------------

// From the completed hourly bars that open between 1:00 and 22:59 on weekdays: the average 'ma' of the log
// close, one step 'stepLog' in log price, and 'z', the distance of the last close from the average in steps.
bool GridSignal(string sym,double &z,double &ma,double &stepLog)
  {
   int nMa=InpGridMaDays*22,nVol=InpGridVolDays*22;
   int need=MathMax(nMa,nVol+2);
   MqlRates r[];
   ArraySetAsSeries(r,true);
   int got=CopyRates(sym,PERIOD_H1,1,need*24/22+72,r);
   double c[];
   ArrayResize(c,need);
   int n=0;
   for(int i=0; i<got && n<need; i++)
     {
      MqlDateTime s;
      TimeToStruct(r[i].time,s);
      if(s.hour<1 || s.hour>22 || s.day_of_week<1 || s.day_of_week>5 || r[i].close<=0)
         continue;
      c[n++]=MathLog(r[i].close);
     }
   if(n<need)
      return(false);
   ma=0.0;
   for(int i=0; i<nMa; i++)
      ma+=c[i];
   ma/=nMa;
   // the volatility leaves the newest hourly return out, as the backtest does
   double mean=0.0,var=0.0;
   for(int i=1; i<=nVol; i++)
      mean+=c[i]-c[i+1];
   mean/=nVol;
   for(int i=1; i<=nVol; i++)
     {
      double d=c[i]-c[i+1]-mean;
      var+=d*d;
     }
   stepLog=InpGridStep*MathSqrt(var/(nVol-1)*22.0);
   if(stepLog<=0)
      return(false);
   z=(c[0]-ma)/stepLog;
   return(true);
  }

// The grid of symbol number 'i': a new target at every hourly close, then orders until the positions match it.
void Grid(int i)
  {
   string sym=g_sym[GRID][i];
   double last,profit;
   datetime opened;
   int q=Levels(GRID,i,last,profit,opened),L=InpGridLevels;
   bool dead=(GlobalVariableCheck(Key(sym,"dead")) && GlobalVariableGet(Key(sym,"dead"))>0);
   datetime now=TimeCurrent();
   datetime bar=iTime(sym,PERIOD_H1,0),done=iTime(sym,PERIOD_H1,1);
   if(bar!=0 && done!=0 && bar!=g_gBar[i])
     {
      MqlDateTime s;
      TimeToStruct(done,s);
      if(s.hour>=1 && s.hour<=22 && s.day_of_week>=1 && s.day_of_week<=5)
        {
         double z,ma,st;
         if(!GridSignal(sym,z,ma,st))
           {
            Note(GRID,i,"grid, hourly history of "+sym+" is too short or still loading");
            if(now-bar>300)
               g_gBar[i]=bar;
            return;
           }
         int side=(z>0 ? 1 : -1);
         double az=MathAbs(z);
         g_gMa[i]=ma;
         g_gStep[i]=st;
         if(dead)
           {
            if(az<0.5)
              {
               GlobalVariableSet(Key(sym,"dead"),0);
               PrintFormat("AurumLegion: grid, %s is back at its average, the grid is live again",sym);
              }
            g_gTarget[i]=0;
           }
         else if(az>=L+1)
           {
            GlobalVariableSet(Key(sym,"dead"),1);
            g_gTarget[i]=0;
            PrintFormat("AurumLegion: grid stop-out, %s is %.2f steps from its average",sym,z);
           }
         else
           {
            int cur=(q*side<0 ? MathAbs(q) : 0);     // levels already open on this side of the average
            g_gTarget[i]=-side*MathMax(MathMin((int)MathFloor(az),L),MathMin(cur,(int)MathCeil(az)));
           }
         g_gSet[i]=true;
        }
      g_gBar[i]=bar;
     }
   MqlTick tick;
   if(!Quote(sym,0.0,tick))
      return;
   // between hourly closes only a move well beyond the stop-out level is acted on
   if(q!=0 && InpGridPanic>0 && g_gStep[i]>0)
     {
      double z=(MathLog(tick.bid)-g_gMa[i])/g_gStep[i];
      if(z*q<0 && MathAbs(z)>=L+1+InpGridPanic)
        {
         GlobalVariableSet(Key(sym,"dead"),1);
         g_gTarget[i]=0;
         g_gSet[i]=true;
         PrintFormat("AurumLegion: grid stop-out inside the hour, %s is %.2f steps from its average",sym,z);
        }
     }
   int t=g_gTarget[i];
   if(!g_gSet[i] || q==t)
      return;
   if(q!=0 && (t==0 || (q>0)!=(t>0)))
     {
      CloseRange(sym,Magic(GRID,i,1),Magic(GRID,i,LV_MAX));   // the next call opens the other side, if any
      return;
     }
   if(MathAbs(t)<MathAbs(q))
     {
      CloseRange(sym,Magic(GRID,i,MathAbs(t)+1),Magic(GRID,i,LV_MAX));
      return;
     }
   if((tick.ask-tick.bid)/tick.bid*1e4>InpMaxSpreadBp)
      return;
   // the size of a grid cycle is fixed when its first level opens
   double base=(q!=0 && GlobalVariableCheck(Key(sym,"base")) ? GlobalVariableGet(Key(sym,"base")) : 0.0);
   if(base<=0)
     {
      double steps=0.0;
      for(int k=1; k<=L; k++)
         steps+=MathPow(InpGridMult,k-1)*(L+1-k);     // steps lost at the stop-out, in first-level lots
      base=RawLots(sym,1,tick.bid,tick.bid*(1.0-MathExp(-g_gStep[i]))*steps,InpGridRiskPct);
      if(base<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN))
        {
         Note(GRID,i,"grid, balance too small for the minimum lot of "+sym);
         g_gTarget[i]=q;
         return;
        }
      GlobalVariableSet(Key(sym,"base"),base);
     }
   int side=(t>0 ? 1 : -1);
   for(int k=MathAbs(q)+1; k<=MathAbs(t); k++)
     {
      double lots=Round(sym,side,tick.ask,base*MathPow(InpGridMult,k-1));
      if(lots<=0)
        {
         Note(GRID,i,"grid, not enough free margin on "+sym+" for level "+IntegerToString(k));
         g_gTarget[i]=side*(k-1);
         return;
        }
      if(!Open(sym,Magic(GRID,i,k),side,lots,0.0,"grid "+IntegerToString(k)))
         return;
     }
  }

//--- 2 martingale ----------------------------------------------------

// Log return 'r1' of the last completed M15 bar and the standard deviation 'sd' of the InpMartWindow before it.
bool MartSigma(string sym,double &r1,double &sd)
  {
   double c[];
   ArraySetAsSeries(c,true);
   int n=InpMartWindow;
   if(CopyClose(sym,PERIOD_M15,1,n+2,c)<n+2 || c[n+1]<=0)
      return(false);
   r1=MathLog(c[0]/c[1]);
   double mean=0.0,var=0.0;
   for(int i=1; i<=n; i++)
      mean+=MathLog(c[i]/c[i+1]);
   mean/=n;
   for(int i=1; i<=n; i++)
     {
      double d=MathLog(c[i]/c[i+1])-mean;
      var+=d*d;
     }
   sd=MathSqrt(var/(n-1));
   return(sd>0);
  }

// The basket of symbol number 'i': starts against a large M15 bar, adds a larger level each further step against
// it, and ends at break-even once it holds two levels, at the stop-out one step past the last level, or on time.
void Mart(int i)
  {
   string sym=g_sym[MART][i];
   double last,profit;
   datetime opened,now=TimeCurrent();
   int q=Levels(MART,i,last,profit,opened),n=MathAbs(q),L=InpMartLevels;
   MqlTick tick;
   if(!Quote(sym,0.0,tick))
      return;
   if(q!=0)
     {
      int side=(q>0 ? 1 : -1);
      double sd=(GlobalVariableCheck(Key(sym,"sd")) ? GlobalVariableGet(Key(sym,"sd")) : 0.0);
      double against=(sd>0 && last>0 ? -side*MathLog(tick.bid/last)/(InpMartStep*sd) : 0.0);   // steps since the last level
      if(now>=opened+InpMartHoldBars*900 || (n>=2 && profit>=0) || (n>=L && against>=1.0))
        {
         PrintFormat("AurumLegion: martingale basket on %s ends with %d levels, result %.2f",sym,n,profit);
         CloseRange(sym,Magic(MART,i,1),Magic(MART,i,LV_MAX));
         return;
        }
      if(n<L && against>=1.0 && (tick.ask-tick.bid)/tick.bid*1e4<=InpMaxSpreadBp)
        {
         datetime o;
         double first=MathAbs(HeldLots(sym,Magic(MART,i,1),o));
         double lots=Round(sym,side,tick.ask,first*MathPow(InpMartMult,n));
         if(lots>0)
            Open(sym,Magic(MART,i,n+1),side,lots,0.0,"martingale "+IntegerToString(n+1));
         else
            Note(MART,i,"martingale, not enough free margin on "+sym+" for level "+IntegerToString(n+1));
        }
      return;
     }
   datetime bar=iTime(sym,PERIOD_M15,0);
   if(bar==0 || bar==g_mBar[i])
      return;
   g_mBar[i]=bar;
   datetime b1=iTime(sym,PERIOD_M15,1);
   MqlDateTime s;
   TimeToStruct(b1,s);
   double r1,sd;
   if(now-bar>60 || bar-b1!=900 || b1-iTime(sym,PERIOD_M15,2)!=900 || s.hour<InpMartFromHour || s.hour>InpMartToHour ||
      !MartSigma(sym,r1,sd) || MathAbs(r1)<InpMartSigma*sd || (InpMartLongOnly && r1>0))
      return;
   if((tick.ask-tick.bid)/tick.bid*1e4>InpMaxSpreadBp)
      return;
   int side=(r1>0 ? -1 : 1);
   double steps=0.0;
   for(int k=1; k<=L; k++)
      steps+=MathPow(InpMartMult,k-1)*(L+1-k);        // steps lost at the stop-out, in first-level lots
   double lots=RiskLots(sym,side,tick.bid,tick.bid*InpMartStep*sd*steps,InpMartRiskPct);
   if(lots<=0)
     {
      Note(MART,i,"martingale, balance too small for the minimum lot of "+sym);
      return;
     }
   GlobalVariableSet(Key(sym,"sd"),sd);
   Open(sym,Magic(MART,i,1),side,lots,0.0,"martingale 1");
  }

//--- 3 tick ----------------------------------------------------------

// The tick bot of symbol number 'i': keeps the mid prices of the last seconds, and when the move over
// InpTickWindowSec is InpTickK times its usual size, trades it and closes InpTickHoldSec later.
void Tick(int i)
  {
   string sym=g_sym[TICK][i];
   long magic=Magic(TICK,i,0);
   datetime opened;
   bool held=(HeldLots(sym,magic,opened)!=0);
   if(held && TimeCurrent()>=opened+InpTickHoldSec)
     {
      CloseAll(sym,magic);
      return;
     }
   MqlTick q;
   if(!Quote(sym,0.0,q))
      return;
   double mid=0.5*(q.bid+q.ask);
   int h=g_tHead[i];
   long prev=(h>0 ? g_tT[i][(h-1)%RING] : 0);
   if(q.time_msc<prev+50)
      return;                  // nothing new, or less than 50 ms after the last kept price
   g_tT[i][h%RING]=q.time_msc;
   g_tP[i][h%RING]=mid;
   g_tHead[i]=h+1;
   // the oldest kept price inside the window
   long from=q.time_msc-(long)InpTickWindowSec*1000;
   int back=0;
   for(int k=1; k<RING && k<=h; k++)
     {
      if(g_tT[i][(h-k)%RING]<from)
         break;
      back=k;
     }
   if(back==0 || q.time_msc-g_tT[i][(h-back)%RING]<(long)InpTickWindowSec*500)
      return;                  // less than half a window of prices, as after a pause
   double move=mid-g_tP[i][(h-back)%RING];
   double avg=g_tAvg[i];
   bool ready=(g_tSeen[i]>=60);
   if(q.time_msc>=g_tMark[i]+(long)InpTickWindowSec*1000)
     {
      g_tAvg[i]=(g_tSeen[i]==0 ? MathAbs(move) : avg+(MathAbs(move)-avg)/MathMin(g_tSeen[i]+1,300));
      g_tSeen[i]++;
      g_tMark[i]=q.time_msc;
     }
   double spread=q.ask-q.bid;
   if(held || !ready || avg<=0 || MathAbs(move)<InpTickK*avg || spread/q.bid*1e4>InpTickMaxSpreadBp || spread>0.5*MathAbs(move))
      return;
   int side=(move>0 ? 1 : -1)*(InpTickFollow ? 1 : -1);
   double dist=InpTickStop*MathAbs(move);
   double sl=StopPrice(sym,side,q,dist);
   double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,InpTickRiskPct);
   if(lots<=0)
     {
      Note(TICK,i,"tick, balance too small for the minimum lot of "+sym);
      return;
     }
   Open(sym,magic,side,lots,sl,"tick");
  }

//--- 4 scalp ---------------------------------------------------------

// The scalper of symbol number 'i', once per M5 bar: fades a close outside the band, exits back at the average.
void Scalp(int i)
  {
   string sym=g_sym[SCALP][i];
   long magic=Magic(SCALP,i,0);
   datetime opened,now=TimeCurrent();
   double held=HeldLots(sym,magic,opened);
   if(held!=0 && now>=opened+InpScalpHoldBars*300)
     {
      CloseAll(sym,magic);
      return;
     }
   datetime bar=iTime(sym,PERIOD_M5,0);
   if(bar==0 || bar==g_sBar[i])
      return;
   double c[];
   ArraySetAsSeries(c,true);
   int n=InpScalpBars;
   if(CopyClose(sym,PERIOD_M5,1,n,c)<n)
      return;
   g_sBar[i]=bar;
   double mean=0.0,var=0.0;
   for(int k=0; k<n; k++)
      mean+=c[k];
   mean/=n;
   for(int k=0; k<n; k++)
      var+=(c[k]-mean)*(c[k]-mean);
   double sd=MathSqrt(var/(n-1));
   if(held!=0)
     {
      if((c[0]-mean)*held>=0)
         CloseAll(sym,magic);
      return;
     }
   MqlDateTime s;
   TimeToStruct(now,s);
   MqlTick q;
   if(sd<=0 || now-bar>60 || s.day_of_week<1 || s.day_of_week>5 || s.hour<InpScalpFromHour || s.hour>InpScalpToHour ||
      MathAbs(c[0]-mean)<InpScalpK*sd || !Quote(sym,InpMaxSpreadBp,q))
      return;
   int side=(c[0]>mean ? -1 : 1);
   double dist=InpScalpStop*sd;
   double sl=StopPrice(sym,side,q,dist);
   double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,InpScalpRiskPct);
   if(lots<=0)
     {
      Note(SCALP,i,"scalp, balance too small for the minimum lot of "+sym);
      return;
     }
   Open(sym,magic,side,lots,sl,"scalp");
  }

//--- 5 day -----------------------------------------------------------

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

// 1 while the United States is on summer time on 'day', else 0.
int UsSummer(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   return(day>=Sunday(s.year,3,2) && day<Sunday(s.year,11,1) ? 1 : 0);
  }

// Minutes the server clock (New York + 7 h) is ahead of clock 'clock' on 'day'.
int ClockOffset(int clock,datetime day)
  {
   if(clock==0)
      return(0);
   if(clock==2)
      return(-420+60*UsSummer(day));                 // Tokyo
   MqlDateTime s;
   TimeToStruct(day,s);
   int uk=(day>=Sunday(s.year,3,-1) && day<Sunday(s.year,10,-1) ? 1 : 0);
   return(120+60*(UsSummer(day)-uk));                // London
  }

// Server time of minute 'minute' of window 'w' on 'day'.
datetime WinTime(int w,datetime day,int minute)
  {
   return(day+(minute+ClockOffset(g_win[w].clock,day))*60);
  }

// True when window 'w' trades on 'day': a weekday, and for a settlement window a date divisible by five,
// or the Friday before one that falls on the weekend.
bool WinDay(int w,datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   if(s.day_of_week<1 || s.day_of_week>5)
      return(false);
   if(!g_win[w].gotobi)
      return(true);
   return(s.day%5==0 || (s.day_of_week==5 && ((s.day+1)%5==0 || (s.day+2)%5==0)));
  }

// Move of window 'w' on 'day' from its start to its end, as a fraction of the price; false without bars.
bool WinMove(int w,datetime day,double &move)
  {
   string sym=g_win[w].sym;
   int s=iBarShift(sym,PERIOD_M5,WinTime(w,day,g_win[w].start),true);
   if(s<0)
      return(false);
   int e=iBarShift(sym,PERIOD_M5,WinTime(w,day,g_win[w].end)-300,false);
   double open=iOpen(sym,PERIOD_M5,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(sym,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// Average size of the move of window 'w' over the InpDayAvgDays trading days before 'today'; 0 while history is short.
double WinAverage(int w,datetime today)
  {
   double sum=0.0,move;
   int n=0;
   for(int i=1; i<=2*InpDayAvgDays+20 && n<InpDayAvgDays; i++)
      if(WinMove(w,today-i*86400,move))
        {
         sum+=MathAbs(move);
         n++;
        }
   return(n>=InpDayAvgDays/2 ? sum/n : 0.0);
  }

// Window 'w': closes its position at the end and opens one at the start.
void Day(int w)
  {
   string sym=g_win[w].sym;
   long magic=Magic(DAY,w,0);
   datetime now=TimeCurrent(),opened;
   bool held=(HeldLots(sym,magic,opened)!=0);
   if(held && now>=WinTime(w,DayOf(opened),g_win[w].end))
      CloseAll(sym,magic);
   datetime today=DayOf(now);
   datetime start=WinTime(w,today,g_win[w].start);
   if(g_win[w].done==today || now<start)
      return;
   if(!WinDay(w,today) || now-start>=InpDayEntrySec || held || TradedSince(sym,magic,start))
     {
      g_win[w].done=today;
      return;
     }
   double avg=WinAverage(w,today);
   if(avg<=0)
     {
      PrintFormat("AurumLegion: day, fewer than %d days of M5 history on %s, no trade today",InpDayAvgDays/2,sym);
      g_win[w].done=today;
      return;
     }
   MqlTick q;
   if(!Quote(sym,InpMaxSpreadBp,q))
      return;                  // tried again until the entry time has run out
   int side=g_win[w].side;
   double dist=InpDayStop*avg*q.bid;
   double sl=StopPrice(sym,side,q,dist);
   double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,g_win[w].risk);
   if(lots<=0)
      PrintFormat("AurumLegion: day, balance too small for the minimum lot of %s, no trade today",sym);
   else if(!Open(sym,magic,side,lots,sl,"day"))
      return;
   g_win[w].done=today;
  }

// Reads InpDayWindows into g_win. Returns false when an entry is malformed.
bool ReadWindows()
  {
   string rows[],f[];
   int n=StringSplit(InpDayWindows,';',rows);
   g_wins=0;
   for(int r=0; r<n; r++)
     {
      StringTrimLeft(rows[r]);
      StringTrimRight(rows[r]);
      if(rows[r]=="")
         continue;
      if(StringSplit(rows[r],',',f)!=7 || g_wins>=MAXS)
        {
         PrintFormat("AurumLegion: day window '%s' needs 7 fields, and at most %d windows are read",rows[r],MAXS);
         return(false);
        }
      for(int k=0; k<7; k++)
        {
         StringTrimLeft(f[k]);
         StringTrimRight(f[k]);
        }
      int a=(int)StringToInteger(f[2]),b=(int)StringToInteger(f[3]);
      Window w;
      w.sym=f[0];
      w.clock=(f[1]=="S" ? 0 : f[1]=="L" ? 1 : f[1]=="T" ? 2 : -1);
      w.start=a/100*60+a%100;
      w.end=b/100*60+b%100;
      w.side=(f[4]=="B" ? 1 : f[4]=="S" ? -1 : 0);
      w.gotobi=(f[5]=="G");
      w.risk=StringToDouble(f[6]);
      w.done=0;
      if(w.clock<0 || w.side==0 || (f[5]!="G" && f[5]!="A") || w.start%5!=0 || w.end%5!=0 || w.end<w.start+5 ||
         w.end>1260 || w.risk<0)
        {
         PrintFormat("AurumLegion: day window '%s' is not valid",rows[r]);
         return(false);
        }
      if(w.risk<=0)
         continue;
      if(!SymbolSelect(w.sym,true))
        {
         PrintFormat("AurumLegion: symbol %s is not available, its day window is left out",w.sym);
         continue;
        }
      iBars(w.sym,PERIOD_M5);
      g_win[g_wins++]=w;
     }
   return(true);
  }

//--- 6 hold ----------------------------------------------------------

// Annual volatility of 'sym' from completed daily closes 'c' (newest first), exponentially weighted with span 40.
double DailyVol(const double &c[])
  {
   double decay=1.0-2.0/41.0,w=1.0,sw=0.0,mean=0.0,var=0.0;
   for(int i=0; i<VOL_BARS; i++)
     {
      mean+=w*(c[i]/c[i+1]-1.0);
      sw+=w;
      w*=decay;
     }
   mean/=sw;
   w=1.0;
   for(int i=0; i<VOL_BARS; i++)
     {
      double r=c[i]/c[i+1]-1.0-mean;
      var+=w*r*r;
      w*=decay;
     }
   return(MathSqrt(var/sw*252.0));
  }

// Once a day for symbol number 'i': a position in proportion to how many of the 20, 60, 120 and 250-day
// returns are positive, scaled to InpHoldVolPct of annual volatility.
void Hold(int i)
  {
   string sym=g_sym[HOLD][i];
   datetime now=TimeCurrent(),day=DayOf(now),opened;
   long magic=Magic(HOLD,i,0);
   MqlDateTime s;
   TimeToStruct(now,s);
   if(g_hDay[i]==day || HHMM(now)<InpHoldHHMM || s.day_of_week<1 || s.day_of_week>5)
      return;
   double held=HeldLots(sym,magic,opened);
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(sym,PERIOD_D1,1,VOL_BARS+2,c)<VOL_BARS+2 || c[VOL_BARS+1]<=0)
      return;
   double vol=DailyVol(c);
   int look[4]={20,60,120,250};
   double sig=0.0;
   for(int k=0; k<4; k++)
      sig+=(c[0]>c[look[k]] ? 0.25 : c[0]<c[look[k]] ? -0.25 : 0.0);
   if(InpHoldLongOnly)
      sig=MathMax(sig,0.0);
   MqlTick q;
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double tickValue=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(vol<=0 || !Quote(sym,0.0,q) || step<=0 || tickSize<=0 || tickValue<=0)
      return;
   double lev=InpSizeMult*sig*MathMin(InpHoldMaxLeverage,InpHoldVolPct/100.0/vol);
   double target=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*MathAbs(lev)/(q.ask/tickSize*tickValue)/step+1e-9)*step;
   target=MathMin(target,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
   target=(target<vmin ? 0.0 : (lev>0 ? target : -target));
   if(held!=0 && target*held<0)
     {
      CloseAll(sym,magic);     // the other side is opened on the next call
      return;
     }
   double diff=NormalizeDouble(MathAbs(target)-MathAbs(held),2);
   if(MathAbs(diff)<vmin || (target!=0 && MathAbs(diff)<=InpHoldBand*MathMax(MathAbs(target),MathAbs(held))))
     {
      g_hDay[i]=day;
      return;
     }
   if(diff>0)
     {
      int side=(target>0 ? 1 : -1);
      if((q.ask-q.bid)/q.bid*1e4>InpMaxSpreadBp)
         return;
      double lots=Round(sym,side,q.ask,diff);
      if(lots>0 && !Open(sym,magic,side,lots,0.0,"hold"))
         return;
     }
   else
     {
      double left=-diff;
      Prepare(sym,magic);
      for(int p=PositionsTotal()-1; p>=0 && left>=vmin; p--)
        {
         ulong t=PositionGetTicket(p);
         if(t==0 || PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=magic)
            continue;
         double v=PositionGetDouble(POSITION_VOLUME);
         double cut=(left>=v || v-left<vmin ? v : NormalizeDouble(left,2));
         if(!(cut>=v ? g_trade.PositionClose(t) : g_trade.PositionClosePartial(t,cut)))
           {
            PrintFormat("AurumLegion: hold close on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
            return;
           }
         left-=cut;
        }
     }
   PrintFormat("AurumLegion: hold %s, trend %+.2f, volatility %.1f%%, position %.2f -> %.2f lots",sym,sig,100.0*vol,held,target);
   g_hDay[i]=day;
  }

//--- the whole EA ----------------------------------------------------

// Reads the symbol list of one bot; a symbol the broker does not have is left out.
void ReadSymbols(int bot,string list,bool on,ENUM_TIMEFRAMES tf)
  {
   string part[];
   g_n[bot]=0;
   int n=(on ? StringSplit(list,',',part) : 0);
   for(int i=0; i<n && g_n[bot]<MAXS; i++)
     {
      StringTrimLeft(part[i]);
      StringTrimRight(part[i]);
      if(part[i]=="")
         continue;
      if(!SymbolSelect(part[i],true))
        {
         PrintFormat("AurumLegion: symbol %s is not available and is left out",part[i]);
         continue;
        }
      iBars(part[i],tf);       // starts loading the bars the bot is built on
      g_sym[bot][g_n[bot]++]=part[i];
     }
  }

// Everything the EA does, called on every tick of the chart and by the timer.
void Run()
  {
   if(g_halted)
      return;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      PrintFormat("AurumLegion: equity %.2f is %.1f%% below the peak %.2f, closing and halting",eq,InpMaxDrawdownPct,g_peak);
      g_halted=CloseRange("",InpMagic,InpMagic+BOTS*1000-1);
      return;
     }
   for(int i=0; i<g_n[TICK]; i++)
      Tick(i);
   for(int i=0; i<g_n[GRID]; i++)
      Grid(i);
   for(int i=0; i<g_n[MART]; i++)
      Mart(i);
   for(int i=0; i<g_n[SCALP]; i++)
      Scalp(i);
   for(int w=0; w<g_wins; w++)
      Day(w);
   for(int i=0; i<g_n[HOLD]; i++)
      Hold(i);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpSizeMult<=0 || InpMarginPct<=0 || InpMaxSpreadBp<=0 || InpDeviation<0 || InpGridRiskPct<0 || InpGridLevels<1 ||
      InpGridLevels>LV_MAX || InpGridMaDays<1 || InpGridStep<=0 || InpGridVolDays<5 || InpGridMult<=0 || InpGridPanic<0 ||
      InpMartRiskPct<0 || InpMartSigma<=0 || InpMartWindow<10 || InpMartLevels<1 || InpMartLevels>LV_MAX ||
      InpMartStep<=0 || InpMartMult<=0 || InpMartHoldBars<1 || InpTickRiskPct<0 || InpTickWindowSec<1 ||
      InpTickWindowSec>20 || InpTickK<=0 || InpTickHoldSec<1 || InpTickStop<=0 || InpTickMaxSpreadBp<=0 ||
      InpScalpRiskPct<0 || InpScalpBars<5 || InpScalpK<=0 || InpScalpStop<=0 || InpScalpHoldBars<1 ||
      InpDayAvgDays<2 || InpDayStop<=0 || InpDayEntrySec<1 || InpHoldVolPct<0 || InpHoldMaxLeverage<=0 || InpHoldBand<0)
      return(INIT_PARAMETERS_INCORRECT);
   ReadSymbols(GRID,InpGridSymbols,InpGridRiskPct>0,PERIOD_H1);
   ReadSymbols(MART,InpMartSymbols,InpMartRiskPct>0,PERIOD_M15);
   ReadSymbols(TICK,InpTickSymbols,InpTickRiskPct>0,PERIOD_M1);
   ReadSymbols(SCALP,InpScalpSymbols,InpScalpRiskPct>0,PERIOD_M5);
   ReadSymbols(HOLD,InpHoldSymbols,InpHoldVolPct>0,PERIOD_D1);
   if(!ReadWindows())
      return(INIT_PARAMETERS_INCORRECT);
   ArrayInitialize(g_note,0);
   ArrayInitialize(g_gBar,0);
   ArrayInitialize(g_gSet,false);
   ArrayInitialize(g_gTarget,0);
   ArrayInitialize(g_gMa,0.0);
   ArrayInitialize(g_gStep,0.0);
   ArrayInitialize(g_mBar,0);
   ArrayInitialize(g_sBar,0);
   ArrayInitialize(g_tHead,0);
   ArrayInitialize(g_tAvg,0.0);
   ArrayInitialize(g_tSeen,0);
   ArrayInitialize(g_tMark,0);
   ArrayInitialize(g_hDay,0);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("AurumLegion: grid on %d symbols, martingale on %d, tick on %d, scalp on %d, %d day windows, hold on %d",
               g_n[GRID],g_n[MART],g_n[TICK],g_n[SCALP],g_wins,g_n[HOLD]);
   // the other symbols' ticks do not call OnTick; the tick bot needs to look several times a second
   if(g_n[TICK]>0)
      EventSetMillisecondTimer(100);
   else
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
