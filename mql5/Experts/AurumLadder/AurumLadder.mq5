//+------------------------------------------------------------------+
//| AurumLadder.mq5 - gold zone-recovery ladder.                     |
//| Design: docs/superpowers/specs/2026-10-09-aurumladder-design.md  |
//| Inputs and event wiring only; logic lives in Include/AurumLadder.|
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <AurumLadder\Broker.mqh>
#include <AurumLadder\Signal.mqh>
#include <AurumLadder\Ladder.mqh>
#include <AurumLadder\RiskGuard.mqh>
#include <AurumLadder\Cycle.mqh>

input group "Signal (M15)"
input int    InpLookback       = 64;    // Regression lookback, bars
input double InpTStatMin       = 3.0;   // Minimum |slope t-statistic|
input double InpEffMin         = 0.25;  // Minimum efficiency ratio

input group "Zone"
input int    InpAtrPeriod      = 14;    // ATR period
input double InpStepAtr        = 1.5;   // Zone width d, x ATR
input double InpTargetAtr      = 1.5;   // Target t, x ATR
input double InpTargetSpreads  = 5.0;   // Target must be at least this many x spread allowance

input group "Ladder"
input int    InpMaxSteps       = 6;     // Step cap N (tune 4-8)
input double InpLossCapPct     = 5.0;   // Failed-ladder loss cap, % of balance
input double InpMarginPct      = 50.0;  // Ladder margin cap, % of free margin
input double InpCommissionLot  = 0.0;   // Round-trip commission per lot, account currency

input group "Risk guard"
input double InpMaxSpread      = 0.40;  // Spread filter and sizing allowance s, price units
input int    InpCooldownHours  = 4;     // Pause after a failed ladder
input int    InpMaxFailsPerDay = 2;     // Failed ladders before stopping for the day
input int    InpNoNewMinutes   = 180;   // No new ladder within this of Friday close
input int    InpFlattenMinutes = 15;    // Close open ladder this long before Friday close
input int    InpFridayCloseMin = 1435;  // Fallback Friday close, minutes after midnight (server)

input group "Execution"
input long   InpMagic          = 245001; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

BrokerSpec   g_broker;
GuardParams  g_guard;
CLadderCycle g_cycle;
int          g_atr=INVALID_HANDLE;
datetime     g_lastBar=0;

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
   if(InpMaxSteps<3 || InpLookback<8 || InpLossCapPct<=0)
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
//| Once per closed M15 bar while flat: guards, signal, sizing, start.|
//+------------------------------------------------------------------+
void TryStart()
  {
   datetime bar=iTime(_Symbol,PERIOD_M15,0);
   if(bar==0 || bar==g_lastBar)
      return;
   g_lastBar=bar;

   datetime now=TimeCurrent();
   if(!g_cycle.CanStart(now) || !AL_SpreadOk(_Symbol,g_guard.maxSpread)
      || AL_WeekendBlocksNew(_Symbol,g_guard,now))
      return;

   double closes[];
   if(CopyClose(_Symbol,PERIOD_M15,1,InpLookback,closes)!=InpLookback)
      return;
   int side=AL_Direction(closes,InpLookback,InpTStatMin,InpEffMin);
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

   // Floors: the target must dwarf the spread, and every stop order and SL/TP
   // must clear the broker's minimum distance even at the widest allowed spread.
   double minDist=g_broker.stopsDist+p.s;
   if(p.t<InpTargetSpreads*p.s || p.d<=minDist || p.t<=minDist || p.t<=p.c)
     {
      PrintFormat("AurumLadder: zone too small (d=%.2f t=%.2f, need > %.2f and t >= %.2f); skipping",
                  p.d,p.t,minDist,InpTargetSpreads*p.s);
      return;
     }

   double mpl=AL_MarginPerLot(g_broker);
   if(mpl<0)
      return;
   double cap=AccountInfoDouble(ACCOUNT_BALANCE)*InpLossCapPct/100.0;
   double marginLimit=AccountInfoDouble(ACCOUNT_MARGIN_FREE)*InpMarginPct/100.0;
   double lots[];
   if(!AL_FirstLot(cap,InpMaxSteps,p,g_broker.v,mpl,marginLimit,lots))
     {
      double minLots[];
      double needed=0.0;
      if(AL_LadderLots(g_broker.vmin,3,p,minLots))
         needed=g_broker.v*AL_FailedLoss(minLots,p)*100.0/InpLossCapPct;
      PrintFormat("AurumLadder: even a 3-step ladder at %.2f lot breaks the %.1f%% cap "
                  "(d=t~%.2f); balance needed about %.0f %s. No trade.",
                  g_broker.vmin,InpLossCapPct,p.d,needed,AccountInfoString(ACCOUNT_CURRENCY));
      return;
     }
   g_cycle.Start(side,p.d,p.t,p.s,lots);
  }

void Step()
  {
   g_cycle.OnTickManage(AL_WeekendForcesFlat(_Symbol,g_guard,TimeCurrent()));
   if(g_cycle.State()==AL_FLAT || g_cycle.State()==AL_COOLDOWN)
      TryStart();
  }

void OnTick()  { Step(); }
void OnTimer() { Step(); }
void OnTrade() { g_cycle.OnTradeEvent(); }
//+------------------------------------------------------------------+
