"""prebuilt_gold_bond_regime: long XAUUSD when trailing 12m gold return >0 and 12m 10y Treasury total return >0.
Month-end signal, hold next month. Bond TR proxy = -7.5*dy + y/12 per month (FRED DGS10). No parameter sweep.
Costs: spread 0.44 USD/oz per switch (half each way counted as full spread on round trip = per switch 0.44 total
across open+close, charged 0.22 on each change), swap -0.5955 USD/oz per calendar night long. Cost scale via argv."""
import sys
sys.path.insert(0, 'tools')
import pandas as pd, numpy as np
import holdout

g = pd.read_csv('marketdata/histdata/XAUUSD_D1.csv.gz')
g['day'] = pd.to_datetime(g.time, unit='s').dt.normalize()
g = holdout.drop(g.set_index('day'))
px = g.close
f = pd.read_csv('marketdata/fred/DGS10.csv', parse_dates=['observation_date']).set_index('observation_date')
y = pd.to_numeric(f.DGS10, errors='coerce').ffill()
y = holdout.drop(y)

# month-end series
gm = px.resample('ME').last()
ym = y.resample('ME').last() / 100
btr = -7.5 * ym.diff() + ym / 12          # monthly bond total return proxy
b12 = (1 + btr).rolling(12).apply(np.prod, raw=True) - 1
g12 = gm.pct_change(12)
sig = ((g12 > 0) & (b12 > 0)).astype(float)
sig[g12.isna() | b12.isna()] = np.nan
# the signal at month-end m applies to days after that month-end (past only)
sd = sig.reindex(px.index, method=None)
daily_sig = pd.Series(np.nan, index=px.index)
for dt, v in sig.dropna().items():
    pass
dsig = sig.shift(0).dropna()
pos = pd.Series(index=px.index, dtype=float)
# position on day d = signal of last month-end strictly before d
ends = dsig.index
idx = np.searchsorted(ends.values, px.index.values, side='left') - 1
pos = pd.Series([dsig.iloc[i] if i >= 0 else np.nan for i in idx], index=px.index).dropna()

ret = px.pct_change().reindex(pos.index)
# signal known at close of previous day (month-end); hold from next day's return
def run(scale):
    p = pos
    spread = 0.44 * scale
    chg = p.diff().abs().fillna(p.abs())
    cal = pd.Series(px.index, index=px.index).diff().dt.days.reindex(p.index).fillna(1)
    cost = chg * (spread / 2) / px.reindex(p.index) + p * cal * 0.5955 * scale / px.reindex(p.index)
    return p * ret - cost
r1, r15, r2 = run(1), run(1.5), run(2)

def sh(x): return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan
for nm, r in [('1x', r1), ('1.5x', r15), ('2x', r2)]:
    a, b = r[r.index < '2018-01-01'], r[r.index >= '2018-01-01']
    print(nm, 'all %.2f  to2017 %.2f  2018+ %.2f' % (sh(r), sh(a), sh(b)), 'ann %.3f' % (r.mean() * 252))
print('days long share', pos.mean(), 'switches', int((pos.diff().abs() > 0).sum()), 'start', pos.index[0])
hold = ret.copy()
print('buy&hold sharpe', sh(hold), ' halves', sh(hold[hold.index < '2018']), sh(hold[hold.index >= '2018']))
print('corr to hold', np.corrcoef(r1.fillna(0), hold.fillna(0))[0, 1])
for nm, r in [('', r1), ('_stress', r15)]:
    o = r.rename('r').reset_index()
    o.columns = ['day', 'r']
    o.to_csv('marketdata/candidates/gold_bond_regime%s.csv' % nm, index=False)
