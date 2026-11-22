"""BSIC VIX/VIX3M spike long (bsic.it/volatility-linked-strategy-new-approach). Rule as published, no sweep:
ratio = VIX/VIX3M; z = (ratio - mean20)/std20; long when z > 1.5, flat otherwise. Signal at close t; to stay past-only
(VIX closes after the cash close) the position earns the return of t+1 -> t+2 (one extra day of lag).
Vol-scaled to 10% a year (trailing 60d, cap 3x) as in vrp_gap. Markets: US500 (SPX_D1), US100 (NSXUSD M1), GRXEUR (M1).
Costs: half spread per exposure change + long financing (DFF+1.5% - 1.8% dividend). Stress 1.5x.
Output: marketdata/candidates/vix_vxv_spike{,_stress,_markets}.csv"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
Z, N = 1.5, 20


def m1_daily(path):
    d = pd.read_csv(path, usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    d['date'] = t.dt.normalize()
    s = d.groupby('date')['close'].last()
    return s[s.index.dayofweek < 5]


def vix(n):
    d = pd.read_csv(M + f'vixidx/{n}.csv', parse_dates=['date']).set_index('date')['close']
    return d


def main():
    ratio = vix('^VIX') / vix('^VIX3M')
    ratio = ratio.dropna()
    z = (ratio - ratio.rolling(N).mean()) / ratio.rolling(N).std()
    sig = (z > Z)
    dff = pd.read_csv(M + 'fred/DFF.csv')
    dff.columns = ['date', 'v']
    dff['date'] = pd.to_datetime(dff.date)
    dff = pd.to_numeric(dff.set_index('date')['v'], errors='coerce')
    spx = pd.read_csv(M + 'histdata/SPX_D1.csv', parse_dates=['date']).set_index('date')['close']
    px = {'US500': (spx, 0.6), 'US100': (m1_daily(M + 'histdata/NSXUSD_M1.csv.gz'), 2.0),
          'GRXEUR': (m1_daily(M + 'histdata/GRXEUR_M1.csv.gz'), 2.0)}
    out, outs = {}, {}
    for name, (p, spr_pts) in px.items():
        p = p[~p.index.duplicated()]
        p = holdout.drop(p)
        ret = p.pct_change().dropna()
        s = sig.reindex(ret.index).fillna(False).astype(float)
        pos = s.shift(2).fillna(0.0)   # signal day t earns ret(t+2)
        vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
        lev = (0.10 / vol).clip(upper=3.0)
        expo = (pos * lev).fillna(0.0)
        fin = (dff.reindex(ret.index, method='ffill') / 100 + 0.015 - 0.018).fillna(0.0) / 252
        for cm, store in ((1.0, out), (1.5, outs)):
            spr = spr_pts / p.shift(1).reindex(ret.index) * cm
            r = expo * ret - expo.diff().abs().fillna(0.0) * spr / 2 - expo * fin * cm
            r = r[ratio.index[0] + pd.Timedelta(days=60):]
            r = r[r.index >= max(r.index[0], pd.Timestamp('2010-04-01'))]
            store[name] = r
        r = out[name]
        sh = lambda x: x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float('nan')
        trades = int((expo.diff() > 0).sum())
        print(f'{name:7s} {r.index[0].date()}..{r.index[-1].date()} SR {sh(r):5.2f} h1 {sh(r[:"2017"]):5.2f} '
              f'h2 {sh(r["2018":]):5.2f} 1.5x {sh(outs[name]):5.2f} entries {trades} '
              f'(h1 {int((expo[:"2017"].diff() > 0).sum())}) inmkt {(expo != 0).mean():.3f}')
        # beta control: random same-length long, mean over 20 draws
        rng = np.random.default_rng(1)
        k = int((expo != 0).sum())
        ctrl = []
        for _ in range(20):
            idx = rng.choice(len(ret), k, replace=False)
            e = np.zeros(len(ret)); e[idx] = 1
            ctrl.append(sh(pd.Series(e * lev.fillna(0).values * ret.values, index=ret.index)['2011':]))
        print('   random-long control SR', round(float(np.mean(ctrl)), 2))
    R = pd.concat(out, axis=1)
    S = pd.concat(outs, axis=1)
    r, s = R.mean(axis=1, skipna=True), S.mean(axis=1, skipna=True)
    sh = lambda x: x.mean() / x.std() * np.sqrt(252)
    print('combined SR', round(sh(r), 2), 'h1', round(sh(r[:'2017']), 2), 'h2', round(sh(r['2018':]), 2),
          'stress', round(sh(s), 2))
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/vix_vxv_spike.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/vix_vxv_spike_stress.csv', index=False)
    mm = R.fillna(0.0)
    mm.insert(0, 'day', mm.index.strftime('%Y-%m-%d'))
    mm.to_csv(M + 'candidates/vix_vxv_spike_markets.csv', index=False)


if __name__ == '__main__':
    main()
