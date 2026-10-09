//+------------------------------------------------------------------+
//| LadderTest.mq5 - tests for Ladder.mqh and Signal.mqh.            |
//| Run on any chart; results go to the Experts log.                 |
//| Same cases as tools/test_ladder_model.py.                        |
//+------------------------------------------------------------------+
#property script_show_inputs

#include <AurumLadder\Ladder.mqh>
#include <AurumLadder\Signal.mqh>

int g_pass=0,g_fail=0;

void Check(const bool cond,const string name)
  {
   if(cond)
      g_pass++;
   else
     {
      g_fail++;
      Print("FAIL: ",name);
     }
  }

double Uniform(const double lo,const double hi) { return(lo+(hi-lo)*MathRand()/32767.0); }

double Gauss(const double sd)
  {
   double u1=MathMax(MathRand(),1)/32768.0,u2=MathRand()/32768.0;
   return(sd*MathSqrt(-2.0*MathLog(u1))*MathCos(2.0*M_PI*u2));
  }

void Params(const double d,const double t,const double s,const double c,const double step,
            LadderParams &p)
  {
   p.d=d;
   p.t=t;
   p.s=s;
   p.c=c;
   p.step=step;
   p.vmin=step;
   p.vmax=500;
  }

void TestReferenceLadder()
  {
   double lots[];
   double want[]={0.01,0.03,0.06,0.12,0.24,0.48};
   LadderParams p;
   Params(1,1,0,0,0.01,p);
   bool ok=AL_LadderLots(0.01,6,p,lots);
   for(int i=0; i<6 && ok; i++)
      ok=MathAbs(lots[i]-want[i])<1e-9;
   Check(ok,"reference ladder 0.01 0.03 0.06 0.12 0.24 0.48");
  }

void TestTerminal14Numbers()
  {
   double lots[];
   LadderParams p;
   Params(11.55,11.55,0.4,0,0.01,p);
   AL_LadderLots(0.01,3,p,lots);
   Check(MathAbs(lots[1]-0.04)<1e-9 && MathAbs(lots[2]-0.09)<1e-9,"terminal 14 lots 0.01 0.04 0.09");
   Check(MathAbs(100*AL_FailedLoss(lots,p)-189)<1,"terminal 14 failed loss 189 USC");
   double none[];
   Check(!AL_FirstLot(677.31*0.05,6,p,100,0,1e18,none),"677 USC balance cannot fit the 5% cap");
   double three[];
   Check(AL_FirstLot(3800*0.05,6,p,100,0,1e18,three) && ArraySize(three)==3,"3800 USC fits N=3");
  }

void TestRandomProperties()
  {
   MathSrand(7);
   double steps[]={0.01,0.1,1.0};
   int    feasible=0;
   for(int it=0; it<2000; it++)
     {
      double d=Uniform(0.5,20),t=Uniform(0.5,20),s=Uniform(0,0.5),c=Uniform(0,0.1)*t;
      double step=steps[MathRand()%3],v=(MathRand()%2==0 ? 1 : 100);
      double balance=Uniform(1e3,1e7);
      LadderParams p;
      Params(d,t,s,c,step,p);
      double lots[];
      if(!AL_FirstLot(balance*0.05,3+MathRand()%6,p,v,0,1e18,lots))
         continue;
      feasible++;
      int    n=ArraySize(lots);
      double pi=lots[0]*(t-c);
      for(int k=1; k<=n; k++)
         if(AL_BasketProfit(lots,k,p)<pi-1e-9)
           {
            Check(false,StringFormat("step %d of %d below target profit (d=%.2f t=%.2f)",k,n,d,t));
            return;
           }
      if(v*AL_FailedLoss(lots,p)>balance*0.05+1e-6)
        {
         Check(false,"failed loss above cap");
         return;
        }
     }
   Check(feasible>1500,"random cases mostly feasible ("+IntegerToString(feasible)+")");
  }

void TestSignal()
  {
   double up[64],down[64],flat[64];
   MathSrand(1);
   for(int i=0; i<64; i++)
     {
      up[i]  =100*MathExp(0.001*i);
      down[i]=100-0.05*i+Gauss(0.05);
      flat[i]=100+Gauss(0.2);
     }
   Check(AL_Direction(up,64,3.0,0.25)==1,"pure uptrend buys");
   Check(AL_Direction(down,64,3.0,0.25)==-1,"noisy downtrend sells");
   Check(AL_Direction(flat,64,3.0,0.25)==0,"flat noise stays out");

   double hand[4];
   double y[]={0,1,1,2};
   for(int i=0; i<4; i++)
      hand[i]=MathExp(y[i]*0.01);
   Check(MathAbs(AL_RegressionTStat(hand,4)-0.006/MathSqrt(1e-5/5))<1e-6,"hand-computed t-statistic");
   double er[]={1,2,1,3};
   Check(MathAbs(AL_EfficiencyRatio(er,4)-0.5)<1e-12,"hand-computed efficiency ratio");
  }

void OnStart()
  {
   TestReferenceLadder();
   TestTerminal14Numbers();
   TestRandomProperties();
   TestSignal();
   PrintFormat("LadderTest: %d passed, %d failed",g_pass,g_fail);
  }
//+------------------------------------------------------------------+
