"""Pre-registered variant of vrp_gap (queue: variant_vrp_gap_equity_indices). Same rule, only markets changed:
US500, US100, DAX; IV proxy = VIX (FRED VIXCLS) for all three. Monday: gap = VIX^2 - RV22^2 (past-only, lagged a day),
top third of trailing 252 -> long 10 trading days (fixed, no sweep). Vol-scaled to 10%/yr (60d, cap 3x).
Costs: half spread per exposure change, financing on long (policy rate + 1.5% - dividend yield). Stress 1.5x.
Also: beta control (random same-length long, same count of entries), corr to buy-and-hold."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout
sys.path.insert(0, 'research')
import vrp_gap as V

M = 'marketdata/'


def daily_m1(name):
    d = pd.read_csv(M + f'histdata/{name}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s')
    d['date'] = t.dt.normalize()
    s = d.groupby('date')['close'].last()
    return s[s.index.dayofweek < 5]


def main():
    dff = V.rate(M + 'fred/DFF.csv')
    ecb = V.rate(M + 'fred/ECBDFR.csv')
    vix = V.vol_series(M + 'fred/VIXCLS.csv')
    mk = {
        'US500': dict(px=V.daily_spx(), iv=vix, spr=lambda p: 0.6 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.018),
        'US100': dict(px=daily_m1('NSXUSD'), iv=vix, spr=lambda p: 1.0 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.010),
        'DAX': dict(px=daily_m1('GRXEUR'), iv=vix, spr=lambda p: 1.0 / p,
                    fin=lambda i: ecb.reindex(i, method='ffill') / 100 + 0.015 - 0.025),
    }
    R, S, B = {}, {}, {}
    for n, m in mk.items():
        r, e = V.run(m, 10)
        rs, _ = V.run(m, 10, 1.5)
        rd, _ = V.run(m, 10, 2.0)
        px = holdout.drop(m['px'].dropna())
        bh = px.pct_change().dropna().reindex(r.index)
        R[n], S[n], B[n] = r, rs, bh
        print(f'{n:6s} n={len(r)} {r.index[0].date()}..{r.index[-1].date()} SR all {V.sharpe(r):5.2f} '
              f'h1 {V.sharpe(r[:"2017"]):5.2f} h2 {V.sharpe(r["2018":]):5.2f} 1.5x {V.sharpe(rs):5.2f} '
              f'2x {V.sharpe(rd):5.2f} inmkt {(e != 0).mean():.2f} BH SR {V.sharpe(bh):5.2f} corrBH {r.corr(bh):.2f}')
    Rd, Sd = pd.concat(R, axis=1), pd.concat(S, axis=1)
    r, s = Rd.mean(axis=1, skipna=True), Sd.mean(axis=1, skipna=True)
    print('combined SR all', round(V.sharpe(r), 2), 'h1', round(V.sharpe(r[:'2017']), 2),
          'h2', round(V.sharpe(r['2018':]), 2), 'stress', round(V.sharpe(s), 2))
    # beta control: random entries, same count, 10-day long, on US500, 20 seeds
    px = holdout.drop(mk['US500']['px'].dropna())
    ret = px.pct_change().dropna()
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    lev = (0.10 / vol).clip(upper=3.0)
    ent = int(round((V.run(mk['US500'], 10)[1] != 0).mean() * len(ret) / 10))
    rng = np.random.default_rng(0)
    mondays = np.where(ret.index.dayofweek == 0)[0]
    srs = []
    for _ in range(50):
        pos = np.zeros(len(ret))
        for i in rng.choice(mondays, size=min(ent, len(mondays)), replace=False):
            pos[i + 1:i + 11] = 1
        rr = pd.Series(pos, index=ret.index) * lev * ret
        srs.append(V.sharpe(rr['2011':]))
    print('random-entry control US500 SR mean %.2f sd %.2f (n entries %d)' % (np.mean(srs), np.std(srs), ent))
    tag = 'vrp_gap_equity_indices'
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + f'candidates/{tag}.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + f'candidates/{tag}_stress.csv', index=False)
    mm = Rd.copy()
    mm.insert(0, 'day', mm.index.strftime('%Y-%m-%d'))
    mm.fillna(0.0).to_csv(M + f'candidates/{tag}_markets.csv', index=False)


if __name__ == '__main__':
    main()
