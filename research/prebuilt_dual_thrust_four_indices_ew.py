"""Dual Thrust k1=0.3/k2=0.7 N=4 on SPX, NSX, GRX, JPX equal weight. Same rule as the pair run, no fitting.
Run: python research/prebuilt_dual_thrust_four_indices_ew.py"""
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
    R = {cm: pd.DataFrame(v).fillna(0).loc['2010':] for cm, v in res.items()}
    b, bs, b2 = R[1.0].mean(axis=1), R[1.5].mean(axis=1), R[2.0].mean(axis=1)
    print('four EW SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          '1.5x', round(sharpe(bs), 2), '2x', round(sharpe(b2), 2))
    name = 'prebuilt_dual_thrust_four_indices_ew'
    for nm, ser in ((name, b), (name + '_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
