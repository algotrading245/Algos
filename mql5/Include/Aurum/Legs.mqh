//+------------------------------------------------------------------+
//| Aurum/Legs.mqh - the legs, sizing and event handlers shared by   |
//| AurumHydra and AurumFunded. Include Aurum/Inputs.mqh first.      |
//+------------------------------------------------------------------+
// Hooks each wrapper defines after including this file:
double AurumSize();                                                 // multiple of every size (a prop guard's cushion sizing)
bool   AurumGoldStop(double lots,double ask,double bid,double &sl); // broker stop of a gold unit (0 = none); false: try later
bool   AurumGuard();                                                // false: nothing is traded on this tick
bool   AurumInputsBad();                                            // true: the wrapper's own inputs are wrong

#define VOL_BARS 250       // daily returns used for the volatility estimate
#define DIP_LATE 300       // a dip signal is dropped this many seconds after its bar closed
#define BELL_SEC 82800     // the bell, seconds after midnight server time (16:00 New York)
#define BELL     0         // the three stop legs; the magic number of leg n is InpMagic+2+n
#define TOKYO    1
#define MERIDIAN 2
#define SNAP     3
#define LEGS     4
#define HOLD_MAGIC 6       // the gold hold position has magic InpMagic+6
#define GRID_MAGIC 10      // level k of the grid has magic InpMagic+10+k
#define GRID_MAX 8
#define GRID_WAIT 10       // seconds to wait for a sent grid level to show among the positions
#define FIX_MAGIC 20       // the fix trades have magic InpMagic+20 before the fix and InpMagic+21 after it
#define FALL_MAGIC 22      // the stock-fall fix trades have magic InpMagic+22
#define MORN_MAGIC 23      // the Tokyo-morning trades have magic InpMagic+23
#define AFTER_MAGIC 24     // the after-holiday trades have magic InpMagic+24
#define DRIFT_MAGIC 25     // the overnight-drift trade has magic InpMagic+25
#define BREAK_MAGIC 26     // the breakout trades have magic InpMagic+26 (long) and InpMagic+27 (short)
#define NOISE_MAGIC 28     // the noise-area trades have magic InpMagic+28 (S&P 500) and InpMagic+29 (Nasdaq)
#define NOISE_OPEN  990    // 9:30 New York in server minutes (the server is New York + 7)
#define NOISE_CLOSE 1380   // 16:00 New York
#define NOISE_N     12     // checks at 10:00, 10:30, ... 15:30 New York
#define NOISE_DAYS  14     // sessions in the average move and the daily volatility
#define DRIFT_DAYS 250     // cash sessions the last one is ranked against
#define MORN_PAIRS 3
#define FIX_PAIRS 5
#define FIX_ALL 8          // the dollar pairs and the yen crosses of the month-end fix

CTrade   g_trade;
datetime g_day=0;          // day whose session entry has been handled
datetime g_bar=0;          // M15 bar whose dip signal has been handled
datetime g_done[LEGS];        // per stop leg: day whose window has been dealt with
double   g_peak=0.0;
bool     g_halted=false;
bool     g_gridOn=false;   // the grid symbol is there and the grid has a size
datetime g_gridBar=0;      // H1 bar whose close has been dealt with
bool     g_gridSet=false;  // a target has been worked out since the start
int      g_gridTarget=0;   // levels the grid should hold, + long, - short
double   g_gridMa=0.0;     // average of the log price at the last hourly close
double   g_gridStep=0.0;   // one step at the last hourly close, in log price
datetime g_gridNote=0;     // day on which the grid last reported a problem
int      g_gridSent=0;     // highest level sent and not yet seen among the positions, + long, - short
datetime g_gridSentAt=0;   // when that level was sent
datetime g_holdDay=0;      // day whose gold hold check is done
bool     g_fixOn=false;    // the stock index is there and the fix leg has a size
string   g_fixSym[FIX_ALL];          // the pairs of the fix leg, then the yen crosses, "" for one that is missing
const int FIX_SIGN[FIX_ALL]={1,1,1,-1,-1,1,1,1};   // +1: the pair rises when the dollar falls; a cross is bought with rising stocks
datetime g_fixDone[2][FIX_ALL];      // per window and pair: day that has been dealt with
datetime g_fixNote=0;      // day on which the fix leg last reported a problem
bool     g_fallOn=false;   // the stock index is there and the stock-fall fix leg has a size
bool     g_mornOn=false;   // the stock index is there and the Tokyo-morning leg has a size
string   g_mornSym[MORN_PAIRS];      // the pairs of the Tokyo-morning leg, "" for one that is missing
datetime g_mornDone[MORN_PAIRS];     // per pair: day that has been dealt with
datetime g_fallDone[FIX_PAIRS];      // per pair: day that has been dealt with
bool     g_afterOn=false;  // the after-holiday leg has a size
datetime g_goalRound=0;    // first day of the goal round whose end has been printed
double   g_goalMult=0;     // goal multiple in use: InpTarget, else InpGoalMult
double   g_goalScale=1;    // goal scale in use: the best tested for InpTarget, else InpGoalScale
bool     g_goalOver=false;  // the round has ended and InpGoalStop asks to close everything and stop
bool     g_driftOn=false;  // the stock index is there and the overnight-drift leg has a size
datetime g_driftDone=0;    // day whose overnight-drift entry has been dealt with
datetime g_afterDone[FIX_PAIRS];     // per pair: day that has been dealt with
bool     g_breakOn=false;  // the breakout leg has a size
datetime g_breakDay=0;     // day the range below belongs to
bool     g_breakOk=false;  // that day's range exists and passed the filter
double   g_breakHi=0.0,g_breakLo=0.0;
datetime g_breakTraded[2]; // per side (long, short): day a trade was opened
bool     g_noiseOn=false;  // the noise-area leg has a size
string   g_noiseSym[2];    // S&P 500 and Nasdaq, "" for one that is missing
datetime g_noiseDay[2];    // day the bands below belong to
bool     g_noiseReady[2];  // that day's bands are known
int      g_noiseLast[2];   // last check dealt with that day
double   g_noiseSig[2][NOISE_N],g_noiseHi[2],g_noiseLo[2],g_noiseLev[2],g_noiseVol[2];

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
   return(leg==TOKYO ? InpYen : leg==MERIDIAN ? InpEuro : InpGold);
  }

string LegName(int leg)
  {
   return(leg==BELL ? "bell" : leg==TOKYO ? "Tokyo" : leg==MERIDIAN ? "midday" : "fast");
  }

string GoalKey(string name)
  {
   return(AURUM_NAME+"."+IntegerToString(InpMagic)+".goal"+IntegerToString(InpGoalRound)+"."+name);
  }

// Weekdays from day 'a' up to but not including day 'b'.
int Weekdays(datetime a,datetime b)
  {
   int n=0;
   MqlDateTime s;
   for(datetime d=a; d<b; d+=86400)
     {
      TimeToStruct(d,s);
      if(s.day_of_week>=1 && s.day_of_week<=5)
         n++;
     }
   return(n);
  }

// The size multiple with the best chance of reaching the goal of the running round, or -1 when no round runs.
// A round starts at the equity of its first day and ends at the goal or after InpGoalDays weekdays.
double GoalSize()
  {
   datetime today=DayOf(TimeCurrent());
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity<=0)
      return(-1.0);
   bool have=(GlobalVariableCheck(GoalKey("start")) && GlobalVariableCheck(GoalKey("day")));
   double start=(have ? GlobalVariableGet(GoalKey("start")) : 0.0);
   datetime day0=(have ? (datetime)GlobalVariableGet(GoalKey("day")) : 0);
   int left=(have ? InpGoalDays-Weekdays(day0,today) : 0);
   if(have && (start<=0 || left<=0 || equity>=start*g_goalMult))
     {
      if(g_goalRound!=day0)
        {
         PrintFormat(AURUM_NAME+": goal round of %s ended, equity %.2f from %.2f (%.2fx, goal %.1fx)",
                     TimeToString(day0,TIME_DATE),equity,start,start>0 ? equity/start : 0.0,g_goalMult);
         g_goalRound=day0;
        }
      if(!InpGoalRepeat)
        {
         g_goalOver=InpGoalStop;
         return(-1.0);
        }
      have=false;
     }
   if(!have)
     {
      start=equity;
      day0=today;
      left=InpGoalDays;
      GlobalVariableSet(GoalKey("start"),start);
      GlobalVariableSet(GoalKey("day"),(double)day0);
      PrintFormat(AURUM_NAME+": goal round started, equity %.2f, goal %.2f within %d weekdays",start,start*g_goalMult,left);
     }
   if(InpGoalBold)
      return(InpGoalCap);
   double x=MathMax(1e-6,MathMin(1.0-1e-6,equity/(start*g_goalMult)));
   int err=0;
   double z=MathQuantileNormal(x,0.0,1.0,err);
   if(err!=0)
      return(-1.0);
   double size=g_goalScale*MathExp(-0.5*z*z)/MathSqrt(2.0*M_PI)/(x*MathSqrt((double)left))/(InpGoalDayVolPct/100.0);
   return(MathMin(InpGoalCap,size));
  }

// Account vol target: InpAcctVolPct over the yearly swing of the daily closed P&L of the last InpAcctVolDays weekdays,
// at most InpAcctVolMax. Read from the deal history once a day, so it survives a restart. 1 while off or while fewer
// than 20 of those weekdays had a trade. Positions still open are not counted until they close.
double VolScale()
  {
   static datetime done=0;
   static double scale=1.0;
   if(InpAcctVolPct<=0)
      return(1.0);
   datetime today=DayOf(TimeCurrent());
   if(done==today)
      return(scale);
   done=today;
   scale=1.0;
   int n=InpAcctVolDays;
   datetime days[];
   double pnl[],flow[];
   ArrayResize(days,n);
   ArrayResize(pnl,n);
   ArrayResize(flow,n);
   ArrayInitialize(pnl,0.0);
   ArrayInitialize(flow,0.0);
   datetime d=today;
   for(int i=0; i<n;)           // days[0] is the last weekday before today, then back in time
     {
      d-=86400;
      MqlDateTime dt;
      TimeToStruct(d,dt);
      if(dt.day_of_week>=1 && dt.day_of_week<=5)
         days[i++]=d;
     }
   if(!HistorySelect(days[n-1],TimeCurrent()+86400))
      return(scale);
   double todayFlow=0.0;
   for(int k=HistoryDealsTotal()-1; k>=0; k--)
     {
      ulong ticket=HistoryDealGetTicket(k);
      if(ticket==0)
         continue;
      long type=HistoryDealGetInteger(ticket,DEAL_TYPE);
      bool trade=(type!=DEAL_TYPE_BALANCE && type!=DEAL_TYPE_CREDIT && type!=DEAL_TYPE_BONUS);
      double amount=HistoryDealGetDouble(ticket,DEAL_PROFIT)+(trade ? HistoryDealGetDouble(ticket,DEAL_SWAP)+
                    HistoryDealGetDouble(ticket,DEAL_COMMISSION)+HistoryDealGetDouble(ticket,DEAL_FEE) : 0.0);
      datetime day=DayOf((datetime)HistoryDealGetInteger(ticket,DEAL_TIME));
      if(day>=today)
        {
         todayFlow+=amount;
         continue;
        }
      for(int i=0; i<n; i++)    // a weekend deal counts on the weekday before it
         if(days[i]<=day)
           {
            if(trade)
               pnl[i]+=amount;
            else
               flow[i]+=amount;
            break;
           }
     }
   double r[],end=AccountInfoDouble(ACCOUNT_BALANCE)-todayFlow,sum=0.0;
   ArrayResize(r,n);
   int active=0;
   for(int i=0; i<n; i++)       // walk the balance back day by day to get each day's return
     {
      double start=end-pnl[i]-flow[i];
      r[i]=(start>0 ? pnl[i]/start : 0.0);
      sum+=r[i];
      if(pnl[i]!=0.0)
         active++;
      end=start;
     }
   if(active<20)
      return(scale);
   double mean=sum/n,ss=0.0;
   for(int i=0; i<n; i++)
      ss+=(r[i]-mean)*(r[i]-mean);
   double vol=MathSqrt(ss/(n-1)*252.0)*100.0;
   if(vol>0)
      scale=MathMin(InpAcctVolMax,InpAcctVolPct/vol);
   PrintFormat(AURUM_NAME+": account swing %.1f%% a year over %d weekdays, vol target %.1f%% gives size x%.2f",vol,n,InpAcctVolPct,scale);
   return(scale);
  }

// InpSizeMult, or the size the goal asks for, cut while a drawdown brake is on (the deeper one wins), times the vol
// target (not with the goal, which sets its own size) and the wrapper's multiple.
double SizeMult()
  {
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   bool brake=(InpBrakePct>0 && g_peak>0 && eq<g_peak*(1.0-InpBrakePct/100.0));
   bool brake2=(InpBrake2Pct>0 && g_peak>0 && eq<g_peak*(1.0-InpBrake2Pct/100.0));
   double goal=(g_goalMult>1.0 ? GoalSize() : -1.0);
   return((goal>=0 ? goal : InpSizeMult*VolScale())*(brake2 ? InpBrake2Cut : brake ? InpBrakeCut : 1.0)*AurumSize());
  }

// Day-loss guard: true (no trading) once equity falls InpDayLossPct under the equity at the first tick of the server
// day; everything is closed (tried again once a minute) and trading starts again the next day. The day's start is kept
// in global variables, so a restart keeps it.
bool DayLossHit(double eq)
  {
   static datetime day=0,hit=0,closed=0,tried=0;
   static double start=0.0;
   if(InpDayLossPct<=0)
      return(false);
   datetime today=DayOf(TimeCurrent());
   if(day!=today)
     {
      string kd=AURUM_NAME+"."+IntegerToString(InpMagic)+".lossday",ks=AURUM_NAME+"."+IntegerToString(InpMagic)+".lossstart";
      if(GlobalVariableCheck(kd) && (datetime)GlobalVariableGet(kd)==today && GlobalVariableCheck(ks))
         start=GlobalVariableGet(ks);
      else
        {
         start=eq;
         GlobalVariableSet(kd,(double)today);
         GlobalVariableSet(ks,start);
        }
      day=today;
     }
   if(hit!=today)
     {
      if(eq>=start*(1.0-InpDayLossPct/100.0))
         return(false);
      hit=today;
      PrintFormat(AURUM_NAME+": equity %.2f is %.1f%% under the day's start %.2f, closing and pausing to the next day",eq,InpDayLossPct,start);
     }
   if(closed!=today && TimeCurrent()>=tried+60)
     {
      tried=TimeCurrent();
      if(CloseEverything())
         closed=today;
     }
   return(true);
  }

// InpMonthEndBoost on the last weekday of a month, 1 on every other day.
double MonthEndBoost()
  {
   return(InpMonthEndBoost!=1.0 && FixDay(DayOf(TimeCurrent())) ? InpMonthEndBoost : 1.0);
  }

double LegRisk(int leg)
  {
   return(SizeMult()*(leg==BELL || leg==TOKYO ? MonthEndBoost() : 1.0)*(leg==BELL ? InpBellRiskPct : leg==TOKYO ? InpTokyoRiskPct : leg==MERIDIAN ? InpMeridianRiskPct : InpSnapRiskPct));
  }

// Points the trade object at one symbol and magic number.
void Prepare(string sym,long magic)
  {
   g_trade.SetExpertMagicNumber(magic);
   g_trade.SetDeviationInPoints(sym==InpGold ? InpGoldDeviation : InpFxDeviation);
   g_trade.SetTypeFillingBySymbol(sym);
  }

// True when the last market order filled. FTMO's market execution answers DONE with an order ticket and deal 0 and
// reports the deal moments later, so DONE with an order ticket counts as a fill.
bool Filled(bool ok)
  {
   return(ok && (g_trade.ResultDeal()>0 || (g_trade.ResultRetcode()==TRADE_RETCODE_DONE && g_trade.ResultOrder()>0)));
  }

// Price of the last fill; the price asked for while the broker has not reported the deal (price 0).
double FillPrice(double asked)
  {
   return(g_trade.ResultPrice()>0 ? g_trade.ResultPrice() : asked);
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

// The last closes sent. FTMO answers a close DONE before its deal lands, so the position is still listed on the next
// tick and a second close is refused (10013 on 2026-10-19, 10036 on 10-23). A close sent under 10 s ago is in flight.
ulong    g_closeTicket[16];
datetime g_closeTime[16];
int      g_closeNext=0;

bool CloseInFlight(ulong t)
  {
   for(int k=0; k<ArraySize(g_closeTicket); k++)
      if(g_closeTicket[k]==t && TimeCurrent()<g_closeTime[k]+10)
         return(true);
   return(false);
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
      if(CloseInFlight(t))
        {
         ok=false;                                                     // not gone yet: a stop caller retries before it halts
         continue;
        }
      if(g_trade.PositionClose(t))
        {
         g_closeTicket[g_closeNext]=t;
         g_closeTime[g_closeNext]=TimeCurrent();
         g_closeNext=(g_closeNext+1)%ArraySize(g_closeTicket);
        }
      else if(g_trade.ResultRetcode()!=TRADE_RETCODE_POSITION_CLOSED)       // already gone: nothing left to close
        {
         PrintFormat(AURUM_NAME+": close on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
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

// Annual volatility of gold from completed daily bars; false while history is not available.
bool GoldVol(int span,double &vol)
  {
   double c[];
   ArraySetAsSeries(c,true);
   if(CopyClose(InpGold,PERIOD_D1,1,VOL_BARS+1,c)<VOL_BARS+1)
      return(false);
   // Exponentially weighted standard deviation of daily returns, newest first, with bias correction.
   double decay=1.0-2.0/(span+1.0);
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
   vol=MathSqrt(var*252.0);
   return(vol>0);
  }

// Leverage of one dip or session unit.
bool UnitLeverage(double &lev)
  {
   double vol;
   if(!GoldVol(InpVolSpan,vol))
      return(false);
   lev=SizeMult()*MathMin(InpMaxLeverage,InpVolTargetPct/100.0/vol);
   return(true);
  }

// Size multiplier from the run of losing trades under 'magic': InpLossMult for each loss in a row, three at most,
// divided by InpLossNorm.
double Progression(string sym,long magic)
  {
   if(InpLossMult==1.0 || InpLossMult<=0 || !HistorySelect(TimeCurrent()-90*86400,TimeCurrent()+60))
      return(1.0);
   int run=0;
   for(int i=HistoryDealsTotal()-1; i>=0 && run<3; i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0 || HistoryDealGetString(d,DEAL_SYMBOL)!=sym || HistoryDealGetInteger(d,DEAL_MAGIC)!=magic ||
         HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_OUT)
         continue;
      if(HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_COMMISSION)>=0)
         break;
      run++;
     }
   return(MathPow(InpLossMult,run)/InpLossNorm);
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
      PrintFormat(AURUM_NAME+": balance too small for the minimum lot at leverage %.2f, no %s unit",lev,what);
      return(true);
     }
   double sl=0.0;
   if(!AurumGoldStop(lots,ask,bid,sl))
      return(false);
   Prepare(InpGold,magic);
   if(!g_trade.Buy(lots,InpGold,0.0,sl,0.0,AURUM_NAME+" "+what))
     {
      PrintFormat(AURUM_NAME+": %s buy failed, retcode %d (%s)",what,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return(false);
     }
   PrintFormat(AURUM_NAME+": %s unit, leverage %.2f, model weight %.2f, bought %.2f",what,lev,weight,lots);
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
   if(BuyUnit(InpMagic+1,"dip",w*Progression(InpGold,InpMagic+1)))
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
   if(leg==BELL || leg==SNAP)
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
   if(leg==SNAP)
      return(opened+InpSnapHoldSec);
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

// Move of the leg's window on 'day'. Bell and fast: price at the bell minus the price InpBellLookMin minutes earlier.
// Tokyo and midday: move from the start to the end of the holding window as a fraction of the price.
// False when that day has no bar at the start.
bool LegMove(int leg,datetime day,double &move)
  {
   string sym=LegSymbol(leg);
   datetime a=LegStart(leg,day);
   int s=iBarShift(sym,PERIOD_M5,a,true);
   if(s<0)
      return(false);
   if(leg==BELL || leg==SNAP)
     {
      int p=iBarShift(sym,PERIOD_M5,a-(leg==BELL ? InpBellLookMin : InpSnapLookMin)*60-300,false);
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
// 'nearest' rounds the risk lots to the nearest step instead of down (at most 2x 'riskPct' at the first step, still
// capped by the margin), for a leg whose size is only a few steps: rounding down there skips its widest stops.
double RiskLots(string sym,int side,double price,double dist,double riskPct,bool nearest=false)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double loss,margin;
   if(!OrderCalcProfit(type,sym,1.0,price,price-side*dist,loss) || loss>=0)
      return(0.0);
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double lots=AccountInfoDouble(ACCOUNT_BALANCE)*riskPct/100.0/(-loss)/step;
   lots=(nearest ? MathRound(lots) : MathFloor(lots+1e-9))*step;
   if(OrderCalcMargin(type,sym,1.0,price,margin) && margin>0)
      lots=MathMin(lots,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
   lots=MathMin(lots,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

// One stop leg: closes its position at the end of the window and opens one at the start.
void Leg(int leg)
  {
   string sym=LegSymbol(leg),name=LegName(leg);
   long magic=InpMagic+2+leg;
   datetime now=TimeCurrent(),opened;
   bool held=(HeldLots(sym,magic,opened)>0),fade=(leg==BELL || leg==SNAP);
   if(held && now>=LegEnd(leg,opened))
      CloseAll(sym,magic);
   datetime today=DayOf(now);
   datetime start=LegStart(leg,today);
   if(LegRisk(leg)<=0 || g_done[leg]==today || now<start)
      return;
   int late=(leg==BELL ? InpBellEntrySec : leg==TOKYO ? InpTokyoEntrySec : leg==MERIDIAN ? InpMeridianEntrySec : InpSnapEntrySec);
   if(!LegDay(leg,today) || now-start>=late || held || TradedSince(sym,magic,start))
     {
      g_done[leg]=today;
      return;
     }
   double move=0.0;
   if(fade && !LegMove(leg,today,move))
      return;                  // the bar of the bell is not built yet, the next call tries again
   double avg=AverageMove(leg,today);
   if(avg<=0)
     {
      PrintFormat(AURUM_NAME+": fewer than %d days of M5 history on %s, no %s trade today",InpDays/2,sym,name);
      g_done[leg]=today;
      return;
     }
   int side=-1;                // Tokyo and midday always sell
   if(fade)
     {
      double k=(leg==BELL ? InpBellK : InpSnapK);
      if(MathAbs(move)<k*avg)
        {
         PrintFormat(AURUM_NAME+": %s move %+.2f is below %.1f x average %.2f, no trade today",name,move,k,avg);
         g_done[leg]=today;
         return;
        }
      side=(move>0 ? -1 : 1);
     }
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   MqlTick q;
   if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>(fade ? InpGoldMaxSpread : InpFxMaxSpread*point))
      return;                  // tried again until the entry time has run out
   double spread=q.ask-q.bid;
   double dist=MathMax(InpStopMult*avg*(fade ? 1.0 : q.bid),SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+spread);
   double w=(leg==SNAP ? 1.0 : ModelWeight(leg+1,sym,side,start,q.bid,leg==BELL ? MathAbs(move)/avg : EMPTY_VALUE,EMPTY_VALUE));
   double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,LegRisk(leg)*w*Progression(sym,magic));
   if(lots<=0)
     {
      PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no %s trade today",
                  sym,DoubleToString(dist,digits),name);
      g_done[leg]=today;
      return;
     }
   // the stop sits 'dist' from the bid on both sides, as in the backtests
   double sl=NormalizeDouble(q.bid-side*dist,digits);
   Prepare(sym,magic);
   bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" "+name) : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" "+name));
   if(!Filled(ok))
     {
      PrintFormat(AURUM_NAME+": %s order failed, retcode %d (%s)",name,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat(AURUM_NAME+": %s leg %s %.2f %s at %s, stop %s, model weight %.2f, %d s after the start",name,
               side>0 ? "bought" : "sold",lots,sym,DoubleToString(FillPrice(side>0 ? q.ask : q.bid),digits),DoubleToString(sl,digits),w,
               (int)(now-start));
   g_done[leg]=today;
  }

//--- grid ------------------------------------------------------------

string GridKey(string what)
  {
   return(StringFormat(AURUM_NAME+".%I64d.grid.%s",InpMagic,what));
  }

// Highest grid level that holds a position, + for a long grid, - for a short one.
int GridHeld()
  {
   int n=0,side=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=InpGridSymbol)
         continue;
      long k=PositionGetInteger(POSITION_MAGIC)-InpMagic-GRID_MAGIC;
      if(k<1 || k>GRID_MAX)
         continue;
      n=(int)MathMax(n,k);
      side=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1);
     }
   return(side*n);
  }

bool GridCloseAll()
  {
   bool ok=true;
   for(int k=1; k<=GRID_MAX; k++)
      ok=CloseAll(InpGridSymbol,InpMagic+GRID_MAGIC+k) && ok;
   return(ok);
  }

// One report a day at most.
void GridNote(string text)
  {
   datetime day=DayOf(TimeCurrent());
   if(g_gridNote==day)
      return;
   g_gridNote=day;
   Print(AURUM_NAME+": grid, ",text);
  }

// From the completed hourly bars that open between 1:00 and 22:59 on weekdays: the average 'ma' of the log
// close, one step 'stepLog' in log price, and 'z', the distance of the last close from the average in steps.
bool GridSignal(double &z,double &ma,double &stepLog)
  {
   int nMa=InpGridMaDays*22,nVol=InpGridVolDays*22;
   int need=MathMax(nMa,nVol+2);
   MqlRates r[];
   ArraySetAsSeries(r,true);
   int got=CopyRates(InpGridSymbol,PERIOD_H1,1,need*24/22+72,r);
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

// Lots of the first level: the whole grid loses InpGridRiskPct of the balance at its stop-out. 0 when too small.
double GridBase(double bid)
  {
   double loss,risk=0.0;
   for(int k=1; k<=InpGridLevels; k++)
      risk+=MathPow(InpGridMult,k-1)*(InpGridLevels+1-k);     // steps lost at the stop-out, in first-level lots
   if(!OrderCalcProfit(ORDER_TYPE_BUY,InpGridSymbol,1.0,bid,bid*MathExp(-g_gridStep),loss) || loss>=0)
      return(0.0);
   double lots=AccountInfoDouble(ACCOUNT_BALANCE)*SizeMult()*InpGridRiskPct/100.0/(risk*(-loss));
   return(lots<SymbolInfoDouble(InpGridSymbol,SYMBOL_VOLUME_MIN) ? 0.0 : lots);
  }

// The grid: a new target at every hourly close, then orders until the positions match it.
void Grid()
  {
   if(!g_gridOn)
      return;
   string sym=InpGridSymbol;
   int q=GridHeld(),L=InpGridLevels;
   if(g_gridSent!=0 && q*g_gridSent>0 && MathAbs(q)>=MathAbs(g_gridSent))
      g_gridSent=0;
   bool dead=(GlobalVariableCheck(GridKey("dead")) && GlobalVariableGet(GridKey("dead"))>0);
   datetime now=TimeCurrent();
   datetime bar=iTime(sym,PERIOD_H1,0),done=iTime(sym,PERIOD_H1,1);
   if(bar!=0 && done!=0 && bar!=g_gridBar)
     {
      MqlDateTime s;
      TimeToStruct(done,s);
      if(s.hour>=1 && s.hour<=22 && s.day_of_week>=1 && s.day_of_week<=5)
        {
         double z,ma,st;
         if(!GridSignal(z,ma,st))
           {
            GridNote("hourly history of "+sym+" is too short or still loading");
            if(now-bar>300)
               g_gridBar=bar;
            return;
           }
         int side=(z>0 ? 1 : -1);
         double az=MathAbs(z);
         g_gridMa=ma;
         g_gridStep=st;
         if(dead)
           {
            if(az<0.5)
              {
               GlobalVariableSet(GridKey("dead"),0);
               Print(AURUM_NAME+": grid, price is back at the average, the grid is live again");
              }
            g_gridTarget=0;
           }
         else if(az>=L+1)
           {
            GlobalVariableSet(GridKey("dead"),1);
            g_gridTarget=0;
            PrintFormat(AURUM_NAME+": grid stop-out, price is %.2f steps from the average",z);
           }
         else
           {
            int cur=(q*side<0 ? MathAbs(q) : 0);     // levels already open on this side of the average
            g_gridTarget=-side*MathMax(MathMin((int)MathFloor(az),L),MathMin(cur,(int)MathCeil(az)));
           }
         g_gridSet=true;
        }
      g_gridBar=bar;
     }
   MqlTick tick;
   if(!SymbolInfoTick(sym,tick) || tick.bid<=0 || tick.ask<=0)
      return;
   // between hourly closes only a move well beyond the stop-out level is acted on
   if(q!=0 && InpGridPanic>0 && g_gridStep>0)
     {
      double z=(MathLog(tick.bid)-g_gridMa)/g_gridStep;
      if(z*q<0 && MathAbs(z)>=L+1+InpGridPanic)
        {
         GlobalVariableSet(GridKey("dead"),1);
         g_gridTarget=0;
         g_gridSet=true;
         PrintFormat(AURUM_NAME+": grid stop-out inside the hour, price is %.2f steps from the average",z);
        }
     }
   int t=g_gridTarget;
   if(q==0 && t==0)
      g_gridSent=0;            // a level that never showed is not waited for once nothing is wanted
   if(!g_gridSet || q==t)
      return;
   if(q!=0 && (t==0 || (q>0)!=(t>0)))
     {
      GridCloseAll();          // the next call opens the other side, if any
      return;
     }
   if(MathAbs(t)<MathAbs(q))
     {
      for(int k=MathAbs(q); k>MathAbs(t); k--)
         CloseAll(sym,InpMagic+GRID_MAGIC+k);
      return;
     }
   // FTMO answers DONE with deal 0 and shows the position moments later: no new level until the last one shows or GRID_WAIT s pass
   if(g_gridSent!=0)
     {
      if(now-g_gridSentAt<GRID_WAIT)
         return;
      PrintFormat(AURUM_NAME+": grid level %d sent %d s ago is not among the positions, it may be sent again",
                  MathAbs(g_gridSent),(int)(now-g_gridSentAt));
      g_gridSent=0;
     }
   if(tick.ask-tick.bid>InpGridMaxSpread*SymbolInfoDouble(sym,SYMBOL_POINT))
      return;
   // the size of a grid cycle is fixed when its first level opens
   double base=(q!=0 && GlobalVariableCheck(GridKey("base")) ? GlobalVariableGet(GridKey("base")) : 0.0);
   if(base<=0)
     {
      base=GridBase(tick.bid);
      if(base<=0)
        {
         GridNote("balance too small for the minimum lot of "+sym+", no grid");
         g_gridTarget=q;
         return;
        }
      GlobalVariableSet(GridKey("base"),base);
     }
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   int side=(t>0 ? 1 : -1);
   for(int k=MathAbs(q)+1; k<=MathAbs(t); k++)
     {
      double lots=MathMin(MathFloor(base*MathPow(InpGridMult,k-1)/step+1e-9)*step,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
      double margin=0.0;
      if(OrderCalcMargin(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,sym,1.0,tick.ask,margin) && margin>0)
         lots=MathMin(lots,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
      lots=NormalizeDouble(lots,2);
      if(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN))
        {
         GridNote("not enough free margin for level "+IntegerToString(k));
         g_gridTarget=side*(k-1);
         return;
        }
      Prepare(sym,InpMagic+GRID_MAGIC+k);
      string note=AURUM_NAME+" grid "+IntegerToString(k);
      bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,0.0,0.0,note) : g_trade.Sell(lots,sym,0.0,0.0,0.0,note));
      if(!Filled(ok))
        {
         PrintFormat(AURUM_NAME+": grid order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         return;
        }
      g_gridSent=side*k;
      g_gridSentAt=now;
      PrintFormat(AURUM_NAME+": grid level %d %s %.2f %s",k,side>0 ? "bought" : "sold",lots,sym);
     }
  }

//--- gold hold -------------------------------------------------------

// Once a day: long gold in proportion to how many of the 20, 60, 120 and 250-day returns are positive.
void Hold()
  {
   datetime now=TimeCurrent(),day=DayOf(now),opened;
   long magic=InpMagic+HOLD_MAGIC;
   MqlDateTime s;
   TimeToStruct(now,s);
   if(g_holdDay==day || HHMM(now)<InpHoldHHMM || s.day_of_week<1 || s.day_of_week>5)
      return;
   double held=HeldLots(InpGold,magic,opened);
   if(InpHoldVolPct<=0 && held<=0)
     {
      g_holdDay=day;
      return;
     }
   double c[],vol;
   ArraySetAsSeries(c,true);
   if(CopyClose(InpGold,PERIOD_D1,1,VOL_BARS+2,c)<VOL_BARS+2 || !GoldVol(40,vol))
      return;
   int look[4]={20,60,120,250};
   double sig=0.0;
   for(int i=0; i<4; i++)
      sig+=(c[0]>c[look[i]] ? 0.25 : c[0]<c[look[i]] ? -0.25 : 0.0);
   sig=MathMax(sig,0.0);
   MqlTick q;
   double step=SymbolInfoDouble(InpGold,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(InpGold,SYMBOL_VOLUME_MIN);
   double tickValue=SymbolInfoDouble(InpGold,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(InpGold,SYMBOL_TRADE_TICK_SIZE);
   if(!SymbolInfoTick(InpGold,q) || q.ask<=0 || q.bid<=0 || step<=0 || tickSize<=0 || tickValue<=0)
      return;
   double lev=(InpHoldVolPct>0 ? SizeMult()*sig*MathMin(InpHoldMaxLeverage,InpHoldVolPct/100.0/vol) : 0.0);
   double target=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*lev/(q.ask/tickSize*tickValue)/step+1e-9)*step;
   target=MathMin(target,SymbolInfoDouble(InpGold,SYMBOL_VOLUME_MAX));
   if(target<vmin)
      target=0.0;
   double diff=NormalizeDouble(target-held,2);
   if(MathAbs(diff)<vmin || (target>0 && MathAbs(diff)<=InpHoldBand*MathMax(target,held)))
     {
      g_holdDay=day;
      return;
     }
   Prepare(InpGold,magic);
   if(diff>0)
     {
      if(q.ask-q.bid>InpGoldMaxSpread)
         return;
      double margin=0.0;
      if(OrderCalcMargin(ORDER_TYPE_BUY,InpGold,1.0,q.ask,margin) && margin>0)
         diff=MathMin(diff,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
      if(diff>=vmin && !g_trade.Buy(NormalizeDouble(diff,2),InpGold,0.0,0.0,0.0,AURUM_NAME+" hold"))
        {
         PrintFormat(AURUM_NAME+": hold buy failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         return;
        }
     }
   else
     {
      double left=-diff;
      for(int i=PositionsTotal()-1; i>=0 && left>=vmin; i--)
        {
         ulong t=PositionGetTicket(i);
         if(t==0 || PositionGetString(POSITION_SYMBOL)!=InpGold || PositionGetInteger(POSITION_MAGIC)!=magic)
            continue;
         double v=PositionGetDouble(POSITION_VOLUME);
         double cut=(left>=v || v-left<vmin ? v : NormalizeDouble(left,2));
         if(!(cut>=v ? g_trade.PositionClose(t) : g_trade.PositionClosePartial(t,cut)))
           {
            PrintFormat(AURUM_NAME+": hold close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
            return;
           }
         left-=cut;
        }
     }
   PrintFormat(AURUM_NAME+": hold, trend %.2f, volatility %.1f%%, position %.2f -> %.2f lots",sig,100.0*vol,held,target);
   g_holdDay=day;
  }

//--- month-end fix ---------------------------------------------------

// Server time of the London 4pm fix on 'day'.
datetime FixTime(datetime day)
  {
   return(day+(960+LondonOffset(day))*60);
  }

// True on the last weekday of a month.
bool FixDay(datetime day)
  {
   MqlDateTime s,n;
   TimeToStruct(day,s);
   if(s.day_of_week<1 || s.day_of_week>5)
      return(false);
   TimeToStruct(day+(s.day_of_week==5 ? 3 : 1)*86400,n);
   return(n.mon!=s.mon);
  }

// Move of the stock index over the month so far as a fraction: its last daily close before 'today' against the
// last close of the month before. False while the daily bars are missing or old.
bool FixTrend(datetime today,double &mtd)
  {
   MqlRates d[];
   ArraySetAsSeries(d,true);
   int n=CopyRates(InpStocks,PERIOD_D1,0,40,d);
   MqlDateTime s,b;
   TimeToStruct(today,s);
   double last=0.0;
   for(int i=0; i<n; i++)
     {
      if(d[i].time>=today || d[i].close<=0)
         continue;
      TimeToStruct(d[i].time,b);
      if(b.mon==s.mon)
        {
         if(last<=0)
           {
            if(today-d[i].time>5*86400)
               return(false);
            last=d[i].close;
           }
         continue;
        }
      if(last<=0)
         return(false);
      mtd=last/d[i].close-1.0;
      return(true);
     }
   return(false);
  }

// Move of 'sym' on 'day' from 'from' to 'to' minutes after the fix (negative: before it) as a fraction of the
// price. False when that day has no bar at the start.
bool FixMove(string sym,int from,int to,datetime day,double &move)
  {
   datetime f=FixTime(day);
   datetime a=f+from*60,b=f+to*60;
   int s=iBarShift(sym,PERIOD_M5,a,true);
   if(s<0)
      return(false);
   int e=iBarShift(sym,PERIOD_M5,b-300,false);
   double open=iOpen(sym,PERIOD_M5,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(sym,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// One report a day at most.
void FixNote(string text)
  {
   datetime day=DayOf(TimeCurrent());
   if(g_fixNote==day)
      return;
   g_fixNote=day;
   Print(AURUM_NAME+": fix, ",text);
  }

// The month-end fix: every pair is traded into the fix and the other way round after it; a yen cross only into it.
void Fix()
  {
   if(!g_fixOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   for(int w=0; w<2; w++)
     {
      long magic=InpMagic+FIX_MAGIC+w;
      datetime start=FixTime(today)-(w==0 ? InpFixBeforeMin*60 : 0);
      for(int i=0; i<FIX_ALL; i++)
        {
         string sym=g_fixSym[i];
         bool cross=(i>=FIX_PAIRS);
         double risk=(cross ? InpFixCrossRiskPct : InpFixRiskPct);
         if(sym=="" || (cross && w==1))
            continue;
         bool held=(HeldLots(sym,magic,opened)>0);
         if(held && now>=FixTime(DayOf(opened))+(w==0 ? 0 : InpFixAfterMin*60))
            CloseAll(sym,magic);
         if(g_fixDone[w][i]==today || now<start)
            continue;
         if(!FixDay(today) || risk<=0 || (w==1 && InpFixAfterMin<=0) || now-start>=InpFixEntrySec || held || TradedSince(sym,magic,start))
           {
            g_fixDone[w][i]=today;
            continue;
           }
         double mtd=0.0;
         if(!FixTrend(today,mtd))
           {
            FixNote("daily history of "+InpStocks+" is missing or old");
            continue;          // tried again until the entry time has run out
           }
         int dir=(mtd>0 ? 1 : mtd<0 ? -1 : 0);
         if(dir==0)
           {
            g_fixDone[w][i]=today;
            continue;
           }
         double weight=(InpFixScalePct>0 ? MathMin(100.0*MathAbs(mtd)/InpFixScalePct,InpFixCap) : 1.0);
         double sum=0.0,move;
         int n=0;
         for(int k=1; k<=2*InpDays+20 && n<InpDays; k++)
            if(FixMove(sym,w==0 ? -InpFixBeforeMin : 0,w==0 ? 0 : InpFixAfterMin,today-k*86400,move))
              {
               sum+=MathAbs(move);
               n++;
              }
         if(n<InpDays/2 || sum<=0)
           {
            PrintFormat(AURUM_NAME+": fewer than %d days of M5 history on %s, no fix trade",InpDays/2,sym);
            g_fixDone[w][i]=today;
            continue;
           }
         int side=(w==0 ? 1 : -1)*FIX_SIGN[i]*dir;
         double point=SymbolInfoDouble(sym,SYMBOL_POINT);
         int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
         MqlTick q;
         if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>(cross ? InpCrossMaxSpread : InpFxMaxSpread)*point)
            continue;          // tried again until the entry time has run out
         double dist=MathMax(InpStopMult*sum/n*q.bid,SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+q.ask-q.bid);
         double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,SizeMult()*MonthEndBoost()*risk*weight);
         if(lots<=0)
           {
            PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no fix trade",
                        sym,DoubleToString(dist,digits));
            g_fixDone[w][i]=today;
            continue;
           }
         double sl=NormalizeDouble(q.bid-side*dist,digits);
         string name=(w==0 ? AURUM_NAME+" fix" : AURUM_NAME+" after fix");
         Prepare(sym,magic);
         bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,name) : g_trade.Sell(lots,sym,0.0,sl,0.0,name));
         if(!Filled(ok))
           {
            PrintFormat(AURUM_NAME+": fix order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
            continue;
           }
         PrintFormat(AURUM_NAME+": %s the fix %s %.2f %s at %s, stop %s, %d s after the start",w==0 ? "before" : "after",
                     side>0 ? "bought" : "sold",lots,sym,DoubleToString(FillPrice(side>0 ? q.ask : q.bid),digits),DoubleToString(sl,digits),
                     (int)(now-start));
         g_fixDone[w][i]=today;
        }
     }
  }

// Move of the stock index over the InpFallDays daily bars to its last close before 'today', as a fraction.
// False while the daily bars are missing or old.
bool FallTrend(datetime today,double &chg)
  {
   MqlRates d[];
   ArraySetAsSeries(d,true);
   int n=CopyRates(InpStocks,PERIOD_D1,0,InpFallDays+10,d);
   int first=-1;
   for(int i=0; i<n; i++)
      if(d[i].time<today)
        {
         first=i;
         break;
        }
   if(first<0 || first+InpFallDays>=n || today-d[first].time>5*86400 || d[first].close<=0 || d[first+InpFallDays].close<=0)
      return(false);
   chg=d[first].close/d[first+InpFallDays].close-1.0;
   return(true);
  }

// The stock-fall fix: on a weekday that is not the month's last, after a fall of the stock index, the dollar is
// bought on every pair before the fix and sold at it.
void Fall()
  {
   if(!g_fallOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   long magic=InpMagic+FALL_MAGIC;
   datetime start=FixTime(today)-InpFallBeforeMin*60;
   MqlDateTime s;
   TimeToStruct(today,s);
   for(int i=0; i<FIX_PAIRS; i++)
     {
      string sym=g_fixSym[i];
      if(sym=="")
         continue;
      bool held=(HeldLots(sym,magic,opened)>0);
      if(held && now>=FixTime(DayOf(opened)))
         CloseAll(sym,magic);
      if(g_fallDone[i]==today || now<start)
         continue;
      if(s.day_of_week<1 || s.day_of_week>5 || FixDay(today) || now-start>=InpFixEntrySec || held || TradedSince(sym,magic,start))
        {
         g_fallDone[i]=today;
         continue;
        }
      double chg=0.0;
      if(!FallTrend(today,chg))
        {
         FixNote("daily history of "+InpStocks+" is missing or old");
         continue;             // tried again until the entry time has run out
        }
      if(chg>=-InpFallPct/100.0)
        {
         g_fallDone[i]=today;
         continue;
        }
      double sum=0.0,move;
      int n=0;
      for(int k=1; k<=2*InpDays+20 && n<InpDays; k++)
         if(FixMove(sym,-InpFallBeforeMin,0,today-k*86400,move))
           {
            sum+=MathAbs(move);
            n++;
           }
      if(n<InpDays/2 || sum<=0)
        {
         PrintFormat(AURUM_NAME+": fewer than %d days of M5 history on %s, no stock-fall fix trade",InpDays/2,sym);
         g_fallDone[i]=today;
         continue;
        }
      int side=-FIX_SIGN[i];
      double point=SymbolInfoDouble(sym,SYMBOL_POINT);
      int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      MqlTick q;
      if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpFxMaxSpread*point)
         continue;             // tried again until the entry time has run out
      double dist=MathMax(InpStopMult*sum/n*q.bid,SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+q.ask-q.bid);
      double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,SizeMult()*InpFallRiskPct);
      if(lots<=0)
        {
         PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no stock-fall fix trade",
                     sym,DoubleToString(dist,digits));
         g_fallDone[i]=today;
         continue;
        }
      double sl=NormalizeDouble(q.bid-side*dist,digits);
      Prepare(sym,magic);
      bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" stock fall") : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" stock fall"));
      if(!Filled(ok))
        {
         PrintFormat(AURUM_NAME+": stock-fall fix order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         continue;
        }
      PrintFormat(AURUM_NAME+": stocks %.1f%% in %d days, %s %.2f %s at %s into the fix, stop %s, %d s after the start",100.0*chg,
                  InpFallDays,side>0 ? "bought" : "sold",lots,sym,DoubleToString(FillPrice(side>0 ? q.ask : q.bid),digits),
                  DoubleToString(sl,digits),(int)(now-start));
      g_fallDone[i]=today;
     }
  }

// Move of the stock index from the daily close before its last one to its last close before 'today', as a
// fraction. False while the daily bars are missing or the last close is more than three days old.
bool MornTrend(datetime today,double &chg)
  {
   MqlRates d[];
   ArraySetAsSeries(d,true);
   int n=CopyRates(InpStocks,PERIOD_D1,0,10,d);
   int first=-1;
   for(int i=0; i<n; i++)
      if(d[i].time<today)
        {
         first=i;
         break;
        }
   if(first<0 || first+1>=n || today-d[first].time>3*86400 || d[first].close<=0 || d[first+1].close<=0)
      return(false);
   chg=d[first].close/d[first+1].close-1.0;
   return(true);
  }

// Move of 'sym' on 'day' over the Tokyo-morning window as a fraction of the price. False when that day has no bar
// at the start.
bool MornMove(string sym,datetime day,double &move)
  {
   datetime f=LegStart(TOKYO,day);
   int s=iBarShift(sym,PERIOD_M5,f-InpMornBeforeMin*60,true);
   if(s<0)
      return(false);
   int e=iBarShift(sym,PERIOD_M5,f+InpMornAfterMin*60-300,false);
   double open=iOpen(sym,PERIOD_M5,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(sym,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// The Tokyo morning: on a weekday after a large daily move of the stock index every pair is traded against that
// move from before the 9:55 Tokyo fixing until after it.
void Morning()
  {
   if(!g_mornOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   long magic=InpMagic+MORN_MAGIC;
   datetime start=LegStart(TOKYO,today)-InpMornBeforeMin*60;
   MqlDateTime s;
   TimeToStruct(today,s);
   for(int i=0; i<MORN_PAIRS; i++)
     {
      string sym=g_mornSym[i];
      if(sym=="")
         continue;
      bool held=(HeldLots(sym,magic,opened)>0);
      if(held && now>=LegStart(TOKYO,DayOf(opened))+InpMornAfterMin*60)
         CloseAll(sym,magic);
      if(g_mornDone[i]==today || now<start)
         continue;
      if(s.day_of_week<1 || s.day_of_week>5 || now-start>=InpFixEntrySec || held || TradedSince(sym,magic,start))
        {
         g_mornDone[i]=today;
         continue;
        }
      double chg=0.0;
      if(!MornTrend(today,chg))
        {
         FixNote("daily history of "+InpStocks+" is missing or old");
         continue;             // tried again until the entry time has run out
        }
      if(MathAbs(chg)<InpMornPct/100.0)
        {
         g_mornDone[i]=today;
         continue;
        }
      double sum=0.0,move;
      int n=0;
      for(int k=1; k<=2*InpDays+20 && n<InpDays; k++)
         if(MornMove(sym,today-k*86400,move))
           {
            sum+=MathAbs(move);
            n++;
           }
      if(n<InpDays/2 || sum<=0)
        {
         PrintFormat(AURUM_NAME+": fewer than %d days of M5 history on %s, no Tokyo-morning trade",InpDays/2,sym);
         g_mornDone[i]=today;
         continue;
        }
      int side=(chg>0 ? -1 : 1);
      double point=SymbolInfoDouble(sym,SYMBOL_POINT);
      int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      MqlTick q;
      if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpCrossMaxSpread*point)
         continue;             // tried again until the entry time has run out
      double dist=MathMax(InpStopMult*sum/n*q.bid,SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+q.ask-q.bid);
      double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,SizeMult()*InpMornRiskPct);
      if(lots<=0)
        {
         PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no Tokyo-morning trade",
                     sym,DoubleToString(dist,digits));
         g_mornDone[i]=today;
         continue;
        }
      double sl=NormalizeDouble(q.bid-side*dist,digits);
      Prepare(sym,magic);
      bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" morning") : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" morning"));
      if(!Filled(ok))
        {
         PrintFormat(AURUM_NAME+": Tokyo-morning order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         continue;
        }
      PrintFormat(AURUM_NAME+": stocks %+.1f%% in a day, %s %.2f %s at %s for the Tokyo morning, stop %s, %d s after the start",100.0*chg,
                  side>0 ? "bought" : "sold",lots,sym,DoubleToString(FillPrice(side>0 ? q.ask : q.bid),digits),
                  DoubleToString(sl,digits),(int)(now-start));
      g_mornDone[i]=today;
     }
  }

//--- after a US holiday ----------------------------------------------

// The n-th 'dow' (0 = Sunday) of the month, n = -1 for the last one (months of 31 days only).
datetime Weekday(int year,int month,int dow,int n)
  {
   MqlDateTime s;
   ZeroMemory(s);
   s.year=year;
   s.mon=month;
   s.day=(n>0 ? 1 : 31);
   datetime d=StructToTime(s);
   TimeToStruct(d,s);
   return(n>0 ? d+(((dow-s.day_of_week+7)%7)+7*(n-1))*86400 : d-((s.day_of_week-dow+7)%7)*86400);
  }

// The day a holiday with a fixed date is kept: the Friday before a Saturday, the Monday after a Sunday.
datetime Observed(int year,int month,int day)
  {
   MqlDateTime s;
   ZeroMemory(s);
   s.year=year;
   s.mon=month;
   s.day=day;
   datetime d=StructToTime(s);
   TimeToStruct(d,s);
   return(s.day_of_week==6 ? d-86400 : (s.day_of_week==0 ? d+86400 : d));
  }

// True when 'day' is a US federal holiday.
bool UsHoliday(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   int y=s.year;
   return(day==Observed(y,1,1) || day==Observed(y+1,1,1) || day==Weekday(y,1,1,3) || day==Weekday(y,2,1,3) ||
          day==Weekday(y,5,1,-1) || (y>=2021 && day==Observed(y,6,19)) || day==Observed(y,7,4) ||
          day==Weekday(y,9,1,1) || day==Weekday(y,10,1,2) || day==Observed(y,11,11) || day==Weekday(y,11,4,4) ||
          day==Observed(y,12,25));
  }

// True on the first weekday after a US federal holiday that is not one itself.
bool AfterDay(datetime day)
  {
   MqlDateTime s;
   TimeToStruct(day,s);
   if(s.day_of_week<1 || s.day_of_week>5 || UsHoliday(day))
      return(false);
   return(UsHoliday(day-(s.day_of_week==1 ? 3 : 1)*86400));
  }

// Seconds after midnight of a time given as HHMM.
int HHMMSec(int hhmm)
  {
   return((hhmm/100)*3600+(hhmm%100)*60);
  }

// Move of 'sym' on 'day' over the after-holiday window as a fraction of the price. False when that day has no bar
// at the start.
bool AfterMove(string sym,datetime day,double &move)
  {
   int s=iBarShift(sym,PERIOD_M5,day+HHMMSec(InpAfterHHMM),true);
   if(s<0)
      return(false);
   int e=iBarShift(sym,PERIOD_M5,day+HHMMSec(InpAfterExitHHMM)-300,false);
   double open=iOpen(sym,PERIOD_M5,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(sym,PERIOD_M5,e)/open-1.0;
   return(true);
  }

// After a US holiday: on the first weekday after one the dollar is bought on every pair for the London morning.
void After()
  {
   if(!g_afterOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   long magic=InpMagic+AFTER_MAGIC;
   datetime start=today+HHMMSec(InpAfterHHMM);
   for(int i=0; i<FIX_PAIRS; i++)
     {
      string sym=g_fixSym[i];
      if(sym=="")
         continue;
      bool held=(HeldLots(sym,magic,opened)>0);
      if(held && now>=DayOf(opened)+HHMMSec(InpAfterExitHHMM))
         CloseAll(sym,magic);
      if(g_afterDone[i]==today || now<start)
         continue;
      if(!AfterDay(today) || now-start>=InpAfterEntrySec || held || TradedSince(sym,magic,start))
        {
         g_afterDone[i]=today;
         continue;
        }
      double sum=0.0,move;
      int n=0;
      for(int k=1; k<=2*InpDays+20 && n<InpDays; k++)
         if(AfterMove(sym,today-k*86400,move))
           {
            sum+=MathAbs(move);
            n++;
           }
      if(n<InpDays/2 || sum<=0)
        {
         PrintFormat(AURUM_NAME+": fewer than %d days of M5 history on %s, no after-holiday trade",InpDays/2,sym);
         g_afterDone[i]=today;
         continue;
        }
      int side=-FIX_SIGN[i];
      double point=SymbolInfoDouble(sym,SYMBOL_POINT);
      int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      MqlTick q;
      if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpFxMaxSpread*point)
         continue;             // tried again until the entry time has run out
      double dist=MathMax(InpStopMult*sum/n*q.bid,SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+q.ask-q.bid);
      double lots=RiskLots(sym,side,side>0 ? q.ask : q.bid,dist,SizeMult()*InpAfterRiskPct);
      if(lots<=0)
        {
         PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no after-holiday trade",
                     sym,DoubleToString(dist,digits));
         g_afterDone[i]=today;
         continue;
        }
      double sl=NormalizeDouble(q.bid-side*dist,digits);
      Prepare(sym,magic);
      bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" after holiday") : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" after holiday"));
      if(!Filled(ok))
        {
         PrintFormat(AURUM_NAME+": after-holiday order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         continue;
        }
      PrintFormat(AURUM_NAME+": day after a US holiday, %s %.2f %s at %s for the London morning, stop %s, %d s after the start",
                  side>0 ? "bought" : "sold",lots,sym,DoubleToString(FillPrice(side>0 ? q.ask : q.bid),digits),
                  DoubleToString(sl,digits),(int)(now-start));
      g_afterDone[i]=today;
     }
  }

// High, low and last close of InpYen's M1 bars from InpBreakFromHHMM to InpBreakToHHMM of 'day'. False when more
// than 5/12 of the minutes are missing.
bool BreakRange(datetime day,double &hi,double &lo,double &last)
  {
   double h[],l[],c[];
   datetime from=day+HHMMSec(InpBreakFromHHMM),to=day+HHMMSec(InpBreakToHHMM)-60;
   int need=(HHMMSec(InpBreakToHHMM)-HHMMSec(InpBreakFromHHMM))/60*7/12;
   int n=CopyHigh(InpYen,PERIOD_M1,from,to,h);
   if(n<need || CopyLow(InpYen,PERIOD_M1,from,to,l)!=n || CopyClose(InpYen,PERIOD_M1,from,to,c)!=n)
      return(false);
   hi=h[ArrayMaximum(h)];
   lo=l[ArrayMinimum(l)];
   last=c[n-1];
   return(hi>lo && last>0);
  }

// USD/JPY London breakout: from InpBreakStartHHMM buy once the ask reaches the high of the morning range and sell
// once the bid reaches its low, each side once a day, stop at the range's other side, both closed at
// InpBreakExitHHMM. Days whose range is far from its InpBreakFilterDays-day average are skipped.
void Breakout()
  {
   if(!g_breakOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   string sym=InpYen;
   for(int s=0; s<2; s++)
      if(HeldLots(sym,InpMagic+BREAK_MAGIC+s,opened)>0 && now>=DayOf(opened)+HHMMSec(InpBreakExitHHMM))
         CloseAll(sym,InpMagic+BREAK_MAGIC+s);
   datetime start=today+HHMMSec(InpBreakStartHHMM);
   if(now<start || now>=today+HHMMSec(InpBreakExitHHMM))
      return;
   MqlDateTime t;
   TimeToStruct(today,t);
   if(t.day_of_week<1 || t.day_of_week>5)
      return;
   if(g_breakDay!=today)
     {
      g_breakDay=today;
      g_breakOk=false;
      double last,h,l,c,sum=0.0;
      int n=0;
      if(!BreakRange(today,g_breakHi,g_breakLo,last))
        {
         PrintFormat(AURUM_NAME+": no USD/JPY range for today in the M1 history, no breakout");
         return;
        }
      for(int k=1; k<=2*InpBreakFilterDays+20 && n<InpBreakFilterDays; k++)
        {
         datetime d=today-k*86400;
         MqlDateTime u;
         TimeToStruct(d,u);
         if(u.day_of_week<1 || u.day_of_week>5 || !BreakRange(d,h,l,c))
            continue;
         sum+=(h-l)/c;
         n++;
        }
      if(n<InpBreakFilterDays/2 || sum<=0)
        {
         PrintFormat(AURUM_NAME+": fewer than %d days of USD/JPY M1 history, no breakout today",InpBreakFilterDays/2);
         return;
        }
      double ratio=(g_breakHi-g_breakLo)/last/(sum/n);
      g_breakOk=(ratio>=InpBreakMinRange && ratio<=InpBreakMaxRange);
      int dg=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      PrintFormat(AURUM_NAME+": USD/JPY range %s-%s, %.2fx its %d-day average%s",DoubleToString(g_breakLo,dg),
                  DoubleToString(g_breakHi,dg),ratio,n,g_breakOk ? "" : ", no breakout today");
      // Started 5 min or more after InpBreakStartHHMM (attach or restart): a side whose level the closed M1 bars
      // already passed would have been traded at the break, so a later entry is a different trade; skip it today.
      // A running EA reads the range in the start minute; only a data gap or a blocked Run (live clock check) brings
      // it here later, where skipping is also right. Missing M1 history since the start skips both sides.
      datetime bar=now-now%60-60;
      double bh[],bl[];
      int want=(int)((bar-start)/60)+1;
      int m=(g_breakOk && now>=start+300 ? CopyHigh(sym,PERIOD_M1,start,bar,bh) : -2);
      if(m!=-2 && (m<=0 || m<want*9/10 || CopyLow(sym,PERIOD_M1,start,bar,bl)!=m))
        {
         g_breakTraded[0]=today;
         g_breakTraded[1]=today;
         PrintFormat(AURUM_NAME+": USD/JPY M1 history since the start is incomplete (%d of %d bars), no late breakout today",
                     MathMax(m,0),want);
        }
      else if(m>0)
         for(int s=0; s<2; s++)
           {
            long magic=InpMagic+BREAK_MAGIC+s;
            if((s==0 ? bh[ArrayMaximum(bh)]<g_breakHi : bl[ArrayMinimum(bl)]>g_breakLo) ||
               HeldLots(sym,magic,opened)>0 || TradedSince(sym,magic,start))
               continue;
            g_breakTraded[s]=today;
            PrintFormat(AURUM_NAME+": USD/JPY passed its range %s before this start, no late %s today",
                        s==0 ? "high" : "low",s==0 ? "buy" : "sell");
           }
     }
   if(!g_breakOk)
      return;
   MqlTick q;
   if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0)
      return;
   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   for(int s=0; s<2; s++)
     {
      int side=(s==0 ? 1 : -1);
      long magic=InpMagic+BREAK_MAGIC+s;
      if(g_breakTraded[s]==today || (side>0 ? q.ask<g_breakHi : q.bid>g_breakLo))
         continue;
      if(HeldLots(sym,magic,opened)>0 || TradedSince(sym,magic,start))
        {
         g_breakTraded[s]=today;
         continue;
        }
      if(q.ask-q.bid>InpFxMaxSpread*point)
         continue;             // tried again on the next tick
      double px=(side>0 ? q.ask : q.bid);
      double sl=NormalizeDouble(side>0 ? g_breakLo : g_breakHi,digits);
      double dist=side*(px-sl);
      if(dist<=SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point+q.ask-q.bid)
        {
         g_breakTraded[s]=today;           // already through the other side: no room for the stop
         continue;
        }
      // Nearest step: at a 10k balance the leg is 1-3 steps of USDJPY and rounding down skipped every stop over ~1 yen.
      double lots=RiskLots(sym,side,px,dist,SizeMult()*InpBreakRiskPct,true);
      if(lots<=0)
        {
         PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at a stop of %s, no breakout",sym,
                     DoubleToString(dist,digits));
         g_breakTraded[s]=today;
         continue;
        }
      Prepare(sym,magic);
      bool ok=(side>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" breakout") : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" breakout"));
      if(!Filled(ok))
        {
         PrintFormat(AURUM_NAME+": breakout order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         continue;
        }
      PrintFormat(AURUM_NAME+": USD/JPY broke its range, %s %.2f lots at %s, stop %s",side>0 ? "bought" : "sold",lots,
                  DoubleToString(FillPrice(px),digits),DoubleToString(sl,digits));
      g_breakTraded[s]=today;
     }
  }

// Bid of 'sym' at server minute 'minute' of 'day': the close of the M1 bar that ended then, else the open of the
// bar starting then. False when neither exists.
bool NoisePrice(string sym,datetime day,int minute,double &px)
  {
   datetime t=day+minute*60;
   int b=iBarShift(sym,PERIOD_M1,t-60,true);
   if(b>=0)
     {
      px=iClose(sym,PERIOD_M1,b);
      return(px>0);
     }
   b=iBarShift(sym,PERIOD_M1,t,true);
   if(b<0)
      return(false);
   px=iOpen(sym,PERIOD_M1,b);
   return(px>0);
  }

// Bands of index i for 'today': the average move from the 9:30 open to each check over the previous NOISE_DAYS
// sessions, today's open and yesterday's close, and the day's notional per unit of equity. False while history is
// short.
bool NoisePrepare(int i,datetime today)
  {
   string sym=g_noiseSym[i];
   double sum[NOISE_N],closes[];
   ArrayInitialize(sum,0.0);
   ArrayResize(closes,0);
   int n=0;
   double prevClose=0.0;
   for(int k=1; k<=3*NOISE_DAYS+15 && n<=NOISE_DAYS; k++)
     {
      datetime d=today-k*86400;
      MqlDateTime t;
      TimeToStruct(d,t);
      if(t.day_of_week<1 || t.day_of_week>5)
         continue;
      double o,c;
      if(!NoisePrice(sym,d,NOISE_OPEN,o) || !NoisePrice(sym,d,NOISE_CLOSE,c))
         continue;
      if(prevClose==0.0)
         prevClose=c;
      int m=ArraySize(closes);
      ArrayResize(closes,m+1);
      closes[m]=c;
      if(n<NOISE_DAYS)
        {
         bool full=true;
         double mv[NOISE_N];
         for(int j=0; j<NOISE_N && full; j++)
           {
            double p;
            full=NoisePrice(sym,d,NOISE_OPEN+30*(j+1),p);
            if(full)
               mv[j]=MathAbs(p/o-1.0);
           }
         if(!full)
            continue;
         for(int j=0; j<NOISE_N; j++)
            sum[j]+=mv[j];
        }
      n++;
     }
   if(n<NOISE_DAYS || ArraySize(closes)<NOISE_DAYS+1)
      return(false);
   for(int j=0; j<NOISE_N; j++)
      g_noiseSig[i][j]=sum[j]/NOISE_DAYS;
   double r[],mean=0.0,var=0.0;
   ArrayResize(r,NOISE_DAYS);
   for(int k=0; k<NOISE_DAYS; k++)
     {
      r[k]=closes[k]/closes[k+1]-1.0;
      mean+=r[k];
     }
   mean/=NOISE_DAYS;
   for(int k=0; k<NOISE_DAYS; k++)
      var+=(r[k]-mean)*(r[k]-mean);
   double vol=MathSqrt(var/(NOISE_DAYS-1)),open;
   if(vol<=0 || !NoisePrice(sym,today,NOISE_OPEN,open))
      return(false);
   g_noiseHi[i]=MathMax(open,prevClose);
   g_noiseLo[i]=MathMin(open,prevClose);
   g_noiseLev[i]=MathMin(4.0,0.02/vol);
   g_noiseVol[i]=vol;
   return(true);
  }

// Mean of the minute closes of index i from 9:30 to server minute 'minute' today.
double NoiseAverage(int i,datetime today,int minute)
  {
   double c[];
   int n=CopyClose(g_noiseSym[i],PERIOD_M1,today+(NOISE_OPEN-1)*60,today+(minute-1)*60,c);
   if(n<=0)
      return(0.0);
   double s=0.0;
   for(int k=0; k<n; k++)
      s+=c[k];
   return(s/n);
  }

// Lots of 'sym' for a notional of 'mult' x equity; 0 below the minimum lot.
double NotionalLots(string sym,int side,double price,double mult)
  {
   ENUM_ORDER_TYPE type=(side>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double pnl,margin;
   if(!OrderCalcProfit(type,sym,1.0,price,price*(1.0+0.01*side),pnl) || pnl<=0)
      return(0.0);
   double lots=AccountInfoDouble(ACCOUNT_EQUITY)*mult/(pnl/0.01);
   if(OrderCalcMargin(type,sym,1.0,price,margin) && margin>0)
      lots=MathMin(lots,AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin);
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

// Noise-area intraday momentum (Zarattini, Aziz, Barbon) on the S&P 500 and the Nasdaq: at each half hour from
// 10:00 New York buy above the upper band, sell below the lower one, close a long under max(upper band, session
// average) and a short over min(lower band, session average), flat at 16:00 New York.
void Noise()
  {
   if(!g_noiseOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   int minute=(int)((now-today)/60);
   for(int i=0; i<2; i++)
     {
      string sym=g_noiseSym[i];
      if(sym=="")
         continue;
      long magic=InpMagic+NOISE_MAGIC+i;
      double held=HeldLots(sym,magic,opened);
      if(held>0 && (minute>=NOISE_CLOSE || DayOf(opened)!=today))
        {
         CloseAll(sym,magic);
         continue;
        }
      if(g_noiseDay[i]!=today)
        {
         g_noiseDay[i]=today;
         g_noiseReady[i]=false;
         g_noiseLast[i]=-1;
        }
      if(minute<NOISE_OPEN+30 || minute>=NOISE_CLOSE)
         continue;
      int j=(minute-NOISE_OPEN)/30-1;
      if(j<0 || j>=NOISE_N || j<=g_noiseLast[i])
         continue;
      g_noiseLast[i]=j;
      if(now-(today+(NOISE_OPEN+30*(j+1))*60)>60)
         continue;                                       // too late for this check
      if(!g_noiseReady[i])
        {
         g_noiseReady[i]=NoisePrepare(i,today);
         if(!g_noiseReady[i])
           {
            PrintFormat(AURUM_NAME+": not enough M1 history on %s for the noise bands, no noise trade today",sym);
            g_noiseLast[i]=NOISE_N;
            continue;
           }
        }
      MqlTick q;
      if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0)
         continue;
      double band=(i==0 ? InpNoiseBandSpx : InpNoiseBandNdx);
      double ub=g_noiseHi[i]*(1.0+band*g_noiseSig[i][j]),lb=g_noiseLo[i]*(1.0-band*g_noiseSig[i][j]);
      double avg=NoiseAverage(i,today,NOISE_OPEN+30*(j+1));
      int side=0;
      if(held>0)
        {
         for(int k=PositionsTotal()-1; k>=0; k--)
           {
            ulong t=PositionGetTicket(k);
            if(t!=0 && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==magic)
               side=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1);
           }
         double stop=(side>0 ? (avg>0 ? MathMax(ub,avg) : ub) : (avg>0 ? MathMin(lb,avg) : lb));
         if((side>0 && q.bid<stop) || (side<0 && q.bid>stop))
           {
            if(!CloseAll(sym,magic))
               continue;
            side=0;
           }
        }
      if(side!=0 || (q.bid<=ub && q.bid>=lb))
         continue;
      if((q.ask-q.bid)/q.bid*1e4>InpNoiseMaxSpreadBp)
        {
         PrintFormat(AURUM_NAME+": %s spread %.1f bp above %.1f, no noise entry",sym,(q.ask-q.bid)/q.bid*1e4,InpNoiseMaxSpreadBp);
         continue;
        }
      int dir=(q.bid>ub ? 1 : -1);
      double lots=NotionalLots(sym,dir,dir>0 ? q.ask : q.bid,SizeMult()*InpNoiseMult*g_noiseLev[i]);
      if(lots<=0)
        {
         PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s, no noise trade",sym);
         continue;
        }
      // a broker stop three daily volatilities away, only against a lost connection; the band and average exits
      // above do the trading
      int dg=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      double px=(dir>0 ? q.ask : q.bid),sl=NormalizeDouble(px*(1.0-dir*3.0*g_noiseVol[i]),dg);
      Prepare(sym,magic);
      bool ok=(dir>0 ? g_trade.Buy(lots,sym,0.0,sl,0.0,AURUM_NAME+" noise") : g_trade.Sell(lots,sym,0.0,sl,0.0,AURUM_NAME+" noise"));
      if(!Filled(ok))
         PrintFormat(AURUM_NAME+": noise order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      else
         PrintFormat(AURUM_NAME+": %s %s %.2f lots at %.2f, bands %.2f / %.2f",sym,dir>0 ? "bought" : "sold",lots,
                     FillPrice(px),ub,lb);
     }
  }

// Move of the stock index over the US cash session of 'day' (16:00 to 23:00) as a fraction of the price. False when
// that day has no bar at the start.
bool DriftMove(datetime day,double &move)
  {
   int s=iBarShift(InpStocks,PERIOD_H1,day+16*3600,true);
   if(s<0)
      return(false);
   int e=iBarShift(InpStocks,PERIOD_H1,day+22*3600,false);
   double open=iOpen(InpStocks,PERIOD_H1,s);
   if(e<0 || e>s || open<=0)
      return(false);
   move=iClose(InpStocks,PERIOD_H1,e)/open-1.0;
   return(true);
  }

// Overnight drift: the stock index is bought for the Asian and European morning on the day after a US cash session
// in the lowest third of the last DRIFT_DAYS. No stop. 2010-2026 hourly data: 6-7 basis points a trade before cost in
// both halves, 0-1 after the other sessions; at InpDriftLev 3 the 5x rounds went from 46% to about 48.5%, which is
// inside the noise of that estimate.
void Drift()
  {
   if(!g_driftOn)
      return;
   datetime now=TimeCurrent(),today=DayOf(now),opened;
   long magic=InpMagic+DRIFT_MAGIC;
   string sym=InpStocks;
   bool held=(HeldLots(sym,magic,opened)>0);
   if(held && now>=DayOf(opened)+HHMMSec(InpDriftExitHHMM))
      CloseAll(sym,magic);
   datetime start=today+HHMMSec(InpDriftHHMM);
   if(g_driftDone==today || now<start)
      return;
   if(now-start>=InpDriftEntrySec || held || TradedSince(sym,magic,start))
     {
      g_driftDone=today;
      return;
     }
   double last=0.0,move=0.0;
   int n=0,below=0;
   bool have=false;
   for(int k=1; k<=2*DRIFT_DAYS && n<DRIFT_DAYS; k++)
     {
      if(!DriftMove(today-k*86400,move))
        {
         if(!have && k>=5)
            break;              // the last session must be less than five days back
         continue;
        }
      if(!have)
        {
         last=move;
         have=true;
         continue;
        }
      n++;
      if(move<last)
         below++;
     }
   if(!have || n<100)
     {
      PrintFormat(AURUM_NAME+": fewer than 100 days of H1 history on %s, no overnight-drift trade",sym);
      g_driftDone=today;
      return;
     }
   if(3*below>=n)
     {
      g_driftDone=today;        // the last cash session was not a weak one
      return;
     }
   MqlTick q;
   if(!SymbolInfoTick(sym,q) || q.bid<=0 || q.ask<=0 || q.ask-q.bid>InpDriftMaxSpread)
      return;                   // tried again until the entry time has run out
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double tickValue=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(step<=0 || tickSize<=0 || tickValue<=0)
      return;
   double lev=MathMin(InpDriftMaxLev,SizeMult()*InpDriftLev);
   double lots=MathFloor(AccountInfoDouble(ACCOUNT_EQUITY)*lev/(q.ask/tickSize*tickValue)/step+1e-9)*step;
   double margin=0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,sym,1.0,q.ask,margin) && margin>0)
      lots=MathMin(lots,MathFloor(AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0/margin/step+1e-9)*step);
   lots=NormalizeDouble(MathMin(lots,SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX)),2);
   if(lots<SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN))
     {
      PrintFormat(AURUM_NAME+": balance too small for the minimum lot of %s at leverage %.1f, no overnight-drift trade",sym,lev);
      g_driftDone=today;
      return;
     }
   Prepare(sym,magic);
   if(!g_trade.Buy(lots,sym,0.0,0.0,0.0,AURUM_NAME+" drift"))
     {
      PrintFormat(AURUM_NAME+": overnight-drift order on %s failed, retcode %d (%s)",sym,g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
      return;
     }
   PrintFormat(AURUM_NAME+": weak US session (%.2f%%, %d of %d lower), bought %.2f %s, leverage %.1f, until %04d",
               100.0*last,below,n,lots,sym,lev,InpDriftExitHHMM);
   g_driftDone=today;
  }

// Everything the EA does, called on every tick of the chart and once a second.
// Closes every position of the EA. Returns false if a close failed.
bool CloseEverything()
  {
   bool ok=CloseAll(InpGold,InpMagic);
   ok=CloseAll(InpGold,InpMagic+1) && ok;
   for(int leg=0; leg<LEGS; leg++)
      ok=CloseAll(LegSymbol(leg),InpMagic+2+leg) && ok;
   ok=CloseAll(InpGold,InpMagic+HOLD_MAGIC) && ok;
   if(g_gridOn)
      ok=GridCloseAll() && ok;
   for(int i=0; i<3*FIX_PAIRS; i++)
      if(g_fixSym[i%FIX_PAIRS]!="")
         ok=CloseAll(g_fixSym[i%FIX_PAIRS],InpMagic+FIX_MAGIC+i/FIX_PAIRS) && ok;
   for(int i=FIX_PAIRS; i<FIX_ALL; i++)
      if(g_fixSym[i]!="")
         ok=CloseAll(g_fixSym[i],InpMagic+FIX_MAGIC) && ok;
   for(int i=0; i<MORN_PAIRS; i++)
      if(g_mornSym[i]!="")
         ok=CloseAll(g_mornSym[i],InpMagic+MORN_MAGIC) && ok;
   for(int i=0; i<FIX_PAIRS; i++)
      if(g_fixSym[i]!="")
         ok=CloseAll(g_fixSym[i],InpMagic+AFTER_MAGIC) && ok;
   if(g_driftOn)
      ok=CloseAll(InpStocks,InpMagic+DRIFT_MAGIC) && ok;
   if(g_breakOn)
      for(int s=0; s<2; s++)
         ok=CloseAll(InpYen,InpMagic+BREAK_MAGIC+s) && ok;
   if(g_noiseOn)
      for(int i=0; i<2; i++)
         if(g_noiseSym[i]!="")
            ok=CloseAll(g_noiseSym[i],InpMagic+NOISE_MAGIC+i) && ok;
   return(ok);
  }

void Run()
  {
   if(g_halted)
      return;
   if(!AurumGuard())
      return;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peak=MathMax(g_peak,eq);
   bool drawdown=(InpMaxDrawdownPct>0 && eq<g_peak*(1.0-InpMaxDrawdownPct/100.0));
   if(!drawdown && !g_goalOver && g_goalMult>1.0 && !InpGoalRepeat && InpGoalStop)
     {
      GoalSize();               // notices the end of the round on the tick it happens
      if(g_goalOver)
         Print(AURUM_NAME+": the goal round is over, closing everything and stopping. A new round needs a new InpGoalRound");
     }
   if(drawdown || g_goalOver)
     {
      static datetime tried=0;  // a close that fails, as in a closed market, is tried again once a minute
      if(TimeCurrent()<tried+60)
         return;
      tried=TimeCurrent();
      if(drawdown)
         PrintFormat(AURUM_NAME+": equity %.2f is %.1f%% below the peak %.2f, closing and halting",eq,InpMaxDrawdownPct,g_peak);
      bool ok=CloseEverything();
      g_halted=ok;
      if(ok && g_goalOver && MQLInfoInteger(MQL_TESTER))
         TesterStop();
      return;
     }
   if(DayLossHit(eq))
      return;
   Session();
   for(int leg=0; leg<LEGS; leg++)
      Leg(leg);
   Grid();
   Hold();
   Fix();
   Fall();
   Morning();
   After();
   Breakout();
   Noise();
   Drift();
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEntryHHMM>=InpExitHHMM || InpEntryMinutes<1 || InpDipWindow<10 || InpDipHoldBars<1 || InpDipSigma<=0 ||
      InpVolSpan<2 || InpVolTargetPct<0 || InpMaxLeverage<=0 || InpBellRiskPct<0 || InpTokyoRiskPct<0 ||
      InpMeridianRiskPct<0 || InpBellLookMin<5 || InpBellLookMin%5!=0 || InpBellK<=0 || InpBellHoldMin<1 ||
      InpTokyoHoldMin<5 || InpTokyoHoldMin%5!=0 || InpStartMin<0 || InpStartMin%5!=0 || InpEndMin%5!=0 ||
      InpEndMin<InpStartMin+5 || InpEndMin>1250 || InpDays<2 || InpStopMult<=0 || InpMarginPct<=0 || InpMonthEndBoost<=0 ||
      InpBellEntrySec<1 || InpTokyoEntrySec<1 || InpMeridianEntrySec<1 || InpModelTilt<0 || InpModelTilt>1 || InpSizeMult<=0 || InpGridRiskPct<0 ||
      InpGridLevels<1 || InpGridLevels>GRID_MAX || InpGridMaDays<1 || InpGridStep<=0 || InpGridVolDays<5 ||
      InpGridMult<=0 || InpGridPanic<0 || InpHoldVolPct<0 || InpHoldMaxLeverage<=0 || InpHoldBand<0 ||
      InpSnapRiskPct<0 || InpSnapLookMin<5 || InpSnapLookMin%5!=0 || InpSnapK<=0 || InpSnapHoldSec<1 ||
      InpSnapEntrySec<1 || InpLossMult<=0 || InpLossNorm<=0 || InpFixRiskPct<0 || InpFixBeforeMin<5 ||
      InpFixBeforeMin>600 || InpFixBeforeMin%5!=0 || InpFixAfterMin<0 || InpFixAfterMin>300 || InpFixAfterMin%5!=0 ||
      InpFixEntrySec<1 || InpFixCrossRiskPct<0 || InpCrossMaxSpread<1 || InpFixScalePct<0 || InpFixCap<=0 || InpBrakePct<0 || InpBrakePct>=100 || InpBrakeCut<=0 ||
      InpBrakeCut>1 || InpBrake2Pct<0 || InpBrake2Pct>=100 || (InpBrake2Pct>0 && InpBrake2Pct<=InpBrakePct) ||
      InpBrake2Cut<=0 || InpBrake2Cut>1 || InpAcctVolPct<0 || InpAcctVolDays<20 || InpAcctVolDays>260 ||
      InpAcctVolMax<=0 || InpDayLossPct<0 || InpDayLossPct>=100 || InpFallRiskPct<0 || InpFallPct<=0 || InpFallDays<1 || InpFallDays>60 || InpFallBeforeMin<5 ||
      InpFallBeforeMin>600 || InpFallBeforeMin%5!=0 || InpMornRiskPct<0 || InpMornPct<=0 || InpMornBeforeMin<5 ||
      InpMornBeforeMin>120 || InpMornBeforeMin%5!=0 || InpMornAfterMin<0 || InpMornAfterMin>600 || InpMornAfterMin%5!=0 ||
      InpAfterRiskPct<0 || InpAfterHHMM<0 || InpAfterHHMM%100>59 || InpAfterHHMM%5!=0 || InpAfterExitHHMM%100>59 ||
      InpAfterExitHHMM%5!=0 || InpAfterExitHHMM>2355 || HHMMSec(InpAfterExitHHMM)<HHMMSec(InpAfterHHMM)+300 || InpAfterEntrySec<1 ||
      InpDriftLev<0 || InpDriftMaxLev<=0 || InpDriftHHMM<0 || InpDriftHHMM%100>59 || InpDriftExitHHMM%100>59 || InpDriftExitHHMM>2359 ||
      HHMMSec(InpDriftExitHHMM)<HHMMSec(InpDriftHHMM)+300 || InpDriftEntrySec<1 || InpDriftMaxSpread<=0 ||
      InpGoalMult<0 || (InpGoalMult>0 && InpGoalMult<=1) || (InpTarget!=0 && (InpTarget<3 || InpTarget>5)) || InpGoalDays<1 || InpGoalCap<=0 || InpGoalDayVolPct<=0 || InpGoalScale<=0 ||
      InpBreakRiskPct<0 || InpBreakFromHHMM<0 || InpBreakFromHHMM%100>59 || InpBreakToHHMM%100>59 || InpBreakStartHHMM%100>59 ||
      InpBreakExitHHMM%100>59 || InpBreakExitHHMM>2359 || HHMMSec(InpBreakToHHMM)<=HHMMSec(InpBreakFromHHMM)+3600 ||
      HHMMSec(InpBreakStartHHMM)<HHMMSec(InpBreakToHHMM) || HHMMSec(InpBreakExitHHMM)<=HHMMSec(InpBreakStartHHMM) ||
      InpBreakFilterDays<10 || InpBreakMinRange<0 || InpBreakMaxRange<=InpBreakMinRange ||
      InpNoiseMult<0 || InpNoiseBandSpx<=0 || InpNoiseBandNdx<=0 || InpNoiseMaxSpreadBp<=0 || AurumInputsBad())
      return(INIT_PARAMETERS_INCORRECT);
   // InpTarget: the goal scale with the best chance of each multiple in tools/target_odds.py (21 weekdays, 70% of
   // the edge, 2010-2025): P(target) is flat from scale 2 to 4 for all three, 2.5 is within a point of the best.
   g_goalMult=(InpTarget>0 ? (double)InpTarget : InpGoalMult);
   g_goalScale=(InpTarget>0 ? 2.5 : InpGoalScale);
   string syms[3];
   syms[0]=InpGold; syms[1]=InpYen; syms[2]=InpEuro;
   for(int i=0; i<3; i++)
     {
      if(!SymbolSelect(syms[i],true))
        {
         PrintFormat(AURUM_NAME+": symbol %s is not available",syms[i]);
         return(INIT_FAILED);
        }
      iBars(syms[i],PERIOD_M5);   // starts loading the bars the averages are built from
      iBars(syms[i],PERIOD_D1);   // and the daily bars of the sizing model
     }
   iBars(InpGold,PERIOD_M15);
   g_gridOn=(InpGridRiskPct>0);
   if(g_gridOn && !SymbolSelect(InpGridSymbol,true))
     {
      PrintFormat(AURUM_NAME+": grid symbol %s is not available, the grid is off",InpGridSymbol);
      g_gridOn=false;
     }
   if(g_gridOn)
      iBars(InpGridSymbol,PERIOD_H1);
   g_fixSym[0]=InpEuro; g_fixSym[1]=InpPound; g_fixSym[2]=InpAussie; g_fixSym[3]=InpLoonie; g_fixSym[4]=InpSwissy;
   g_fixSym[5]=InpFixCross1; g_fixSym[6]=InpFixCross2; g_fixSym[7]=InpFixCross3;
   g_fixOn=(InpFixRiskPct>0 || InpFixCrossRiskPct>0);
   g_fallOn=(InpFallRiskPct>0);
   g_mornOn=(InpMornRiskPct>0);
   g_afterOn=(InpAfterRiskPct>0);
   g_mornSym[0]=InpMorn1; g_mornSym[1]=InpMorn2; g_mornSym[2]=InpMorn3;
   if((g_fixOn || g_fallOn || g_mornOn) && !SymbolSelect(InpStocks,true))
     {
      PrintFormat(AURUM_NAME+": stock index %s is not available, both fix legs and the Tokyo-morning leg are off",InpStocks);
      g_fixOn=false; g_fallOn=false; g_mornOn=false;
     }
   if(g_mornOn)
     {
      iBars(InpStocks,PERIOD_D1);
      for(int i=0; i<MORN_PAIRS; i++)
        {
         if(SymbolSelect(g_mornSym[i],true))
            iBars(g_mornSym[i],PERIOD_M5);
         else
           {
            PrintFormat(AURUM_NAME+": symbol %s is not available, the Tokyo-morning leg leaves it out",g_mornSym[i]);
            g_mornSym[i]="";
           }
        }
     }
   if(g_fixOn || g_fallOn || g_afterOn)
     {
      if(g_fixOn || g_fallOn)
         iBars(InpStocks,PERIOD_D1);
      for(int i=1; i<FIX_ALL; i++)
        {
         if(i>=FIX_PAIRS && (!g_fixOn || InpFixCrossRiskPct<=0))
            g_fixSym[i]="";
         else if(SymbolSelect(g_fixSym[i],true))
            iBars(g_fixSym[i],PERIOD_M5);
         else
           {
            PrintFormat(AURUM_NAME+": symbol %s is not available, the fix and after-holiday legs leave it out",g_fixSym[i]);
            g_fixSym[i]="";
           }
        }
     }
   ArrayInitialize(g_fixDone,0);
   ArrayInitialize(g_fallDone,0);
   ArrayInitialize(g_mornDone,0);
   ArrayInitialize(g_afterDone,0);
   g_driftOn=(InpDriftLev>0);
   g_driftDone=0;
   g_breakOn=(InpBreakRiskPct>0);
   g_breakDay=0;
   ArrayInitialize(g_breakTraded,0);
   if(g_breakOn)
      iBars(InpYen,PERIOD_M1);
   g_noiseOn=(InpNoiseMult>0);
   g_noiseSym[0]=InpStocks;
   g_noiseSym[1]=InpNasdaq;
   for(int i=0; i<2; i++)
     {
      g_noiseDay[i]=0;
      g_noiseLast[i]=-1;
      g_noiseReady[i]=false;
      if(!g_noiseOn)
         continue;
      if(SymbolSelect(g_noiseSym[i],true))
         iBars(g_noiseSym[i],PERIOD_M1);
      else
        {
         PrintFormat(AURUM_NAME+": symbol %s is not available, the noise leg leaves it out",g_noiseSym[i]);
         g_noiseSym[i]="";
        }
     }
   if(g_driftOn && !SymbolSelect(InpStocks,true))
     {
      PrintFormat(AURUM_NAME+": stock index %s is not available, the overnight-drift leg is off",InpStocks);
      g_driftOn=false;
     }
   if(g_driftOn)
      iBars(InpStocks,PERIOD_H1);
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

// Once a day: the account leverage and the margin of 1 lot on the main symbols, so a demo or live log can be set
// against a tester run (the tester tests at its own saved leverage, not the job's: lesson 19). Logging only.
void LogMargin()
  {
   static datetime logged=0;
   datetime day=DayOf(TimeCurrent());
   if(day==logged)
      return;
   string syms[5];
   syms[0]=InpGold; syms[1]=InpYen; syms[2]=InpEuro; syms[3]=InpGridSymbol; syms[4]=InpStocks;
   string s="";
   for(int i=0; i<5; i++)
     {
      // Only symbols already in use (selected), so the tester loads no history just for this line.
      if(i>0 && !SymbolInfoInteger(syms[i],SYMBOL_SELECT))
        {
         s+=StringFormat(", %s n/a",syms[i]);
         continue;
        }
      double ask=SymbolInfoDouble(syms[i],SYMBOL_ASK),margin=0;
      bool ok=(ask>0 && OrderCalcMargin(ORDER_TYPE_BUY,syms[i],1.0,ask,margin) && margin>0);
      if(!ok && i==0)
         return;   // gold not priced yet: try again on the next tick
      s+=(ok ? StringFormat(", %s %.2f at %.6g",syms[i],margin,ask) : StringFormat(", %s n/a",syms[i]));
     }
   logged=day;
   PrintFormat(AURUM_NAME+": account leverage 1:%d, margin of 1 lot in %s%s",(int)AccountInfoInteger(ACCOUNT_LEVERAGE),
               AccountInfoString(ACCOUNT_CURRENCY),s);
  }

void OnTick()
  {
   LogMargin();
   Run();
  }

input group "Strategy Tester only"
input double InpTesterCommMult  = 1.0;   // Commission the tester charges is multiplied by this (1 = as charged)

// A test in dollars charges the cent symbols' commission in dollars, a hundred times the live cent account's.
// In the tester only, the part of each deal's commission above InpTesterCommMult times it is paid back.
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
  {
   static double owed=0;
   if(InpTesterCommMult>=1.0 || InpTesterCommMult<0 || !MQLInfoInteger(MQL_TESTER) ||
      trans.type!=TRADE_TRANSACTION_DEAL_ADD || !HistoryDealSelect(trans.deal))
      return;
   double c=HistoryDealGetDouble(trans.deal,DEAL_COMMISSION);
   if(c>=0)
      return;
   owed+=-c*(1.0-InpTesterCommMult);
   double pay=MathFloor(owed*100.0)/100.0;
   if(pay>=0.01 && TesterDeposit(pay))
      owed-=pay;
  }
//+------------------------------------------------------------------+
