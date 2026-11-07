"""Keloharju-Linnainmaa-Nyberg same-calendar-month commodity long-short. Pre-registered: top3/bottom3 of 15 (OJ dropped),
rank = mean return of the same calendar month over ALL prior years (>=5), inverse 60d vol weights per side, hold calendar
month, month-end rebalance. Placebo: rank by mean of the other 11 months. Costs per side-turnover 8bp at 1x
(FTMO commodity CFD spread+slippage) + financing 4%/yr on gross at 1x (swap both legs). 1.5x/2x scale both."""
import sys
sys.path.insert(0, 'tools')
import pandas as pd, numpy as np
import holdout

SYMS = ['CL', 'BZ', 'NG', 'HG', 'GC', 'SI', 'PL', 'PA', 'ZC', 'ZS', 'ZW', 'CT', 'CC', 'KC', 'SB']
px = {}
for s in SYMS:
    d = pd.read_csv(f'marketdata/commod/{s}.csv', parse_dates=['date']).set_index('date')
    px[s] = d.close
px = holdout.drop(pd.DataFrame(px)).sort_index()
ret = px.pct_change(fill_method=None).clip(-0.12, 0.12)
mret = (1 + ret.fillna(0)).groupby([ret.index.year, ret.index.month]).prod() - 1   # year, month x sym
mret.index.names = ['y', 'm']
vol = ret.rolling(60, min_periods=40).std()


def run(placebo, K=3):
    months = [(y, m) for (y, m) in mret.index]
    W = {}
    for (y, m) in months:
        if y < 2010:
            continue
        # signal built from prior years only
        hist = mret[mret.index.get_level_values('y') < y]
        same = hist[hist.index.get_level_values('m') == m]
        other = hist[hist.index.get_level_values('m') != m]
        sig = other.groupby(level='m').mean().mean() if placebo else same.mean()
        n = same.count()
        ok = n[n >= 5].index
        sig = sig[ok].dropna()
        if len(sig) < 2 * K + 2:
            continue
        # vol at the prior month end
        first = ret.index[(ret.index.year == y) & (ret.index.month == m)]
        if len(first) == 0:
            continue
        v = vol.loc[:first[0]].iloc[-2] if len(vol.loc[:first[0]]) > 1 else None
        if v is None:
            continue
        rk = sig.sort_values()
        lo, hi = list(rk.index[:K]), list(rk.index[-K:])
        w = pd.Series(0.0, index=px.columns)
        for names, sgn in [(hi, 1), (lo, -1)]:
            iv = 1 / v[names]
            w[names] = sgn * iv / iv.sum()
        W[(y, m)] = w * 0.5   # gross 1 in total
    return pd.DataFrame(W).T


def daily(Wm, mult):
    rows = []
    prev = pd.Series(0.0, index=px.columns)
    out = {}
    for (y, m), w in Wm.iterrows():
        idx = ret.index[(ret.index.year == y) & (ret.index.month == m)]
        turn = (w - prev).abs().sum()
        for i, dte in enumerate(idx):
            r = (w * ret.loc[dte].fillna(0)).sum()
            r -= w.abs().sum() * 0.04 / 365 * mult * (ret.index[ret.index.get_loc(dte)] - (idx[i - 1] if i else dte)).days if i else 0
            if i == 0:
                r -= turn * 8e-4 * mult
            out[dte] = r
        prev = w
    return pd.Series(out)


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0


def rep(name, r):
    print(name, 'SR', round(sharpe(r), 2), 'h<2018', round(sharpe(r[r.index < '2018-01-01']), 2),
          'h>=2018', round(sharpe(r[r.index >= '2018-01-01']), 2), 'ann%', round(r.mean() * 252 * 100, 2),
          'n', len(r))


Wr = run(False)
Wp = run(True)
res = {m: daily(Wr, m) for m in (0, 1, 1.5, 2)}
gross = res[0]
for k, v in res.items():
    rep(f'real {k}x', v)
rep('placebo 1x', daily(Wp, 1))
rep('placebo gross', daily(Wp, 0))
# gross diff (real - placebo)
d = (gross - daily(Wp, 0)).dropna()
rep('real-minus-placebo gross', d)
# per-year real 1x
r1 = res[1]
print((r1.groupby(r1.index.year).sum() * 100).round(1).to_dict())
# leave-one-out by long/short: which symbols selected most
cnt = (Wr > 0).sum().sort_values(ascending=False).to_dict()
print('long counts', cnt)

for nm, key in [('commod_same_month', 1), ('commod_same_month_stress', 1.5)]:
    r = res[key].rename('r')
    r.index.name = 'day'
    r = r.reset_index()
    r['day'] = r['day'].dt.strftime('%Y-%m-%d')
    r.to_csv(f'marketdata/candidates/{nm}.csv', index=False)
