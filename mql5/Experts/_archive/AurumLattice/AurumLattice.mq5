//+------------------------------------------------------------------+
//| AurumLattice.mq5 - a reverse grid around the price of gold at    |
//| the start of the session. At the start time the bid is taken as  |
//| the anchor A and the step is g = InpStep times the average       |
//| high-low range of the same hours over the previous InpDays days. |
//| The position is always q units, q being the number of whole      |
//| steps the price has gone away from A: one unit is bought at each |
//| level reached above A and sold again when the price comes one    |
//| step back, and the mirror below A. A day that runs n steps one   |
//| way earns g*n*(n-1)/2 per unit, every swing of one step and back |
//| loses g. When the day has lost InpCapSteps steps everything is   |
//| closed and the day is over; at the end time everything is closed.|
//| The unit is sized so that InpCapSteps steps are InpRiskPct of    |
//| the balance. Nothing is held overnight.                          |
//| Most days lose a little and a few days win a lot: about one day  |
//| in three ends in profit.                                         |
//| Backtest: tools/backtest_lattice.py                              |
//+------------------------------------------------------------------+
#property copyright "algotrading245"
#property version   "1.00"

#include <Trade\Trade.mqh>

input group "Grid"
input int    InpStartHour      = 15;     // Anchor time, hour (server time)
input int    InpStartMinute    = 0;      // Anchor time, minute (multiple of 5)
input int    InpEndHour        = 23;     // Everything is closed at, hour
input int    InpEndMinute      = 0;      // Everything is closed at, minute (multiple of 5)
input double InpStep           = 0.40;   // Step, average ranges of the session
input int    InpDays           = 60;     // Days in the average range
input int    InpLevels         = 6;      // Levels on each side of the anchor
input int    InpSide           = 0;      // 1 = only above the anchor (long), -1 = only below, 0 = both

input group "Size and risk guard"
input double InpRiskPct        = 1.0;    // Loss that ends the day, % of balance
input double InpCapSteps       = 6.0;    // The same loss in steps of one unit
input double InpMaxSpread      = 0.30;   // No new unit while spread is above this, price units
input int    InpEntrySec       = 60;     // No start later than this after the anchor time, seconds

input group "Execution"
input long   InpMagic          = 245009; // Magic number
input int    InpDeviation      = 30;     // Max slippage, points

#define WAITING 0
#define RUNNING 1
#define DONE    2

CTrade   g_trade;
datetime g_day=0;          // day the state below belongs to
int      g_state=WAITING;
double   g_anchor=0.0;
double   g_step=0.0;       // grid step, price units
double   g_unit=0.0;       // lots per level
double   g_risk=0.0;       // loss that ends the day, account currency
double   g_realised=0.0;   // result of the units closed today, account currency

string Key(string name)
  {
   return("AurumLattice."+(string)InpMagic+"."+_Symbol+"."+name);
  }

void Save()
  {
   GlobalVariableSet(Key("day"),(double)g_day);
   GlobalVariableSet(Key("state"),g_state);
   GlobalVariableSet(Key("anchor"),g_anchor);
   GlobalVariableSet(Key("step"),g_step);
   GlobalVariableSet(Key("unit"),g_unit);
   GlobalVariableSet(Key("risk"),g_risk);
  }

// Units held under the magic number, positive when long; 'last' receives the ticket opened last, 'floating' their result.
int Units(ulong &last,double &floating)
  {
   int q=0;
   long newest=-1;
   last=0;
   floating=0.0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      q+=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1);
      floating+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      if(PositionGetInteger(POSITION_TIME_MSC)>newest)
        {
         newest=PositionGetInteger(POSITION_TIME_MSC);
         last=t;
        }
     }
   return(q);
  }

// Result of all deals of this EA since 'from' with commission and swap, account currency.
double Realised(datetime from)
  {
   double sum=0.0;
   if(!HistorySelect(from,TimeCurrent()+60))
      return(0.0);
   for(int i=HistoryDealsTotal()-1; i>=0; i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d!=0 && HistoryDealGetString(d,DEAL_SYMBOL)==_Symbol && HistoryDealGetInteger(d,DEAL_MAGIC)==InpMagic)
         sum+=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_COMMISSION)+
              HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_FEE);
     }
   return(sum);
  }

// Closes every unit; true when none is left.
bool CloseAll()
  {
   bool clean=true;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong t=PositionGetTicket(i);
      if(t==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic)
         continue;
      if(!g_trade.PositionClose(t,InpDeviation))
        {
         PrintFormat("AurumLattice: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
         clean=false;
        }
     }
   return(clean);
  }

// Average high-low range between the start and end time over the InpDays trading days before 'today'; 0 while history is short.
double AverageRange(datetime today)
  {
   int from=InpStartHour*3600+InpStartMinute*60,to=InpEndHour*3600+InpEndMinute*60;
   int need=(to-from)/300/2;
   double sum=0.0,hi[],lo[];
   int n=0;
   for(int i=1; i<=2*InpDays+20 && n<InpDays; i++)
     {
      datetime day=today-i*86400;
      int h=CopyHigh(_Symbol,PERIOD_M5,day+from,day+to-1,hi);
      int l=CopyLow(_Symbol,PERIOD_M5,day+from,day+to-1,lo);
      if(h<need || l!=h)
         continue;
      sum+=hi[ArrayMaximum(hi)]-lo[ArrayMinimum(lo)];
      n++;
     }
   return(n>=InpDays/2 ? sum/n : 0.0);
  }

// Lots per level such that InpCapSteps steps lose InpRiskPct of the balance; 0 when below the minimum lot.
double UnitLots(double price)
  {
   double loss,margin;
   if(!OrderCalcProfit(ORDER_TYPE_BUY,_Symbol,1.0,price,price-g_step,loss) || loss>=0)
      return(0.0);
   double lots=g_risk/(InpCapSteps*(-loss));
   if(OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,1.0,price,margin) && margin>0)
      lots=MathMin(lots,0.5*AccountInfoDouble(ACCOUNT_MARGIN_FREE)/(margin*InpLevels));
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   lots=MathMin(MathFloor(lots/step+1e-9)*step,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   return(lots<SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN) ? 0.0 : NormalizeDouble(lots,2));
  }

void Finish(string why)
  {
   g_state=DONE;
   Save();
   PrintFormat("AurumLattice: %s, result of the day %+.2f",why,Realised(g_day+InpStartHour*3600+InpStartMinute*60));
  }

// Takes the anchor, the step and the unit for the day.
void Start(datetime today,double bid)
  {
   double avg=AverageRange(today);
   if(avg<=0)
     {
      PrintFormat("AurumLattice: fewer than %d days of M5 history, no grid today",InpDays/2);
      g_state=DONE;
      Save();
      return;
     }
   g_anchor=bid;
   g_step=InpStep*avg;
   g_risk=AccountInfoDouble(ACCOUNT_BALANCE)*InpRiskPct/100.0;
   g_unit=UnitLots(bid);
   g_realised=0.0;
   if(g_unit<=0)
     {
      PrintFormat("AurumLattice: balance too small for the minimum lot at a step of %.2f, no grid today",g_step);
      g_state=DONE;
      Save();
      return;
     }
   g_state=RUNNING;
   Save();
   PrintFormat("AurumLattice: anchor %.2f, step %.2f (average range %.2f), %.2f lots per level, the day ends at a loss of %.2f",
               g_anchor,g_step,avg,g_unit,g_risk);
  }

// Brings the number of units to the number of whole steps the price is away from the anchor.
void Walk(int q,ulong last,double bid,double ask)
  {
   double x=(bid-g_anchor)/g_step;
   int tgt=(x>q ? MathMax(q,(int)MathFloor(x+1e-9)) : MathMin(q,(int)MathCeil(x-1e-9)));
   tgt=MathMax(InpSide<=0 ? -InpLevels : 0,MathMin(InpSide>=0 ? InpLevels : 0,tgt));
   double floating;
   while(q!=tgt)
     {
      int dir=(tgt>q ? 1 : -1);
      if(dir*q>=0)             // one more unit with the move
        {
         if(ask-bid>InpMaxSpread)
            return;
         bool ok=(dir>0 ? g_trade.Buy(g_unit,_Symbol,0.0,0.0,0.0,"AurumLattice") : g_trade.Sell(g_unit,_Symbol,0.0,0.0,0.0,"AurumLattice"));
         if(!ok || g_trade.ResultDeal()==0)
           {
            PrintFormat("AurumLattice: order failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
            return;
           }
        }
      else                     // the price came a step back: the unit opened last is given up
        {
         if(!g_trade.PositionClose(last,InpDeviation))
           {
            PrintFormat("AurumLattice: close failed, retcode %d (%s)",g_trade.ResultRetcode(),g_trade.ResultRetcodeDescription());
            return;
           }
         g_realised=Realised(g_day+InpStartHour*3600+InpStartMinute*60);
        }
      int now=Units(last,floating);
      if(now==q)
         return;               // the terminal has not booked the deal yet, the next tick goes on
      q=now;
     }
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   int from=InpStartHour*60+InpStartMinute,to=InpEndHour*60+InpEndMinute;
   if(InpStartHour<0 || InpStartHour>23 || InpEndHour<0 || InpEndHour>23 || InpStartMinute<0 || InpStartMinute>55 ||
      InpStartMinute%5!=0 || InpEndMinute<0 || InpEndMinute>55 || InpEndMinute%5!=0 || to-from<30 || InpStep<=0 ||
      InpDays<2 || InpLevels<1 || InpSide<-1 || InpSide>1 || InpRiskPct<=0 || InpCapSteps<=0 || InpEntrySec<1)
      return(INIT_PARAMETERS_INCORRECT);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpDeviation);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   iBars(_Symbol,PERIOD_M5);   // starts loading the bars the average range is built from
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick) || tick.bid<=0 || tick.ask<=0)
      return;
   datetime now=TimeCurrent();
   datetime today=now-now%86400;
   datetime start=today+InpStartHour*3600+InpStartMinute*60;
   datetime end=today+InpEndHour*3600+InpEndMinute*60;
   ulong last;
   double floating;
   int q=Units(last,floating);
   if(g_day!=today)
     {
      g_day=today;
      g_state=WAITING;
      if(GlobalVariableCheck(Key("day")) && (datetime)GlobalVariableGet(Key("day"))==today)
        {
         // the EA was restarted during the day: go on with the same grid
         g_state=(int)GlobalVariableGet(Key("state"));
         g_anchor=GlobalVariableGet(Key("anchor"));
         g_step=GlobalVariableGet(Key("step"));
         g_unit=GlobalVariableGet(Key("unit"));
         g_risk=GlobalVariableGet(Key("risk"));
         g_realised=Realised(start);
        }
     }
   if(g_state!=RUNNING)
     {
      if(q!=0)
         CloseAll();           // units without a grid: left from a day the EA did not see the end of
      if(g_state==DONE || now<start)
         return;
      if(now>=end || now-start>=InpEntrySec || q!=0)
        {
         g_state=DONE;
         Save();
         return;
        }
      Start(today,tick.bid);
      if(g_state!=RUNNING)
         return;
     }
   if(now>=end)
     {
      if(CloseAll())
         Finish("end of the session");
      return;
     }
   if(g_realised+floating<=-g_risk)
     {
      if(CloseAll())
         Finish("loss limit of the day reached");
      return;
     }
   Walk(q,last,tick.bid,tick.ask);
  }
//+------------------------------------------------------------------+
