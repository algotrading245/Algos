//+------------------------------------------------------------------+
//| Signal.mqh - direction signal (spec section 1).                   |
//| closes[] is oldest first. Mirrors tools/ladder_model.py.          |
//+------------------------------------------------------------------+
#ifndef AURUMLADDER_SIGNAL_MQH
#define AURUMLADDER_SIGNAL_MQH

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

#endif
//+------------------------------------------------------------------+
