"""fix_vrp_leg_fidelity: per-market halves of the VRP leg (US500, US100, DAX), correlation to every book leg (gold hold
included), the US500+US100 subset (the EA's markets), and a random same-count 10-day long control per market written
as candidates vrp_ctrl_s0..s2 (gate each with tools/gates.py --dry-run). Same costs, vol scaling and window as
vrp_gap.run. No new settings."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
sys.path.insert(0, 'research')
import holdout
import vrp_gap as V
import vrp_gap_equity_indices as E
import book_sim as B

M = 'marketdata/'


def run_ctrl(m, hold, n_ent, rng, cm=1.0):
    px = m['px'].dropna()
    px = px[~px.index.duplicated()]
    px = holdout.drop(px)
    ret = px.pct_change().dropna()
    iv = m['iv'].reindex(px.index, method='ffill')
    rv = ret.rolling(22).std() * np.sqrt(252)
    gap = (iv / 100) ** 2 - rv ** 2
    thr = gap.rolling(252).quantile(2 / 3)
    valid = thr.shift(1).reindex(ret.index).notna()
    idx = list(px.index)
    pos_i = {d: i for i, d in enumerate(idx)}
    mondays = [d for d in px.index[px.index.dayofweek == 0] if d in valid.index and valid.get(d, False)]
    pick = rng.choice(len(mondays), size=min(n_ent, len(mondays)), replace=False)
    arr = np.zeros(len(idx))
    for k in pick:
        i = pos_i[mondays[k]]
        arr[i + 1:i + 1 + hold] = 1.0
    pos = pd.Series(arr, index=px.index)
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    lev = (0.10 / vol).clip(upper=3.0)
    expo = (pos * lev).reindex(ret.index).fillna(0.0)
    spr = m['spr'](px.shift(1)).reindex(ret.index) * cm
    fin = m['fin'](ret.index) * cm / 252
    r = expo * ret - expo.diff().abs().fillna(0.0) * spr / 2 - expo * fin.fillna(0.0)
    return r[valid]


def n_entries(m):
    # signal Mondays that start a hold (counted from the exposure series)
    r, e = V.run(m, 10)
    px = holdout.drop(m['px'].dropna())
    ret = px.pct_change().dropna()
    sig = (e != 0).astype(int)
    starts = ((sig == 1) & (sig.shift(1).fillna(0) == 0)).sum()
    # overlapping signals extend holds, so independent Monday signals can be more than runs: count Monday signals
    return int(round((e != 0).sum() / 10)), int(starts)


def sr(x):
    return V.sharpe(x)


def main():
    dff = V.rate(M + 'fred/DFF.csv')
    ecb = V.rate(M + 'fred/ECBDFR.csv')
    vix = V.vol_series(M + 'fred/VIXCLS.csv')
    mk = {
        'US500': dict(px=V.daily_spx(), iv=vix, spr=lambda p: 0.6 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.018),
        'US100': dict(px=E.daily_m1('NSXUSD'), iv=vix, spr=lambda p: 1.0 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.010),
        'DAX': dict(px=E.daily_m1('GRXEUR'), iv=vix, spr=lambda p: 1.0 / p,
                    fin=lambda i: ecb.reindex(i, method='ffill') / 100 + 0.015 - 0.025),
    }
    R, S = {}, {}
    for n, m in mk.items():
        r, e = V.run(m, 10)
        rs, _ = V.run(m, 10, 1.5)
        R[n], S[n] = r, rs
        print(f'{n:6s} SR all {sr(r):5.2f} h1 {sr(r[:"2017"]):5.2f} h2 {sr(r["2018":]):5.2f} 1.5x {sr(rs):5.2f} '
              f'in-market days {(e != 0).sum()}')
    Rd, Sd = pd.concat(R, axis=1), pd.concat(S, axis=1)
    r2, s2 = Rd[['US500', 'US100']].mean(axis=1, skipna=True), Sd[['US500', 'US100']].mean(axis=1, skipna=True)
    print(f'US500+US100 SR all {sr(r2):5.2f} h1 {sr(r2[:"2017"]):5.2f} h2 {sr(r2["2018":]):5.2f} 1.5x {sr(s2):5.2f}')
    r3 = Rd.mean(axis=1, skipna=True)
    print(f'all three   SR all {sr(r3):5.2f} h1 {sr(r3[:"2017"]):5.2f} h2 {sr(r3["2018":]):5.2f}')

    # correlation with every book leg (daily), for the 3-market and 2-market series
    legs = B.legs(without=['vrp_gap_equity_indices'])
    for nm, ser in (('3mkt', r3), ('US500+US100', r2)):
        j = legs.join(ser.rename('v'), how='inner')
        print(nm, 'corr to legs:', {c: round(j[c].corr(j['v']), 3) for c in legs.columns})
    # random control: same entry count per market, 3 seeds
    ents = {n: n_entries(m)[0] for n, m in mk.items()}
    print('entries per market (in-market days / 10):', ents)
    for seed in range(3):
        rng = np.random.default_rng(100 + seed)
        C, CS = {}, {}
        for n, m in mk.items():
            st = np.random.default_rng(100 + seed)
            C[n] = run_ctrl(m, 10, ents[n], np.random.default_rng(1000 * seed + len(n)))
            CS[n] = run_ctrl(m, 10, ents[n], np.random.default_rng(1000 * seed + len(n)), 1.5)
        Cd, CSd = pd.concat(C, axis=1), pd.concat(CS, axis=1)
        c, cs = Cd.mean(axis=1, skipna=True), CSd.mean(axis=1, skipna=True)
        tag = f'vrp_ctrl_s{seed}'
        pd.DataFrame({'day': c.index.strftime('%Y-%m-%d'), 'r': c.values}).to_csv(M + f'candidates/{tag}.csv', index=False)
        pd.DataFrame({'day': cs.index.strftime('%Y-%m-%d'), 'r': cs.values}).to_csv(M + f'candidates/{tag}_stress.csv', index=False)
        mm = Cd.copy()
        mm.insert(0, 'day', mm.index.strftime('%Y-%m-%d'))
        mm.fillna(0.0).to_csv(M + f'candidates/{tag}_markets.csv', index=False)
        print(f'{tag} SR all {sr(c):5.2f} h1 {sr(c[:"2017"]):5.2f} h2 {sr(c["2018":]):5.2f} 1.5x {sr(cs):5.2f}')


if __name__ == '__main__':
    main()
