"""Dual Thrust on indices, asymmetric k (long 0.3, short 0.7), N=4, fixed before the test, no sweep.
Reuses sim() of prebuilt_dual_thrust_fx_gold.py with K1/K2 set. Candidate = SPXUSD+NSXUSD equal weight;
GRXEUR, JPXJPY as belief markets. Run: python research/prebuilt_dual_thrust_indices.py"""
import sys
import pandas as pd
sys.path.insert(0, 'research')
sys.path.insert(0, 'tools')
import holdout
import prebuilt_dual_thrust_fx_gold as dt

dt.K1, dt.K2 = 0.3, 0.7
SPR = {'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4, 'GRXEUR': 2.0e-4, 'JPXJPY': 3.0e-4}
sharpe = dt.sharpe


def main():
    res = {1.0: {}, 1.5: {}, 2.0: {}}
    for s in SPR:
        gr, fl, idx = dt.sim(s, dt.load(s))
        for cm in res:
            res[cm][s] = holdout.drop((gr - fl * SPR[s] * cm).reindex(idx).fillna(0.0))
        x = res[1.0][s]
        print(s, x.index[0].date(), 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2),
              'h2', round(sharpe(x['2018':]), 2), '1.5x', round(sharpe(res[1.5][s]), 2),
              '2x', round(sharpe(res[2.0][s]), 2), flush=True)
    R = {cm: pd.DataFrame(v).fillna(0).loc['2010':] for cm, v in res.items()}
    cols = ['SPXUSD', 'NSXUSD']
    b, bs = R[1.0][cols].mean(axis=1), R[1.5][cols].mean(axis=1)
    print('book SPX+NSX SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          '1.5x', round(sharpe(bs), 2), '2x', round(sharpe(R[2.0][cols].mean(axis=1)), 2))
    name = 'prebuilt_dual_thrust_indices_overnight_free'
    for nm, ser in ((name, b), (name + '_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
