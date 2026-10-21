import pandas as pd, numpy as np, sys
sys.path.insert(0,'tools')
import holdout
def load(f):
    d=pd.read_csv(f); d['t']=pd.to_datetime(d.time,unit='s'); s=d.set_index('t').close
    return s.resample('D').last().dropna()
au=load('marketdata/histdata/XAUUSD_M1.csv.gz')
ag=load('marketdata/histdata/XAGUSD_M1.csv.gz')
df=pd.concat([au,ag],axis=1,keys=['au','ag']).dropna()
df=df[df.index.dayofweek<5]
df.index.name='day'
df=holdout.drop(df)
print(df.index.min(),df.index.max(),len(df))
lr=np.log(df.au/df.ag); ra=np.log(df.au).diff(); rg=np.log(df.ag).diff()
def run(L,ent,ex,cm=1.0):
    z=(lr-lr.rolling(L).mean())/lr.rolling(L).std()
    pos=pd.Series(0.0,index=df.index); p=0.0
    for d,v in z.shift(1).items():
        if np.isnan(v): pos[d]=0;continue
        if p==0:
            if v>ent:p=-1.0
            elif v<-ent:p=1.0
        elif (p<0 and v<ex) or (p>0 and v>-ex): p=0.0
        pos[d]=p
    gross=pos*0.5*(ra-rg)
    dp=pos.diff().abs().fillna(0)
    cost=dp*0.5*(2e-4+10e-4)*cm
    return (gross-cost).dropna()
sh=lambda x:x.mean()/x.std()*np.sqrt(252) if x.std()>0 else 0
rows=[]
for L in (20,60,120):
  for ent in (1.5,2.0,2.5):
    for ex in (0.0,0.5):
      r=run(L,ent,ex)
      rows.append((L,ent,ex,sh(r),sh(r[:'2017']),sh(r['2018':]),sh(run(L,ent,ex,1.5)['2018':])))
t=pd.DataFrame(rows,columns='L ent ex all h1 h2 h2_15x'.split());print(t.round(2).to_string())
print('trials',len(t))
b=t.sort_values('all').iloc[-1];print(b)
r=run(int(b.L),b.ent,b.ex);s=run(int(b.L),b.ent,b.ex,1.5)
r.rename('r').to_csv('marketdata/candidates/gsr_meanrev.csv',index_label='day')
s.rename('r').to_csv('marketdata/candidates/gsr_meanrev_stress.csv',index_label='day')
