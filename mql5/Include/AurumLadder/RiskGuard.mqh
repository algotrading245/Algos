//+------------------------------------------------------------------+
//| RiskGuard.mqh - spread, weekend, daily stop (spec section 6).    |
//| Cooldown and the failure count are persisted by Cycle.mqh.       |
//+------------------------------------------------------------------+
#ifndef AURUMLADDER_RISKGUARD_MQH
#define AURUMLADDER_RISKGUARD_MQH

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

#endif
//+------------------------------------------------------------------+
