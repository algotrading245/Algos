"""Frazzini-Pedersen BAB, equity-index version on SPX, NSX, GRX, JPX. Pre-registered: beta = 1y rolling daily
slope vs equal-weight proxy (sum of lags 0..5 slopes approximated by 5-day-return slope), shrunk 0.5*b+0.5; monthly
rebalance at last trading day close (17:00 NY); A = long lowest-beta/short highest-beta, each scaled to beta 1
(leverage 1/beta); B = paper rank weights over all 4. Earn the next month. Cost 3bp per side on traded notional
(1x; assumed index CFD spread), 1.5x, 2x. Financing/swap not modelled. Holdout dropped."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout


def daily(sym):
    m = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(m['time'] + 60 - 7 * 3600, unit='s').dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT')
    ok = t.notna().to_numpy()
    s = pd.Series(m['close'].to_numpy()[ok], index=pd.DatetimeIndex(t[ok]))
    s = s.groupby(level=0).last()
    s.index = s.index.tz_localize(None) + pd.Timedelta(hours=7)
    d = s.groupby(s.index.normalize()).last()
    return d[d.index.dayofweek < 5]


syms = ['SPXUSD', 'NSXUSD', 'GRXEUR', 'JPXJPY']
px = pd.concat([daily(s) for s in syms], axis=1, keys=syms).dropna()
ret = px.pct_change().dropna()
ret = ret[ret.abs().max(axis=1) < 0.25]
print('days', len(ret), ret.index[0].date(), ret.index[-1].date())
mkt = ret.mean(axis=1)
# 5-day (weekly) overlapping returns slope as Dimson-style proxy for lags 0..5
r5 = ret.rolling(5).sum()
m5 = mkt.rolling(5).sum()
beta = pd.DataFrame({c: r5[c].rolling(252).cov(m5) / m5.rolling(252).var() for c in syms})
beta = 0.5 * beta + 0.5
me = ret.index.to_series().groupby([ret.index.year, ret.index.month]).last().values
me = pd.DatetimeIndex(me)


def run(variant, mult):
    out = pd.Series(0.0, index=ret.index)
    prev = pd.Series(0.0, index=syms)
    for k in range(len(me) - 1):
        d0, d1 = me[k], me[k + 1]
        b = beta.loc[d0]
        if b.isna().any() or (b <= 0.1).any():
            continue
        if variant == 'A':
            lo, hi = b.idxmin(), b.idxmax()
            w = pd.Series(0.0, index=syms)
            w[lo] = 1 / b[lo]
            w[hi] = -1 / b[hi]
            w *= 0.5  # gross scaling to ~1x per leg-pair
        else:
            rk = b.rank()
            z = rk - rk.mean()
            wl = z.clip(lower=0)
            wh = -z.clip(upper=0)
            wl /= wl.sum()
            wh /= wh.sum()
            bl, bh = (wl * b).sum(), (wh * b).sum()
            w = 0.5 * (wl / bl - wh / bh)
        seg = ret.loc[(ret.index > d0) & (ret.index <= d1)]
        pnl = (seg * w).sum(axis=1)
        cst = (w - prev).abs().sum() * 3e-4 * mult
        # holding cost: reweight drift ignored
        pnl.iloc[0] -= cst
        pnl.iloc[-1] -= w.abs().sum() * 0  # exit cost is charged by next entry diff
        out.loc[pnl.index] = pnl
        prev = w
    return out[out.index >= me[0]]


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 30 and x.std() > 0 else float('nan')


for v in ('A', 'B'):
    for mult in (1, 1.5, 2):
        r = holdout.drop(run(v, mult))
        print(f'{v} x{mult}: all {sh(r):5.2f} to2017 {sh(r[:"2017"]):5.2f} 2018+ {sh(r["2018":]):5.2f} ann vol {r.std()*np.sqrt(252):.3f}')
r = run('A', 1)
s = run('A', 1.5)
holdout.drop(r).rename('r').to_csv('marketdata/candidates/paper_bab_index_beta_neutral.csv', index_label='day')
holdout.drop(s).rename('r').to_csv('marketdata/candidates/paper_bab_index_beta_neutral_stress.csv', index_label='day')
print('trials: 2 variants x 3 costs; candidate = A')
