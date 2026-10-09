//+------------------------------------------------------------------+
//| Cycle.mqh - ladder state machine, orders, basket close and       |
//| restart recovery (spec sections 3 and 5).                        |
//|                                                                  |
//| State lives in terminal global variables under "AL_<magic>_" so  |
//| a restarted EA resumes the same ladder.                          |
//+------------------------------------------------------------------+
#ifndef AURUMLADDER_CYCLE_MQH
#define AURUMLADDER_CYCLE_MQH

#include <Trade\Trade.mqh>
#include "Broker.mqh"
#include "Ladder.mqh"
#include "RiskGuard.mqh"

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
   void              Log(const string msg) const { PrintFormat("AurumLadder[%I64d] %s",m_magic,msg); }

public:
                     CLadderCycle() : m_state(AL_FLAT), m_exitSeen(false) {}
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
   if((long)GetGV("failday",-1)==AL_ServerDay(now) && (int)GetGV("fails",0)>=m_maxFailsPerDay)
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

#endif
//+------------------------------------------------------------------+
