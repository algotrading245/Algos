//+------------------------------------------------------------------+
//| Ladder.mqh - pure ladder maths (spec section 4). No trading calls.|
//| Mirrors tools/ladder_model.py; keep the two in step.              |
//| Distances are price units; trade numbers n are 1-based.           |
//+------------------------------------------------------------------+
#ifndef AURUMLADDER_LADDER_MQH
#define AURUMLADDER_LADDER_MQH

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

#endif
//+------------------------------------------------------------------+
