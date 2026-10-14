//+------------------------------------------------------------------+
//| AurumLadder.mq5 - gold zone-recovery ladder.                     |
//| Design: docs/superpowers/specs/2026-10-09-aurumladder-design.md  |
//| One self-contained file: copy it into MQL5\Experts and compile.  |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

// LadderTest.mq5 defines AURUMLADDER_NO_EA to include the maths below without the inputs and event handlers.
#ifndef AURUMLADDER_NO_EA
input group "Signal (M15)"
input int    InpLookback       = 64;    // Regression lookback, bars
input double InpTStatMin       = 3.0;   // Minimum |slope t-statistic|
input double InpEffMin         = 0.25;  // Minimum efficiency ratio

input group "Zone"
input int    InpAtrPeriod      = 14;    // ATR period
input double InpStepAtr        = 1.5;   // Zone width d, x ATR
input double InpTargetAtr      = 1.5;   // Target t, x ATR
input double InpTargetSpreads  = 5.0;   // Target must be at least this many x spread allowance
input double InpProfitMin      = 7.0;   // Profit of a won ladder, at least, account currency (cents on a cent account)
input double InpProfitMax      = 12.0;  // Profit of a won ladder, at most; a wider target is pulled in

input group "Ladder"
input int    InpMaxSteps       = 6;     // Step cap N (tune 4-8)
input double InpLossCapPct     = 5.0;   // Failed-ladder loss cap, % of balance
input double InpMarginPct      = 50.0;  // Ladder margin cap, % of free margin
input double InpCommissionLot  = 0.0;   // Round-trip commission per lot, account currency

input group "Risk guard"
input double InpMaxSpread      = 0.40;  // Spread filter and sizing allowance s, price units
input int    InpCooldownHours  = 0;     // Pause after a failed ladder, hours (0 = none)
input int    InpMaxFailsPerDay = 2;     // Failed ladders before stopping for the day (0 = no limit)
input bool   InpRestartNow     = true;  // Start the next ladder as soon as one closes, without waiting for a signal
input int    InpNoNewMinutes   = 180;   // No new ladder within this of Friday close
input int    InpFlattenMinutes = 15;    // Close open ladder this long before Friday close
input int    InpFridayCloseMin = 1435;  // Fallback Friday close, minutes after midnight (server)

input group "Execution"
input long   InpMagic          = 245001; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points
#endif

//+------------------------------------------------------------------+
//| Broker - symbol and account specifications, read at run time.    |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| Signal - direction signal (spec section 1).                      |
//| closes[] is oldest first. Mirrors tools/ladder_model.py.          |
//+------------------------------------------------------------------+
// t-statistic of the least-squares slope of ln(close) against bar index.
double AL_RegressionTStat(const double &closes[],const int n)
  {
   double xm=(n-1)/2.0,ym=0.0;
   for(int i=0; i<n; i++)
      ym+=MathLog(closes[i]);
   ym/=n;
   double sxx=0.0,sxy=0.0;
   for(int i=0; i<n; i++)
     {
      sxx+=(i-xm)*(i-xm);
      sxy+=(i-xm)*(MathLog(closes[i])-ym);
     }
   double b=sxy/sxx,sse=0.0;
   for(int i=0; i<n; i++)
     {
      double r=MathLog(closes[i])-ym-b*(i-xm);
      sse+=r*r;
     }
   if(sse<=1e-18)
      return(b>0 ? 1e9 : (b<0 ? -1e9 : 0.0));
   return(b/MathSqrt(sse/(n-2)/sxx));
  }

// |net move| / total path over the window.
double AL_EfficiencyRatio(const double &closes[],const int n)
  {
   double path=0.0;
   for(int i=1; i<n; i++)
      path+=MathAbs(closes[i]-closes[i-1]);
   return(path>0 ? MathAbs(closes[n-1]-closes[0])/path : 0.0);
  }

// +1 buy, -1 sell, 0 no trade.
int AL_Direction(const double &closes[],const int n,const double tMin,const double erMin)
  {
   double t=AL_RegressionTStat(closes,n);
   if(MathAbs(t)>=tMin && AL_EfficiencyRatio(closes,n)>=erMin)
      return(t>0 ? 1 : -1);
   return(0);
  }

//+------------------------------------------------------------------+
//| Ladder - pure ladder maths (spec section 4). No trading calls.   |
//| Mirrors tools/ladder_model.py; keep the two in step.              |
//| Distances are price units; trade numbers n are 1-based.           |
//+------------------------------------------------------------------+
#define AL_EPS 1e-9

struct LadderParams
  {
   double            d;      // zone width
   double            t;      // target distance beyond an edge
   double            s;      // spread allowance
   double            c;      // round-trip commission per lot, price units
   double            step;   // broker lot step
   double            vmin;   // broker minimum lot
   double            vmax;   // broker maximum lot
  };

double AL_RoundUp(const double lot,const double step)
  {
   return NormalizeDouble(MathCeil(lot/step-AL_EPS)*step,8);
  }

// Lots on trade n's side (w) and the opposite side (x) over trades 1..n-1.
void AL_SideSums(const double &lots[],const int n,double &w,double &x)
  {
   w=0.0;
   x=0.0;
   for(int k=1; k<n; k++)
     {
      if(k%2==n%2)
         w+=lots[k-1];
      else
         x+=lots[k-1];
     }
  }

// Fills lots[0..nMax-1]. False when a lot would exceed the broker maximum.
bool AL_LadderLots(const double l1,const int nMax,const LadderParams &p,double &lots[])
  {
   ArrayResize(lots,nMax);
   lots[0]=l1;
   double pi=l1*(p.t-p.c);
   for(int n=2; n<=nMax; n++)
     {
      double w,x;
      AL_SideSums(lots,n,w,x);
      double ln=(pi+(p.d+p.t+p.s)*x+p.c*(w+x)-p.t*w)/(p.t-p.c);
      ln=MathMax(AL_RoundUp(ln,p.step),p.vmin);
      if(ln>p.vmax+AL_EPS)
         return(false);
      lots[n-1]=ln;
     }
   return(true);
  }

// Lot x price profit when trade n is the latest fill and its side reaches target.
double AL_BasketProfit(const double &lots[],const int n,const LadderParams &p)
  {
   double w,x;
   AL_SideSums(lots,n,w,x);
   w+=lots[n-1];
   return(p.t*w-(p.d+p.t+p.s)*x-p.c*(w+x));
  }

// Lot x price loss (positive) when the last trade of the ladder is stopped out.
double AL_FailedLoss(const double &lots[],const LadderParams &p)
  {
   int n=ArraySize(lots);
   double w=0.0,x=0.0;
   for(int k=1; k<=n; k++)
     {
      if(k%2==n%2)
         w+=lots[k-1];
      else
         x+=lots[k-1];
     }
   return((p.d+p.t+p.s)*w-p.t*x+p.c*(w+x));
  }

// Largest first lot whose failed ladder loses at most capMoney and whose total
// margin stays within marginLimit. Reduces N while even the minimum lot fails;
// returns false when N would fall below 3. v = money per lot per 1.00 price move.
bool AL_FirstLot(const double capMoney,const int nMax,const LadderParams &p,const double v,
                 const double marginPerLot,const double marginLimit,double &lots[])
  {
   for(int n=nMax; n>=3; n--)
     {
      double best[];
      bool   found=false;
      for(long k=(long)MathRound(p.vmin/p.step); ; k++)
        {
         double l1=NormalizeDouble(k*p.step,8);
         if(l1>p.vmax+AL_EPS)
            break;
         double cand[];
         if(!AL_LadderLots(l1,n,p,cand))
            break;
         double sum=0.0;
         for(int i=0; i<n; i++)
            sum+=cand[i];
         if(v*AL_FailedLoss(cand,p)>capMoney+AL_EPS || marginPerLot*sum>marginLimit+AL_EPS)
            break;
         ArrayResize(best,n);
         ArrayCopy(best,cand);
         found=true;
        }
      if(found)
        {
         ArrayResize(lots,n);
         ArrayCopy(lots,best);
         return(true);
        }
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| RiskGuard - spread, weekend, daily stop (spec section 6).        |
//| Cooldown and the failure count are persisted by the cycle below.  |
//+------------------------------------------------------------------+
struct GuardParams
  {
   double            maxSpread;        // price units; also the sizing allowance s
   int               noNewMinutes;     // before Friday close
   int               flattenMinutes;   // before Friday close
   long              fridayCloseSec;   // fallback when the session table is empty
   int               maxFailsPerDay;
  };

bool AL_SpreadOk(const string symbol,const double maxSpread)
  {
   return(SymbolInfoDouble(symbol,SYMBOL_ASK)-SymbolInfoDouble(symbol,SYMBOL_BID)<=maxSpread+1e-9);
  }

// Seconds until Friday's close, or a large number on any other day.
long AL_SecondsToFridayClose(const string symbol,const GuardParams &g,const datetime now)
  {
   MqlDateTime dt;
   TimeToStruct(now,dt);
   if(dt.day_of_week!=FRIDAY)
      return(LONG_MAX);
   long closeSec=AL_FridayCloseSeconds(symbol);
   if(closeSec<=0)
      closeSec=g.fridayCloseSec;
   long sinceMidnight=dt.hour*3600+dt.min*60+dt.sec;
   return(closeSec-sinceMidnight);
  }

bool AL_WeekendBlocksNew(const string symbol,const GuardParams &g,const datetime now)
  {
   return(AL_SecondsToFridayClose(symbol,g,now)<(long)g.noNewMinutes*60);
  }

bool AL_WeekendForcesFlat(const string symbol,const GuardParams &g,const datetime now)
  {
   return(AL_SecondsToFridayClose(symbol,g,now)<(long)g.flattenMinutes*60);
  }

long AL_ServerDay(const datetime now)
  {
   return((long)now/86400);
  }

//+------------------------------------------------------------------+
//| Cycle - ladder state machine, orders, basket close and           |
//| restart recovery (spec sections 3 and 5).                        |
//|                                                                  |
//| State lives in terminal global variables under "AL_<magic>_" so  |
//| a restarted EA resumes the same ladder.                          |
//+------------------------------------------------------------------+

// Results of finished ladders, for the tester summary and acceptance checks.
struct LadderStats
  {
   int               ladders;
   int               wins;
   int               firstStepWins;   // closed in profit with only trade 1 filled
   int               losses;
   int               stepCapLosses;   // all N trades filled, then stopped out
   double            worstLossPct;    // largest single-ladder loss, % of balance at its start
   int               fillsHist[10];   // ladders by trades filled (index 9 = 9 or more)
  };

enum ENUM_AL_STATE
  {
   AL_FLAT=0,
   AL_LADDERING=1,
   AL_CLOSING=2,      // basket exit in progress; retried each tick until empty
   AL_COOLDOWN=3
  };

class CLadderCycle
  {
private:
   CTrade            m_trade;
   BrokerSpec        m_b;
   long              m_magic;
   string            m_pfx;
   int               m_cooldownSec;
   int               m_maxFailsPerDay;

   // ladder state, mirrored in global variables
   ENUM_AL_STATE     m_state;
   int               m_side1;       // +1 buy, -1 sell
   double            m_upper;
   double            m_lower;
   double            m_d;
   double            m_t;
   double            m_s;
   int               m_n;           // step cap for this ladder
   int               m_filled;      // trades filled so far
   datetime          m_start;
   double            m_lots[];
   bool              m_exitSeen;    // a closing deal was seen since the ladder started
   double            m_startBal;    // balance when the ladder opened
   string            m_csv;         // per-ladder log in the terminals' common Files folder

   string            Key(const string name) const { return(m_pfx+name); }
   void              SetGV(const string name,const double v) { GlobalVariableSet(Key(name),v); }
   double            GetGV(const string name,const double dflt) const
     {
      return(GlobalVariableCheck(Key(name)) ? GlobalVariableGet(Key(name)) : dflt);
     }

   int               SideOf(const int k) const { return(k%2==1 ? m_side1 : -m_side1); }
   void              Save();
   void              Load();
   int               CountPositions();
   int               CountOrders();
   bool              PlaceStep(const int k);
   bool              CloseAll();
   double            RealisedSinceStart();
   void              Finalise();
   void              Record(const double pnl);
   void              Log(const string msg) const { PrintFormat("AurumLadder[%I64d] %s",m_magic,msg); }

public:
   LadderStats       stats;

                     CLadderCycle() : m_state(AL_FLAT), m_exitSeen(false), m_startBal(0) { ZeroMemory(stats); }
   bool              Init(const BrokerSpec &b,const long magic,const int deviationPoints,
                          const int cooldownHours,const int maxFailsPerDay);
   ENUM_AL_STATE     State() const { return(m_state); }
   bool              CanStart(const datetime now);
   bool              Start(const int side,const double d,const double t,const double s,
                           const double &lots[]);
   void              OnTickManage(const bool forceFlat);
   void              OnTradeEvent();
  };

//+------------------------------------------------------------------+
bool CLadderCycle::Init(const BrokerSpec &b,const long magic,const int deviationPoints,
                        const int cooldownHours,const int maxFailsPerDay)
  {
   m_b=b;
   m_magic=magic;
   m_pfx="AL_"+IntegerToString(magic)+"_";
   m_cooldownSec=cooldownHours*3600;
   m_maxFailsPerDay=maxFailsPerDay;
   m_trade.SetExpertMagicNumber((ulong)magic);
   m_trade.SetDeviationInPoints(deviationPoints);
   m_trade.SetTypeFillingBySymbol(b.symbol);
   bool tester=(bool)MQLInfoInteger(MQL_TESTER);
   m_csv=(bool)MQLInfoInteger(MQL_OPTIMIZATION) ? ""
         : "AurumLadder_"+IntegerToString(magic)+(tester ? "_tester" : "_live")+".csv";
   if(tester && m_csv!="")
      FileDelete(m_csv,FILE_COMMON);
   Load();

   int pos=CountPositions(),ord=CountOrders();
   if(m_state==AL_LADDERING || m_state==AL_CLOSING)
     {
      if(pos==0)
        {
         // Basket exited while the EA was offline.
         if(ord>0)
            CloseAll();
         Finalise();
        }
      else
         Log(StringFormat("resumed ladder: %d of %d filled, zone %.2f-%.2f",
                          m_filled,m_n,m_lower,m_upper));
     }
   else if(pos>0 || ord>0)
     {
      Log("positions or orders exist without a saved zone; closing them rather than guessing");
      m_state=AL_CLOSING;
      Save();
     }
   return(true);
  }

//+------------------------------------------------------------------+
void CLadderCycle::Save()
  {
   SetGV("state",(double)m_state);
   SetGV("side1",m_side1);
   SetGV("upper",m_upper);
   SetGV("lower",m_lower);
   SetGV("d",m_d);
   SetGV("t",m_t);
   SetGV("s",m_s);
   SetGV("n",m_n);
   SetGV("filled",m_filled);
   SetGV("start",(double)m_start);
   SetGV("startbal",m_startBal);
   for(int i=0; i<ArraySize(m_lots); i++)
      SetGV("lot"+IntegerToString(i+1),m_lots[i]);
  }

void CLadderCycle::Load()
  {
   m_state =(ENUM_AL_STATE)(int)GetGV("state",AL_FLAT);
   m_side1 =(int)GetGV("side1",1);
   m_upper =GetGV("upper",0);
   m_lower =GetGV("lower",0);
   m_d     =GetGV("d",0);
   m_t     =GetGV("t",0);
   m_s     =GetGV("s",0);
   m_n     =(int)GetGV("n",0);
   m_filled=(int)GetGV("filled",0);
   m_start =(datetime)(long)GetGV("start",0);
   m_startBal=GetGV("startbal",0);
   ArrayResize(m_lots,m_n);
   for(int i=0; i<m_n; i++)
      m_lots[i]=GetGV("lot"+IntegerToString(i+1),0);
   if((m_state==AL_LADDERING || m_state==AL_CLOSING) && (m_n<1 || m_upper<=0))
      m_state=AL_CLOSING;   // zone missing: flatten, never guess
  }

//+------------------------------------------------------------------+
int CLadderCycle::CountPositions()
  {
   int cnt=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk>0 && PositionGetInteger(POSITION_MAGIC)==m_magic
         && PositionGetString(POSITION_SYMBOL)==m_b.symbol)
         cnt++;
     }
   return(cnt);
  }

int CLadderCycle::CountOrders()
  {
   int cnt=0;
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      ulong tk=OrderGetTicket(i);
      if(tk>0 && OrderGetInteger(ORDER_MAGIC)==m_magic && OrderGetString(ORDER_SYMBOL)==m_b.symbol)
         cnt++;
     }
   return(cnt);
  }

//+------------------------------------------------------------------+
//| Places trade k: a stop order at its edge, or a market order when  |
//| price is already through the edge.                                |
//+------------------------------------------------------------------+
bool CLadderCycle::PlaceStep(const int k)
  {
   int    side=SideOf(k);
   double lot =AL_NormLot(m_b,m_lots[k-1]);
   string cmt ="AL#"+IntegerToString(k);
   double ask =SymbolInfoDouble(m_b.symbol,SYMBOL_ASK);
   double bid =SymbolInfoDouble(m_b.symbol,SYMBOL_BID);
   bool   ok;
   if(side>0)
     {
      double tp=AL_NormPrice(m_b,m_upper+m_t);
      double sl=AL_NormPrice(m_b,m_lower-m_t-m_s);
      double px=AL_NormPrice(m_b,m_upper);
      if(px-ask>m_b.stopsDist)
         ok=m_trade.BuyStop(lot,px,m_b.symbol,sl,tp,ORDER_TIME_GTC,0,cmt);
      else
         ok=m_trade.Buy(lot,m_b.symbol,ask,sl,tp,cmt);
     }
   else
     {
      double tp=AL_NormPrice(m_b,m_lower-m_t);
      double sl=AL_NormPrice(m_b,m_upper+m_t+m_s);
      double px=AL_NormPrice(m_b,m_lower);
      if(bid-px>m_b.stopsDist)
         ok=m_trade.SellStop(lot,px,m_b.symbol,sl,tp,ORDER_TIME_GTC,0,cmt);
      else
         ok=m_trade.Sell(lot,m_b.symbol,bid,sl,tp,cmt);
     }
   uint rc=m_trade.ResultRetcode();
   if(!ok || (rc!=TRADE_RETCODE_DONE && rc!=TRADE_RETCODE_PLACED))
     {
      Log(StringFormat("step %d (%s %.2f) failed: %u %s",k,side>0?"buy":"sell",lot,rc,
                       m_trade.ResultRetcodeDescription()));
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
bool CLadderCycle::CloseAll()
  {
   for(int i=OrdersTotal()-1; i>=0; i--)
     {
      ulong tk=OrderGetTicket(i);
      if(tk>0 && OrderGetInteger(ORDER_MAGIC)==m_magic && OrderGetString(ORDER_SYMBOL)==m_b.symbol)
         m_trade.OrderDelete(tk);
     }
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk>0 && PositionGetInteger(POSITION_MAGIC)==m_magic
         && PositionGetString(POSITION_SYMBOL)==m_b.symbol)
         m_trade.PositionClose(tk);
     }
   return(CountPositions()==0 && CountOrders()==0);
  }

double CLadderCycle::RealisedSinceStart()
  {
   double pnl=0.0;
   if(!HistorySelect(m_start,TimeCurrent()+60))
      return(0.0);
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong tk=HistoryDealGetTicket(i);
      if(tk==0 || HistoryDealGetInteger(tk,DEAL_MAGIC)!=m_magic
         || HistoryDealGetString(tk,DEAL_SYMBOL)!=m_b.symbol)
         continue;
      pnl+=HistoryDealGetDouble(tk,DEAL_PROFIT)+HistoryDealGetDouble(tk,DEAL_COMMISSION)
           +HistoryDealGetDouble(tk,DEAL_SWAP)+HistoryDealGetDouble(tk,DEAL_FEE);
     }
   return(pnl);
  }

//+------------------------------------------------------------------+
//| Basket is empty: book the result, set cooldown and daily count.   |
//+------------------------------------------------------------------+
void CLadderCycle::Finalise()
  {
   double   pnl=(m_start>0 ? RealisedSinceStart() : 0.0);
   datetime now=TimeCurrent();
   bool     failed=(pnl<0);
   Log(StringFormat("ladder closed after %d of %d steps, result %.2f %s",m_filled,m_n,pnl,
                    AccountInfoString(ACCOUNT_CURRENCY)));
   if(m_start>0)
      Record(pnl);
   GlobalVariablesDeleteAll(m_pfx+"lot");
   m_state=AL_FLAT;
   m_filled=0;
   m_n=0;
   m_start=0;
   m_exitSeen=false;
   ArrayResize(m_lots,0);
   if(failed)
     {
      long day=AL_ServerDay(now);
      int  fails=((long)GetGV("failday",-1)==day ? (int)GetGV("fails",0) : 0)+1;
      SetGV("failday",(double)day);
      SetGV("fails",fails);
      SetGV("cooldown",(double)(now+m_cooldownSec));
      m_state=AL_COOLDOWN;
     }
   Save();
  }

//+------------------------------------------------------------------+
void CLadderCycle::Record(const double pnl)
  {
   double pct=(m_startBal>0 ? 100.0*pnl/m_startBal : 0.0);
   stats.ladders++;
   stats.fillsHist[MathMin(MathMax(m_filled,0),9)]++;
   if(pnl>=0)
     {
      stats.wins++;
      if(m_filled==1)
         stats.firstStepWins++;
     }
   else
     {
      stats.losses++;
      if(m_filled>=m_n)
         stats.stepCapLosses++;
      stats.worstLossPct=MathMax(stats.worstLossPct,-pct);
     }
   if(m_csv=="")
      return;
   int h=FileOpen(m_csv,FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(h==INVALID_HANDLE)
      return;
   if(FileSize(h)==0)
      FileWrite(h,"start","end","side","d","t","n","filled","lot1","pnl","pnl_pct","balance_before");
   FileSeek(h,0,SEEK_END);
   FileWrite(h,TimeToString(m_start+1,TIME_DATE|TIME_SECONDS),
             TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
             m_side1>0 ? "buy" : "sell",DoubleToString(m_d,2),DoubleToString(m_t,2),m_n,m_filled,
             DoubleToString(ArraySize(m_lots)>0 ? m_lots[0] : 0,2),DoubleToString(pnl,2),
             DoubleToString(pct,3),DoubleToString(m_startBal,2));
   FileClose(h);
  }

//+------------------------------------------------------------------+
bool CLadderCycle::CanStart(const datetime now)
  {
   if(m_state==AL_COOLDOWN)
     {
      if(now<(datetime)(long)GetGV("cooldown",0))
         return(false);
      m_state=AL_FLAT;
      Save();
     }
   if(m_state!=AL_FLAT)
      return(false);
   if(m_maxFailsPerDay>0 && (long)GetGV("failday",-1)==AL_ServerDay(now) && (int)GetGV("fails",0)>=m_maxFailsPerDay)
      return(false);
   return(true);
  }

//+------------------------------------------------------------------+
//| Opens trade 1 at market, freezes the zone around its fill price,  |
//| then places trade 2 as a pending stop.                            |
//+------------------------------------------------------------------+
bool CLadderCycle::Start(const int side,const double d,const double t,const double s,
                         const double &lots[])
  {
   double lot=AL_NormLot(m_b,lots[0]);
   bool ok=(side>0 ? m_trade.Buy(lot,m_b.symbol,0,0,0,"AL#1")
                   : m_trade.Sell(lot,m_b.symbol,0,0,0,"AL#1"));
   if(!ok || m_trade.ResultRetcode()!=TRADE_RETCODE_DONE)
     {
      Log(StringFormat("first trade failed: %u %s",m_trade.ResultRetcode(),
                       m_trade.ResultRetcodeDescription()));
      return(false);
     }

   ulong  ticket=0;
   double fill=0.0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong tk=PositionGetTicket(i);
      if(tk>0 && PositionGetInteger(POSITION_MAGIC)==m_magic
         && PositionGetString(POSITION_SYMBOL)==m_b.symbol)
        {
         ticket=tk;
         fill=PositionGetDouble(POSITION_PRICE_OPEN);
        }
     }
   if(ticket==0)
      fill=m_trade.ResultPrice();

   m_side1=side;
   m_d=d;
   m_t=t;
   m_s=s;
   m_n=ArraySize(lots);
   ArrayResize(m_lots,m_n);
   ArrayCopy(m_lots,lots);
   m_upper=(side>0 ? fill : fill+d);
   m_lower=(side>0 ? fill-d : fill);
   m_filled=1;
   m_start=TimeCurrent()-1;
   m_startBal=AccountInfoDouble(ACCOUNT_BALANCE);
   m_exitSeen=false;
   m_state=AL_LADDERING;
   Save();

   double tp=AL_NormPrice(m_b,side>0 ? m_upper+t : m_lower-t);
   double sl=AL_NormPrice(m_b,side>0 ? m_lower-t-s : m_upper+t+s);
   if(ticket==0 || !m_trade.PositionModify(ticket,sl,tp))
     {
      Log("could not attach stop-loss/take-profit to trade 1; closing the ladder");
      m_state=AL_CLOSING;
      Save();
      return(false);
     }
   Log(StringFormat("ladder start: %s %.2f at %.2f, zone %.2f-%.2f, N=%d",
                    side>0?"buy":"sell",lot,fill,m_lower,m_upper,m_n));
   PlaceStep(2);
   return(true);
  }

//+------------------------------------------------------------------+
void CLadderCycle::OnTradeEvent()
  {
   if(m_state!=AL_LADDERING || m_start==0)
      return;
   if(!HistorySelect(m_start,TimeCurrent()+60))
      return;
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong tk=HistoryDealGetTicket(i);
      if(tk==0 || HistoryDealGetInteger(tk,DEAL_MAGIC)!=m_magic
         || HistoryDealGetString(tk,DEAL_SYMBOL)!=m_b.symbol)
         continue;
      ENUM_DEAL_ENTRY e=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(tk,DEAL_ENTRY);
      if(e==DEAL_ENTRY_OUT || e==DEAL_ENTRY_OUT_BY || e==DEAL_ENTRY_INOUT)
        {
         m_exitSeen=true;
         return;
        }
     }
  }

//+------------------------------------------------------------------+
void CLadderCycle::OnTickManage(const bool forceFlat)
  {
   if(m_state==AL_LADDERING)
     {
      int pos=CountPositions();
      if(forceFlat)
        {
         Log("weekend close approaching; flattening the ladder");
         m_state=AL_CLOSING;
         Save();
        }
      else if(m_exitSeen || pos<m_filled)
        {
         // Any take-profit or stop-loss ends the ladder; close what is left.
         m_state=AL_CLOSING;
         Save();
        }
      else if(pos>m_filled)
        {
         m_filled=pos;
         Save();
         Log(StringFormat("step %d filled",m_filled));
         if(m_filled<m_n)
            PlaceStep(m_filled+1);
        }
      else if(m_filled<m_n && CountOrders()==0)
         PlaceStep(m_filled+1);   // re-place a missing or rejected reversal order
     }
   if(m_state==AL_CLOSING && CloseAll())
      Finalise();
  }

#ifndef AURUMLADDER_NO_EA
BrokerSpec   g_broker;
GuardParams  g_guard;
CLadderCycle g_cycle;
int          g_atr=INVALID_HANDLE;
datetime     g_lastBar=0;
datetime     g_lastWarn=0;

// Skip-reason messages would repeat every bar; print them at most once a day.
bool WarnDue()
  {
   if(TimeCurrent()-g_lastWarn<86400)
      return(false);
   g_lastWarn=TimeCurrent();
   return(true);
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(!AL_IsHedging())
     {
      Print("AurumLadder needs a hedging account; this one is netting. Stopping.");
      return(INIT_FAILED);
     }
   if(!AL_LoadBroker(_Symbol,g_broker))
     {
      Print("AurumLadder could not read the symbol specification for ",_Symbol);
      return(INIT_FAILED);
     }
   if(InpMaxSteps<3 || InpLookback<8 || InpLossCapPct<=0 || InpProfitMin<=0 || InpProfitMax<InpProfitMin || InpCooldownHours<0)
      return(INIT_PARAMETERS_INCORRECT);

   g_guard.maxSpread     =InpMaxSpread;
   g_guard.noNewMinutes  =InpNoNewMinutes;
   g_guard.flattenMinutes=InpFlattenMinutes;
   g_guard.fridayCloseSec=(long)InpFridayCloseMin*60;
   g_guard.maxFailsPerDay=InpMaxFailsPerDay;

   g_atr=iATR(_Symbol,PERIOD_M15,InpAtrPeriod);
   if(g_atr==INVALID_HANDLE)
      return(INIT_FAILED);
   if(!g_cycle.Init(g_broker,InpMagic,InpDeviation,InpCooldownHours,InpMaxFailsPerDay))
      return(INIT_FAILED);
   EventSetTimer(1);
   PrintFormat("AurumLadder ready on %s: V=%.2f %s per lot per 1.00, lot %.2f-%.2f step %.2f, stops %.2f",
               _Symbol,g_broker.v,AccountInfoString(ACCOUNT_CURRENCY),g_broker.vmin,g_broker.vmax,
               g_broker.step,g_broker.stopsDist);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_atr!=INVALID_HANDLE)
      IndicatorRelease(g_atr);
  }

//+------------------------------------------------------------------+
//| While flat: guards, signal, sizing, start. Once per M15 bar, and   |
//| again at once after a ladder closes when InpRestartNow is set.    |
//+------------------------------------------------------------------+
void TryStart()
  {
   datetime bar=iTime(_Symbol,PERIOD_M15,0);
   if(bar==0 || bar==g_lastBar)
      return;
   datetime now=TimeCurrent();
   if(!g_cycle.CanStart(now) || !AL_SpreadOk(_Symbol,g_guard.maxSpread)
      || AL_WeekendBlocksNew(_Symbol,g_guard,now))
      return;
   g_lastBar=bar;

   double closes[];
   if(CopyClose(_Symbol,PERIOD_M15,1,InpLookback,closes)!=InpLookback)
      return;
   int side=AL_Direction(closes,InpLookback,InpTStatMin,InpEffMin);
   // No signal: with InpRestartNow the ladder still starts, along the slope of the lookback.
   if(side==0 && InpRestartNow)
      side=(AL_RegressionTStat(closes,InpLookback)>=0 ? 1 : -1);
   if(side==0)
      return;

   double atr[];
   if(CopyBuffer(g_atr,0,1,1,atr)!=1 || atr[0]<=0)
      return;

   LadderParams p;
   p.d   =InpStepAtr*atr[0];
   p.t   =InpTargetAtr*atr[0];
   p.s   =InpMaxSpread;
   p.c   =InpCommissionLot/g_broker.v;
   p.step=g_broker.step;
   p.vmin=g_broker.vmin;
   p.vmax=g_broker.vmax;

   // First lot: the smallest whose won ladder pays InpProfitMin. A target so wide that this lot would pay more
   // than InpProfitMax is pulled in. Later lots are rounded up, so a ladder won at a late step can pay a little more.
   double l1=g_broker.vmin;
   if(p.t>p.c)
     {
      l1=MathMax(g_broker.vmin,AL_RoundUp(InpProfitMin/(g_broker.v*(p.t-p.c)),g_broker.step));
      if(g_broker.v*l1*(p.t-p.c)>InpProfitMax)
         p.t=p.c+InpProfitMax/(g_broker.v*l1);
     }

   // Floors: the target must dwarf the spread, and every stop order and SL/TP
   // must clear the broker's minimum distance even at the widest allowed spread.
   double minDist=g_broker.stopsDist+p.s;
   if(p.t<InpTargetSpreads*p.s || p.d<=minDist || p.t<=minDist || p.t<=p.c)
     {
      if(WarnDue())
         PrintFormat("AurumLadder: zone too small (d=%.2f t=%.2f, need > %.2f and t >= %.2f); skipping",
                  p.d,p.t,minDist,InpTargetSpreads*p.s);
      return;
     }

   double mpl=AL_MarginPerLot(g_broker);
   if(mpl<0)
      return;
   double cap=AccountInfoDouble(ACCOUNT_BALANCE)*InpLossCapPct/100.0;
   double marginLimit=AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0;
   // Fewer steps while the failed ladder would break the loss cap or the margin limit.
   double lots[];
   bool   fits=false;
   for(int n=InpMaxSteps; n>=3 && !fits; n--)
     {
      if(!AL_LadderLots(l1,n,p,lots))
         continue;
      double sum=0.0;
      for(int i=0; i<n; i++)
         sum+=lots[i];
      fits=(g_broker.v*AL_FailedLoss(lots,p)<=cap+AL_EPS && mpl*sum<=marginLimit+AL_EPS);
     }
   if(!fits)
     {
      if(!WarnDue())
         return;
      double needed=0.0;
      if(AL_LadderLots(l1,3,p,lots))
         needed=g_broker.v*AL_FailedLoss(lots,p)*100.0/InpLossCapPct;
      PrintFormat("AurumLadder: even a 3-step ladder from %.2f lot breaks the %.1f%% cap or the margin limit "
                  "(d=%.2f t=%.2f); balance needed about %.0f %s. No trade.",
                  l1,InpLossCapPct,p.d,p.t,needed,AccountInfoString(ACCOUNT_CURRENCY));
      return;
     }
   g_cycle.Start(side,p.d,p.t,p.s,lots);
  }

void Step()
  {
   bool open=(g_cycle.State()!=AL_FLAT && g_cycle.State()!=AL_COOLDOWN);
   g_cycle.OnTickManage(AL_WeekendForcesFlat(_Symbol,g_guard,TimeCurrent()));
   if(InpRestartNow && open && (g_cycle.State()==AL_FLAT || g_cycle.State()==AL_COOLDOWN))
      g_lastBar=0;   // the ladder just closed: do not wait for the next bar
   if(g_cycle.State()==AL_FLAT || g_cycle.State()==AL_COOLDOWN)
      TryStart();
  }

//+------------------------------------------------------------------+
//| Acceptance (spec section 9), scored after every tester run.       |
//| Gates: first-trade win rate above d/(d+t), worst ladder loss <= 6%|
//| of balance, equity drawdown <= 30%. The optimiser maximises net   |
//| profit among runs that pass; failing runs score below zero.       |
//+------------------------------------------------------------------+
double OnTester()
  {
   LadderStats st=g_cycle.stats;
   double profit =TesterStatistics(STAT_PROFIT);
   double dd     =TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double be     =InpStepAtr/(InpStepAtr+InpTargetAtr);   // approximate when InpProfitMax pulled the target in
   double winRate=(st.ladders>0 ? (double)st.firstStepWins/st.ladders : 0.0);
   bool   gWin   =winRate>be;
   bool   gLoss  =st.worstLossPct<=6.0;
   bool   gDd    =dd<=30.0;
   bool   gProfit=profit>0;
   string hist="";
   for(int i=1; i<10; i++)
      if(st.fillsHist[i]>0)
         hist+=StringFormat(" %s%d:%d",i==9 ? ">=" : "",i,st.fillsHist[i]);

   PrintFormat("AurumLadder summary: %d ladders, %d won (%d at trade 1), %d lost (%d at step cap); fills by step:%s",
               st.ladders,st.wins,st.firstStepWins,st.losses,st.stepCapLosses,hist);
   PrintFormat("  net profit %.2f %s  [%s]",profit,AccountInfoString(ACCOUNT_CURRENCY),gProfit?"PASS":"FAIL");
   PrintFormat("  first-trade win rate %.1f%% vs break-even %.1f%%  [%s]",100*winRate,100*be,gWin?"PASS":"FAIL");
   PrintFormat("  worst ladder loss %.2f%% of balance (limit 6%%)  [%s]",st.worstLossPct,gLoss?"PASS":"FAIL");
   PrintFormat("  max equity drawdown %.2f%% (limit 30%%)  [%s]",dd,gDd?"PASS":"FAIL");
   PrintFormat("  ACCEPTANCE: %s",(gProfit && gWin && gLoss && gDd) ? "PASS" : "FAIL");

   if(st.ladders<30)
      return(-1e6);                      // too few ladders to judge
   int misses=(gWin?0:1)+(gLoss?0:1)+(gDd?0:1);
   return(misses==0 ? profit : MathMin(profit,0.0)-1e5*misses);
  }

void OnTick()  { Step(); }
void OnTimer() { Step(); }
void OnTrade() { g_cycle.OnTradeEvent(); }
//+------------------------------------------------------------------+
#endif
