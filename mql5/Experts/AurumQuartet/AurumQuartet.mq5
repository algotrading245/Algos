//+------------------------------------------------------------------+
//| AurumQuartet.mq5 - four unrelated session patterns, one account. |
//| Gold dip: buy gold after a sharp M15 fall in the Asian session,  |
//| held four hours (the dip unit of AurumOrient). The plain long    |
//| through the whole session is an option, off by default.          |
//| Closing bell: fade of gold's last 15 minutes into the New York   |
//| 16:00 close, held 10 minutes (AurumBell).                        |
//| Tokyo fixing: short USD/JPY for 90 minutes after the 9:55 Tokyo  |
//| fixing on settlement days (AurumTokyo).                          |
//| Midday: short EUR/USD, 11:30 to 13:00 London (AurumMeridian).    |
//| The legs trade at different hours and their daily results are    |
//| close to uncorrelated, which is what the combination earns from. |
//| The default sizes give each leg about 8% annual volatility; the  |
//| backtest's worst drawdown at these sizes is about 23%. Scale all |
//| five size inputs together to change the risk.                    |
//| Sizing model: the rules decide when to trade, a small model how  |
//| much. Each trade is scaled by 1 + InpModelTilt x erf of a ridge  |
//| regression score of numbers known at the entry: recent daily and |
//| hourly moves, today's range, the volatility ratio, the weekday.  |
//| Walk-forward from 2014 at tilt 0.5 it added about 5% a year with |
//| about 10% more volatility: Sharpe 2.06 against 1.99, a small     |
//| gain. InpUseModel = false gives the plain rules back.            |
//| Attach to a gold chart on a hedging account. The server clock is |
//| taken to be New York time plus 7 hours. The currency legs need a |
//| raw spread account: their edge is about one basis point each;    |
//| the midday leg stops paying above 1.2 basis points of cost.      |
//| Backtest: tools/backtest_quartet.py                              |
//| Sizing model: tools/quartet_model.py                             |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.20"

#include <Trade\Trade.mqh>

input group "Symbols"
input string InpGold            = "XAUUSD.pc"; // Gold
input string InpYen             = "USDJPY.pc"; // USD/JPY
input string InpEuro            = "EURUSD.pc"; // EUR/USD

input group "Size of each leg (0 switches the leg off)"
input double InpVolTargetPct    = 46.5;  // Gold: annual gold volatility one unit is scaled to, %
input double InpMaxLeverage     = 6.2;   // Gold: maximum notional of one unit, multiple of equity
input double InpBellRiskPct     = 2.7;   // Closing bell: loss at the stop, % of balance
input double InpTokyoRiskPct    = 2.0;   // Tokyo fixing: loss at the stop, % of balance
input double InpMeridianRiskPct = 1.0;   // Midday: loss at the stop, % of balance

input group "Gold session leg (server time)"
input int    InpEntryHHMM       = 105;   // Buy from this time, HHMM
input int    InpEntryMinutes    = 20;    // Stop trying to enter this many minutes later
input int    InpExitHHMM        = 900;   // Close at this time, HHMM
input bool   InpUseSession      = false; // Hold a unit through the whole session
input bool   InpUseDip          = true;  // Buy a unit after a sharp M15 fall
input double InpDipSigma        = 3.0;   // Fall of the M15 bar, standard deviations
input int    InpDipWindow       = 96;    // M15 returns used for the standard deviation
input int    InpDipFromHHMM     = 115;   // Earliest open time of the falling bar, HHMM
input int    InpDipToHHMM       = 745;   // Latest open time of the falling bar, HHMM
input int    InpDipHoldBars     = 16;    // Holding time of the dip unit, M15 bars
input int    InpVolSpan         = 30;    // Span of the exponentially weighted daily volatility

input group "Closing bell leg (23:00 server time)"
input int    InpBellLookMin     = 15;    // Move is measured over this many minutes (multiple of 5)
input double InpBellK           = 1.5;   // Trade when the move is at least this many average moves
input int    InpBellHoldMin     = 10;    // Holding time, minutes
input int    InpBellEntrySec    = 20;    // No entry later than this after the bell, seconds

input group "Tokyo fixing leg"
input int    InpTokyoHoldMin    = 90;    // Holding time after 9:55 Tokyo, minutes (multiple of 5)
input bool   InpGotobi          = true;  // Only on settlement days (5th, 10th, 15th, ...)
input int    InpTokyoEntrySec   = 20;    // No entry later than this after the fixing, seconds

input group "Midday leg (London time)"
input int    InpStartMin        = 690;   // Entry, minutes after midnight London time (multiple of 5)
input int    InpEndMin          = 780;   // Exit, minutes after midnight London time (multiple of 5)
input int    InpMeridianEntrySec= 60;    // No entry later than this after the start, seconds

input group "Stops and risk guard"
input int    InpDays            = 60;    // Days in the average move of each window
input double InpStopMult        = 3.0;   // Stop distance of the three stop legs, average moves
input double InpMarginPct       = 50.0;  // Margin cap of one order, % of free margin
input double InpGoldMaxSpread   = 0.30;  // No gold entry while spread is above this, price units
input int    InpFxMaxSpread     = 15;    // No currency entry while spread is above this, points
input double InpMaxDrawdownPct  = 35.0;  // Close everything and stop after this equity drawdown from the peak, %

input group "Sizing model"
input bool   InpUseModel        = true;  // Scale each trade by the model's score
input double InpModelTilt       = 0.5;   // Size runs from 1 - tilt to 1 + tilt times the leg's size (0 to 1)

input group "Execution"
input long   InpMagic           = 245013; // First of five magic numbers: session, dip, bell, Tokyo, midday
input int    InpGoldDeviation   = 30;     // Max slippage on gold, points
input int    InpFxDeviation     = 10;     // Max slippage on the currency pairs, points

#define VOL_BARS 250       // daily returns used for the volatility estimate
#define DIP_LATE 300       // a dip signal is dropped this many seconds after its bar closed
#define BELL_SEC 82800     // the bell, seconds after midnight server time (16:00 New York)
#define BELL     0         // the three stop legs; the magic number of leg n is InpMagic+2+n
#define TOKYO    1
#define MERIDIAN 2

CTrade   g_trade;
datetime g_day=0;          // day whose session entry has been handled
datetime g_bar=0;          // M15 bar whose dip signal has been handled
datetime g_done[3];        // per stop leg: day whose window has been dealt with
double   g_peak=0.0;
bool     g_halted=false;

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

string LegSymbol(int leg)
  {
   return(leg==BELL ? InpGold : leg==TOKYO ? InpYen : InpEuro);
  }

string LegName(int leg)
  {
   return(leg==BELL ? "bell" : leg==TOKYO ? "Tokyo" : "midday");
  }

double LegRisk(int leg)
  {
   return(leg==BELL ? InpBellRiskPct : leg==TOKYO ? InpTokyoRiskPct : InpMeridianRiskPct);
  }

// Points the trade object at one symbol and magic number.
void Prepare(string sym,long magic)
  {
   g_trade.SetExpertMagicNumber(magic);
   g_trade.SetDeviationInPoints(sym==InpGold ? InpGoldDeviation : InpFxDeviation);
   g_trade.SetTypeFillingBySymbol(sym);
  }

// Lots held on 'sym' under 'magic'; 'opened' receives the earliest open time.
double HeldLots(string sym,long magic,datetime &opened)
  {
   double lots=0.0;
   opened=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      lots+=PositionGetDouble(POSITION_VOLUME);
      datetime o=(datetime)PositionGetInteger(POSITION_TIME);
      if(opened==0 || o<opened)
         opened=o;
     }
   return(lots);
  }

// Closes every position on 'sym' under 'magic'. Returns false if a close failed.
bool CloseAll(string sym,long magic)
  {
   bool ok=true;
   Prepare(sym,magic);
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=magic)
         continue;
      if(!g_trade.PositionClose(t))
        {
         PrintFormat("AurumQuartet: close on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         ok=false;
        }
     }
   return(ok);
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

//--- sizing model ----------------------------------------------------

#define M_N 10             // features per model: eight common ones, then the leg's own
// Models 0 dip, 1 bell, 2 Tokyo, 3 midday: mean and deviation of each feature, ridge coefficients, intercept,
// mean and deviation of the score. Features: yesterday's return, move since yesterday's close, today's range,
// move of the last hour, return of the five days before, log of 20-day over 250-day volatility, Monday, Friday;
// dip: fall of the bar in deviations, time of day; bell: move into the bell in average moves.
// fitted by tools/quartet_model.py on 337 dip, 917 bell, 1244 tokyo, 4504 meridian trades
const double M_MU[4][10]={{-0.241327,-0.548495,1.13472,-0.564266,0.00723672,0.0215233,0.255193,0.163205,4.377,0.454748},
                          {-0.0432458,-0.453609,2.46708,-0.20984,-0.070375,0.0154071,0.17121,0.214831,2.61344,0},
                          {-0.0300123,-0.0999195,0.665049,-0.0294836,-0.075475,-0.0711498,0.142283,0.430868,0,0},
                          {0.0178814,-0.0239354,1.27521,0.00456749,0.0347858,-0.0606847,0.19849,0.199156,0,0}};
const double M_SD[4][10]={{1.4966,0.875983,1.02257,0.520418,1.58531,0.317946,0.43597,0.369552,2.64734,0.218518},
                          {1.39402,1.73567,1.36383,0.369691,1.5385,0.311915,0.376693,0.410705,1.58626,1},
                          {1.34387,0.419067,0.357447,0.322085,1.32749,0.33053,0.34934,0.495198,1,1},
                          {1.27812,0.838987,0.599588,0.278277,1.26888,0.291435,0.398863,0.399366,1,1}};
const double M_BETA[4][10]={{-0.000472785,-0.000681935,0.00197359,0.000737604,-0.000109932,0.000487392,-0.000152912,0.000375268,3.72676e-05,-0.000884524},
                            {-0.00669045,-0.0125059,-0.00595841,-0.0245472,0.0110492,-0.000956699,0.0184791,0.00397413,0.0576784,0},
                            {-0.0211557,-0.0325854,-0.0139104,0.0165104,-0.00990422,-0.00970784,0.000638976,0.00460912,0,0},
                            {0.00450127,-0.00293494,-0.0169657,0.00246045,-0.00321528,0.0025459,-0.00418112,0.0118214,0,0}};
const double M_ICPT[4]={0.00122555,0.0903307,0.0549724,0.0124345};
const double M_MEAN[4]={0.00115069,0.0893031,0.0551513,0.0126668};
const double M_DEV[4]={0.00180657,0.0658701,0.0393015,0.0217522};

// Error function (Abramowitz and Stegun 7.1.26, error below 1.5e-7).
double Erf(double x)
  {
   double t=1.0/(1.0+0.3275911*MathAbs(x));
   double y=1.0-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*MathExp(-x*x);
   return(x<0 ? -y : y);
  }

// Size multiplier of a trade of model 'm' on 'sym' in direction 'side', entered at 'price' in the bar that opens
// at 't0'; x8 and x9 are the leg's own features (EMPTY_VALUE when it has none). 1 while the model is off or the
// daily history is short.
double ModelWeight(int m,string sym,int side,datetime t0,double price,double x8,double x9)
  {
   if(!InpUseModel || InpModelTilt<=0)
      return(1.0);
   MqlRates d[];
   ArraySetAsSeries(d,true);
   int n=CopyRates(sym,PERIOD_D1,0,VOL_BARS+2,d);
   if(n<22 || d[0].time!=DayOf(t0) || price<=0)
      return(1.0);
   // mean absolute daily return of the last 20 and of the last VOL_BARS completed days
   int k=MathMin(VOL_BARS,n-2);
   double dv=0.0,dl=0.0;
   for(int i=1; i<=k; i++)
     {
      if(d[i+1].close<=0)
         return(1.0);
      double r=MathAbs(d[i].close/d[i+1].close-1.0);
      dl+=r;
      if(i<=20)
         dv+=r;
     }
   dv/=20.0;
   dl/=k;
   if(dv<=0)
      return(1.0);
   MqlDateTime s;
   TimeToStruct(t0,s);
   double x[M_N];
   ArrayInitialize(x,EMPTY_VALUE);
   x[0]=side*(d[1].close/d[2].close-1.0)/dv;
   x[1]=side*(price/d[1].close-1.0)/dv;
   x[2]=(d[0].high-d[0].low)/price/dv;
   // the M5 bar that closes one hour before the entry, if today has one
   int p=iBarShift(sym,PERIOD_M5,t0-3900,false);
   if(p>=0 && iTime(sym,PERIOD_M5,p)>=DayOf(t0) && iClose(sym,PERIOD_M5,p)>0)
      x[3]=side*(price/iClose(sym,PERIOD_M5,p)-1.0)/dv;
   x[4]=side*(d[1].close/d[6].close-1.0)/(dv*MathSqrt(5.0));
   if(k>=60 && dl>0)
      x[5]=MathLog(dv/dl);
   x[6]=(s.day_of_week==1 ? 1.0 : 0.0);
   x[7]=(s.day_of_week==5 ? 1.0 : 0.0);
   x[8]=x8;
   x[9]=x9;
   double score=M_ICPT[m];
   for(int j=0; j<M_N; j++)
      if(x[j]!=EMPTY_VALUE)     // a missing feature counts as its average
         score+=M_BETA[m][j]*MathMax(-4.0,MathMin(4.0,(x[j]-M_MU[m][j])/M_SD[m][j]));
   return(1.0+InpModelTilt*Erf((score-M_MEAN[m])/M_DEV[m]/MathSqrt(2.0)));
  }

//--- gold session leg ------------------------------------------------

// Leverage of one unit from completed daily bars; false while history is not available.
bool UnitLeverage(double &lev)
  {
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(InpGold,PERIOD_D1,1,VOL_BARS+1,c)<VOL_BARS+1)
      return(false);
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

// Buys one gold unit under 'magic', 'weight' times its plain size. Returns true when nothing is left to do,
// false to try again later.
bool BuyUnit(long magic,string what,double weight)
  {
   double lev;
   if(!UnitLeverage(lev))
      return(false);
   double ask=SymbolInfoDouble(InpGold,SYMBOL_ASK);
   double bid=SymbolInfoDouble(InpGold,SYMBOL_BID);
   double step=SymbolInfoDouble(InpGold,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(InpGold,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(InpGold,SYMBOL_VOLUME_MAX);
   double tickValue=SymbolInfoDouble(InpGold,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(InpGold,SYMBOL_TRADE_TICK_SIZE);
   if(ask<=0 || bid<=0 || step<=0 || tickSize<=0 || tickValue<=0 || ask-bid>InpGoldMaxSpread)
      return(false);
   // Money value of one lot at the current price, in account currency.
   double notionalPerLot=ask/tickSize*tickValue;
   double lots=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*lev*weight/notionalPerLot/step+1e-9)*step;
   double margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,InpGold,1.0,ask,margin) && margin>0)
      lots=MathMin(lots,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
   lots=MathMin(lots,vmax);
   if(lots<vmin)
     {
      PrintFormat("AurumQuartet: balance too small for the minimum lot at leverage %.2f, no %s unit",lev,what);
      return(true);
     }
   Prepare(InpGold,magic);
   if(!g_trade.Buy(lots,InpGold,0.0,0.0,0.0,"AurumQuartet "+what))
     {
      PrintFormat("AurumQuartet: %s buy failed, retcode %d (%s)",what,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return(false);
     }
   PrintFormat("AurumQuartet: %s unit, leverage %.2f, model weight %.2f, bought %.2f",what,lev,weight,lots);
   return(true);
  }

// True when the last completed M15 bar of gold is a dip signal; 'z' receives its fall in standard deviations.
bool DipSignal(double &z)
  {
   datetime bar=iTime(InpGold,PERIOD_M15,1);
   int hm=HHMM(bar);
   if(bar==0 || DayOf(bar)!=DayOf(TimeCurrent()) || hm<InpDipFromHHMM || hm>InpDipToHHMM)
      return(false);
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(InpGold,PERIOD_M15,1,InpDipWindow+2,c)<InpDipWindow+2)
      return(false);
   double mean=0.0,var=0.0;
   for(int i=1; i<=InpDipWindow; i++)
      mean+=MathLog(c[i]/c[i+1]);
   mean/=InpDipWindow;
   for(int i=1; i<=InpDipWindow; i++)
     {
      double r=MathLog(c[i]/c[i+1])-mean;
      var+=r*r;
     }
   double sd=MathSqrt(var/(InpDipWindow-1));
   if(sd<=0)
      return(false);
   z=-MathLog(c[0]/c[1])/sd;
   return(z>=InpDipSigma);
  }

// The session unit and the dip unit of gold.
void Session()
  {
   datetime now=TimeCurrent();
   datetime day=DayOf(now);
   int hm=HHMM(now);
   datetime baseOpened,dipOpened;
   double baseLots=HeldLots(InpGold,InpMagic,baseOpened);
   double dipLots=HeldLots(InpGold,InpMagic+1,dipOpened);
   bool on=(InpVolTargetPct>0);
   // Session unit: closed at the exit time, and whenever it is found open outside the session.
   if(baseLots>0 && (hm>=InpExitHHMM || hm<InpEntryHHMM || DayOf(baseOpened)!=day))
      CloseAll(InpGold,InpMagic);
   else if(on && InpUseSession && baseLots<=0 && g_day!=day && hm>=InpEntryHHMM && hm<InpExitHHMM)
     {
      MqlDateTime s;
      TimeToStruct(now,s);
      if(s.hour*60+s.min>=InpEntryHHMM/100*60+InpEntryHHMM%100+InpEntryMinutes || BuyUnit(InpMagic,"session",1.0))
         g_day=day;
     }
   else if(baseLots>0)
      g_day=day;
   // Dip unit: closed InpDipHoldBars bars after the bar it was bought on, or before the day ends.
   if(dipLots>0)
     {
      datetime entryBar=dipOpened-dipOpened%900;
      if(now>=entryBar+InpDipHoldBars*900 || DayOf(dipOpened)!=day || hm>=2350)
         CloseAll(InpGold,InpMagic+1);
      return;
     }
   datetime bar=iTime(InpGold,PERIOD_M15,0);
   if(!on || !InpUseDip || bar==0 || bar==g_bar)
      return;
   double z=0.0;
   if(now-bar>DIP_LATE || !DipSignal(z))
     {
      g_bar=bar;
      return;
     }
   double w=ModelWeight(0,InpGold,1,bar,iOpen(InpGold,PERIOD_M15,0),z,((bar-day)/60-60)/420.0);
   if(BuyUnit(InpMagic+1,"dip",w))
      g_bar=bar;
  }

//--- the three stop legs ---------------------------------------------

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

// Minutes the server clock is ahead of London time on 'day': 120, or 180 while only the US is on summer time.
int LondonOffset(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   int uk=(day>=Sunday(s.year,3,-1) && day<Sunday(s.year,10,-1) ? 1 : 0);
   return(120+60*(UsSummer(day)-uk));
  }

// Server time at which the leg opens on 'day': the bell, 9:55 Tokyo, or the London start minute.
datetime LegStart(int leg,datetime day)
  {
   if(leg==BELL)
      return(day+BELL_SEC);
   if(leg==TOKYO)
      return(day+(175+60*UsSummer(day))*60);
   return(day+(InpStartMin+LondonOffset(day))*60);
  }

// Server time at which a position of the leg opened at 'opened' is closed.
datetime LegEnd(int leg,datetime opened)
  {
   datetime day=DayOf(opened);
   if(leg==BELL)
      return(opened+InpBellHoldMin*60);
   if(leg==TOKYO)
      return(LegStart(TOKYO,day)+InpTokyoHoldMin*60);
   return(day+(InpEndMin+LondonOffset(day))*60);
  }

// True when the leg trades on 'day': a weekday, and for Tokyo a settlement day (a date divisible by five, or
// the Friday before one that falls on the weekend).
bool LegDay(int leg,datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   if(s.day_of_week<1 || s.day_of_week>5)
      return(false);
   if(leg!=TOKYO || !InpGotobi)
      return(true);
   return(s.day%5==0 || (s.day_of_week==5 && ((s.day+1)%5==0 || (s.day+2)%5==0)));
  }

// Move of the leg's window on 'day'. Bell: price at the bell minus the price InpBellLookMin minutes earlier.
// Tokyo and midday: move from the start to the end of the holding window as a fraction of the price.
// False when that day has no bar at the start.
bool LegMove(int leg,datetime day,double &move)
  {
   string sym=LegSymbol(leg);
   datetime a=LegStart(leg,day);
   int s=iBarShift(sym,PERIOD_M5,a,true);
   if(s<0)
      return(false);
   if(leg==BELL)
     {
      int p=iBarShift(sym,PERIOD_M5,a-InpBellLookMin*60-300,false);
      if(p<=s || iTime(sym,PERIOD_M5,p)<day)
         return(false);
      move=iOpen(sym,PERIOD_M5,s)-iClose(sym,PERIOD_M5,p);
      return(true);
     }
   int e=iBarShift(sym,PERIOD_M5,LegEnd(leg,a)-300,false);
   double open=iOpen(sym,PERIOD_M5,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(sym,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// Average size of the leg's move over the InpDays trading days before 'today'; 0 while history is short.
double AverageMove(int leg,datetime today)
  {
   double sum=0.0,move;
   int n=0;
   for(int i=1; i<=2*InpDays+20 && n<InpDays; i++)
      if(LegMove(leg,today-i*86400,move))
        {
         sum+=MathAbs(move);
         n++;
        }
   return(n>=InpDays/2 ? sum/n : 0.0);
  }

// Lots that lose 'riskPct' of the balance when price goes 'dist' against the position; 0 when below the minimum lot.
double RiskLots(string sym,int side,double price,double dist,double riskPct)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss,margin;
   if(!OrderCalcProfit(type,sym,1.0,price,price-side*dist,loss) || loss>=0)
      return(0.0);
   double lots=AccountInfoDouble(ACCOUNT_BALANCE)*riskPct/100.0/(-loss);
   if(OrderCalcMargin(type,sym,1.0,price,margin) && margin>0)
      lots=MathMin(lots,AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin);
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

// One stop leg: closes its position at the end of the window and opens one at the start.
void Leg(int leg)
  {
   string sym=LegSymbol(leg),name=LegName(leg);
   long magic=InpMagic+2+leg;
   datetime now=TimeCurrent(),opened;
   bool held=(HeldLots(sym,magic,opened)>0);
   if(held && now>=LegEnd(leg,opened))
      CloseAll(sym,magic);
   datetime today=DayOf(now);
   datetime start=LegStart(leg,today);
   if(LegRisk(leg)<=0 || g_done[leg]==today || now<start)
      return;
   int late=(leg==BELL ? InpBellEntrySec : leg==TOKYO ? InpTokyoEntrySec : InpMeridianEntrySec);
   if(!LegDay(leg,today) || now-start>=late || held || TradedSince(sym,magic,start))
     {
      g_done[leg]=today;
      return;
     }
   double move=0.0;
   if(leg==BELL && !LegMove(BELL,today,move))
      return;                  // the bar of the bell is not built yet, the next call tries again
   double avg=AverageMove(leg,today);
   if(avg<=0)
     {
      PrintFormat("AurumQuartet: fewer than %d days of M5 history on %s, no %s trade today",InpDays/2,sym,name);
      g_done[leg]=today;
      return;
     }
   int side=-1;                // Tokyo and midday always sell
   if(leg==BELL)
     {
      if(MathAbs(move)<InpBellK*avg)
        {
         PrintFormat("AurumQuartet: bell move %+.2f is below %.1f x average %.2f, no trade today",move,InpBellK,avg);
         g_done[leg]=today;
         return;
        }
      side=(move>0 ? -1 : 1);
     }
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   MqlTick q;
   if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>(leg==BELL ? InpGoldMaxSpread : InpFxMaxSpread*point))
      return;                  // tried again until the entry time has run out
   double spread=q.ask-q.bid;
   double dist=MathMax(InpStopMult*avg*(leg==BELL ? 1.0 : q.bid),SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+spread);
   double w=ModelWeight(leg+1,sym,side,start,q.bid,leg==BELL ? MathAbs(move)/avg : EMPTY_VALUE,EMPTY_VALUE);
   double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,LegRisk(leg)*w);
   if(lots<=0)
     {
      PrintFormat("AurumQuartet: balance too small for the minimum lot of %s at a stop of %s, no %s trade today",
                  sym,DoubleToString(dist,digits),name);
      g_done[leg]=today;
      return;
     }
   // the stop sits 'dist' from the bid on both sides, as in the backtests
   double sl=NormalizeDouble(q.bid-side*dist,digits);
   Prepare(sym,magic);
   bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,"AurumQuartet "+name) : g_trade.Sell(lots,sym,0.0,sl,0.0,"AurumQuartet "+name));
   if(!ok || g_trade.ResultDeal()==0)
     {
      PrintFormat("AurumQuartet: %s order failed, retcode %d (%s)",name,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat("AurumQuartet: %s leg %s %.2f %s at %s, stop %s, model weight %.2f, %d s after the start",name,
               side>0 ? "bought" : "sold",lots,sym,DoubleToString(g_trade.ResultPrice(),digits),DoubleToString(sl,digits),w,
               (int)(now-start));
   g_done[leg]=today;
  }

// Everything the EA does, called on every tick of the chart and once a second.
void Run()
  {
   if(g_halted)
      return;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   if(InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0))
     {
      PrintFormat("AurumQuartet: equity %.2f is %.1f%% below the peak %.2f, closing and halting",eq,InpMaxDrawdownPct,g_peak);
      bool ok=CloseAll(InpGold,InpMagic);
      ok=CloseAll(InpGold,InpMagic+1) && ok;
      for(int leg=BELL; leg<=MERIDIAN; leg++)
         ok=CloseAll(LegSymbol(leg),InpMagic+2+leg) && ok;
      g_halted=ok;
      return;
     }
   Session();
   for(int leg=BELL; leg<=MERIDIAN; leg++)
      Leg(leg);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEntryHHMM>=InpExitHHMM || InpEntryMinutes<1 || InpDipWindow<10 || InpDipHoldBars<1 || InpDipSigma<=0 ||
      InpVolSpan<2 || InpVolTargetPct<0 || InpMaxLeverage<=0 || InpBellRiskPct<0 || InpTokyoRiskPct<0 ||
      InpMeridianRiskPct<0 || InpBellLookMin<5 || InpBellLookMin%5!=0 || InpBellK<=0 || InpBellHoldMin<1 ||
      InpTokyoHoldMin<5 || InpTokyoHoldMin%5!=0 || InpStartMin<0 || InpStartMin%5!=0 || InpEndMin%5!=0 ||
      InpEndMin<InpStartMin+5 || InpEndMin>1250 || InpDays<2 || InpStopMult<=0 || InpMarginPct<=0 ||
      InpBellEntrySec<1 || InpTokyoEntrySec<1 || InpMeridianEntrySec<1 || InpModelTilt<0 || InpModelTilt>1)
      return(INIT_PARAMETERS_INCORRECT);
   string syms[3];
   syms[0]=InpGold; syms[1]=InpYen; syms[2]=InpEuro;
   for(int i=0; i<3; i++)
     {
      if(!SymbolSelect(syms[i],true))
        {
         PrintFormat("AurumQuartet: symbol %s is not available",syms[i]);
         return(INIT_FAILED);
        }
      iBars(syms[i],PERIOD_M5);   // starts loading the bars the averages are built from
      iBars(syms[i],PERIOD_D1);   // and the daily bars of the sizing model
     }
   iBars(InpGold,PERIOD_M15);
   ArrayInitialize(g_done,0);
   g_peak=AccountInfoDouble(ACCOUNT_EQUITY);
   EventSetTimer(1);              // the other symbols' ticks do not call OnTick
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
