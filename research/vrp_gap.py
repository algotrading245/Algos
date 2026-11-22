"""VRP gap timing (Bollerslev-Tauchen-Zhou 2009; working paper FEDS 2007-11 read: VRP = implied - realized variance,
high premium -> higher future return, best at 1-3 months). Rule from the queue item: every Monday, gap = IV^2 - RV22^2
(close-to-close, annualized; IV from GVZ / VIX / EVZ, all lagged by the weekend so past-only). Gap in the top third of
its trailing 252 days -> long for N days (5, 10, 20), else flat. Entry at Monday close (one extra day of lag).
Positions are vol-scaled to 10% a year (trailing 60 days, cap 3x). Costs: half spread per unit of exposure change,
financing on long exposure. Stress = 1.5x spread and 1.5x financing/markup.
Output: marketdata/candidates/vrp_gap{,_stress,_markets}.csv (headline hold = 10 days, fixed in advance)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'


def vol_series(path, col=None):
    d = pd.read_csv(path)
    d.columns = ['date', 'v']
    d['date'] = pd.to_datetime(d['date'])
    d['v'] = pd.to_numeric(d['v'], errors='coerce')
    return d.dropna().set_index('date')['v']


def daily_gold():
    d = pd.read_csv(M + 'histdata/XAUUSD_D1.csv.gz')
    d['date'] = pd.to_datetime(d.time, unit='s').dt.normalize()
    return d.groupby('date')['close'].last()


def daily_spx():
    d = pd.read_csv(M + 'histdata/SPX_D1.csv', parse_dates=['date'])
    return d.set_index('date')['close']


def daily_eur():
    d = pd.read_csv(M + 'histdata/EURUSD_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)  # NY 17:00 roll (approx, ignores DST)
    d['date'] = t.dt.normalize()
    s = d.groupby('date')['close'].last()
    s = s[s.index.dayofweek < 5]
    return s


def rate(path):
    d = pd.read_csv(path)
    d.columns = ['date', 'v']
    d['date'] = pd.to_datetime(d['date'])
    d['v'] = pd.to_numeric(d['v'], errors='coerce')
    return d.dropna().set_index('date')['v']


# market: price, IV, spread (fraction of price, full), financing on LONG (annual, positive = cost)
def markets():
    gold, spx, eur = daily_gold(), daily_spx(), daily_eur()
    ecb = rate(M + 'fred/ECBDFR.csv')
    dff = rate(M + 'fred/DFF.csv')
    out = {}
    # gold: spread 0.30 USD (cap), long financing 2.5%/yr (swap, assumed from ftmo spec magnitude)
    out['XAUUSD'] = dict(px=gold, iv=vol_series(M + 'fred/GVZCLS.csv'), spr=lambda p: 0.30 / p,
                         fin=lambda idx: pd.Series(0.025, index=idx))
    # US500: spread 0.6 pt; financing = DFF + 1.5% markup minus dividend yield ~1.8%
    out['US500'] = dict(px=spx, iv=vol_series(M + 'fred/VIXCLS.csv'), spr=lambda p: 0.6 / p,
                        fin=lambda idx: (dff.reindex(idx, method='ffill') / 100 + 0.015 - 0.018))
    # EURUSD: spread 1.2 pip incl commission; long earns (ECB - DFF) minus 0.7% markup
    out['EURUSD'] = dict(px=eur, iv=vol_series(M + 'fred/EVZCLS.csv'), spr=lambda p: 0.00012 / p,
                         fin=lambda idx: -((ecb.reindex(idx, method='ffill') - dff.reindex(idx, method='ffill')) / 100) + 0.007)
    return out


def run(m, hold, cm=1.0):
    px = m['px'].dropna()
    px = px[~px.index.duplicated()]
    px = holdout.drop(px)
    ret = px.pct_change().dropna()
    iv = m['iv'].reindex(px.index, method='ffill')
    rv = ret.rolling(22).std() * np.sqrt(252)
    gap = (iv / 100) ** 2 - rv ** 2
    thr = gap.rolling(252).quantile(2 / 3)
    sig = (gap > thr)
    # Monday decisions use Friday-or-earlier data: signal row t = Monday value shifted from previous trading day
    sig_prev = sig.shift(1)  # known at previous close
    mondays = sig_prev.index[sig_prev.index.dayofweek == 0]
    pos = pd.Series(0.0, index=px.index)
    k = int(np.ceil(hold / 5))
    # position window: from Monday close (entry) for `hold` trading days after; extended by later on-signals
    idx = list(px.index)
    pos_arr = np.zeros(len(idx))
    pos_i = {d: i for i, d in enumerate(idx)}
    for d in mondays:
        if bool(sig_prev.loc[d]) and not pd.isna(thr.shift(1).loc[d]):
            i = pos_i[d]
            pos_arr[i + 1:i + 1 + hold] = 1.0   # hold N days of returns starting next day
    pos = pd.Series(pos_arr, index=px.index)
    # vol scale to 10% a year with trailing 60d vol (lagged)
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    lev = (0.10 / vol).clip(upper=3.0)
    expo = (pos * lev).reindex(ret.index).fillna(0.0)
    spr = m['spr'](px.shift(1)).reindex(ret.index) * cm
    d_expo = expo.diff().abs().fillna(0.0)
    fin = m['fin'](ret.index) * cm / 252
    r = expo * ret - d_expo * spr / 2 - expo * fin.fillna(0.0)
    valid = thr.shift(1).reindex(ret.index).notna()
    r = r[valid]
    return r, expo[valid]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    mk = markets()
    res = {}
    for hold in (5, 10, 20):
        for name, m in mk.items():
            r, e = run(m, hold)
            rs, _ = run(m, hold, 1.5)
            rd, _ = run(m, hold, 2.0)
            h1 = r[:'2017-12-31']
            h2 = r['2018-01-01':]
            print(f'hold {hold:2d} {name:7s} n={len(r)} {r.index[0].date()}..{r.index[-1].date()} '
                  f'SR all {sharpe(r):5.2f} h1 {sharpe(h1):5.2f} h2 {sharpe(h2):5.2f} '
                  f'1.5x {sharpe(rs):5.2f} 2x {sharpe(rd):5.2f} inmkt {(e != 0).mean():.2f}')
            res[(hold, name)] = (r, rs)
    # headline: hold 10, equal-weight average over available markets
    for hold, tag in ((10, 'vrp_gap'),):
        R = pd.concat({n: res[(hold, n)][0] for n in mk}, axis=1)
        S = pd.concat({n: res[(hold, n)][1] for n in mk}, axis=1)
        r = R.mean(axis=1, skipna=True)
        s = S.mean(axis=1, skipna=True)
        pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(
            M + f'candidates/{tag}.csv', index=False)
        pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(
            M + f'candidates/{tag}_stress.csv', index=False)
        mm = R.copy()
        mm.insert(0, 'day', mm.index.strftime('%Y-%m-%d'))
        mm.fillna(0.0).to_csv(M + f'candidates/{tag}_markets.csv', index=False)
        print('combined', tag, 'SR all', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2),
              'h2', round(sharpe(r['2018':]), 2), 'stress', round(sharpe(s), 2))


if __name__ == '__main__':
    main()
