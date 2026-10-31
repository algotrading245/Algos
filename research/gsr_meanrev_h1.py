import pandas as pd, numpy as np, sys
sys.path.insert(0,'tools')
import holdout
# H1 gold-silver log-ratio z-score mean reversion. Cost: 4bp silver + 2bp gold-ish round trip assumed as in D1 run
# (gold 2bp, silver 10bp per full turn of its leg, half-notional each leg) - silver spread data request still open.
def load(f):
    d=pd.read_csv(f); d['t']=pd.to_datetime(d.time,unit='s'); s=d.set_index('t').close
    return s.resample('h').last().dropna()
au=load('marketdata/histdata/XAUUSD_M1.csv.gz')
ag=load('marketdata/histdata/XAGUSD_M1.csv.gz')
df=pd.concat([au,ag],axis=1,keys=['au','ag']).dropna()
df=df[df.index.dayofweek<5]
df=df[~df.index.hour.isin([22,23,0])]  # keep rollover out
df.index.name='day'
df=holdout.drop(df)
print(df.index.min(),df.index.max(),len(df))
lr=np.log(df.au/df.ag); ra=np.log(df.au).diff(); rg=np.log(df.ag).diff()
def run(L,ent,ex,cm=1.0):
    z=((lr-lr.rolling(L).mean())/lr.rolling(L).std()).shift(1).values
    pos=np.zeros(len(df)); p=0.0
    for i,v in enumerate(z):
        if np.isnan(v): pos[i]=0;continue
        if p==0:
            if v>ent:p=-1.0
            elif v<-ent:p=1.0
        elif (p<0 and v<ex) or (p>0 and v>-ex): p=0.0
        pos[i]=p
    pos=pd.Series(pos,index=df.index)
    gross=pos*0.5*(ra-rg)
    cost=pos.diff().abs().fillna(0)*0.5*(2e-4+10e-4)*cm
    r=(gross-cost).dropna()
    return r.groupby(r.index.normalize()).sum()
sh=lambda x:x.mean()/x.std()*np.sqrt(252) if x.std()>0 else 0
rows=[]
for L in (120,480,1200):
  for ent in (2.0,2.5,3.0):
    for ex in (0.0,0.5):
      r=run(L,ent,ex)
      rows.append((L,ent,ex,sh(r),sh(r[:'2017']),sh(r['2018':]),sh(run(L,ent,ex,1.5)['2018':])))
t=pd.DataFrame(rows,columns='L ent ex all h1 h2 h2_15x'.split());print(t.round(2).to_string())
print('trials',len(t))
b=t.sort_values('all').iloc[-1];print(b)
r=run(int(b.L),b.ent,b.ex);s=run(int(b.L),b.ent,b.ex,1.5)
r.rename('r').to_csv('marketdata/candidates/gsr_meanrev_h1.csv',index_label='day')
s.rename('r').to_csv('marketdata/candidates/gsr_meanrev_h1_stress.csv',index_label='day')
