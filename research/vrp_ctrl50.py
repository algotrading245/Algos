"""fix_vrp_leg_fidelity2: 50-seed random-long control for the VRP leg. Same rule as vrp_gap_equity_indices (3 markets,
10-day long, vol scale 10%/yr cap 3x, same costs), but the Monday entries are drawn at random (same number of entries per
market as the signal gives, from the Mondays the signal could have used). Reports Sharpe and book gain (2018+) of the
VRP leg against the distribution of the 50 controls. No setting is tuned."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
sys.path.insert(0, 'research')
import holdout
import book_sim as B
import vrp_gap as V
import vrp_gap_equity_indices as E

M = 'marketdata/'
NSEED = 50


def markets():
    dff = V.rate(M + 'fred/DFF.csv')
    ecb = V.rate(M + 'fred/ECBDFR.csv')
    vix = V.vol_series(M + 'fred/VIXCLS.csv')
    return {
        'US500': dict(px=V.daily_spx(), iv=vix, spr=lambda p: 0.6 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.018),
        'US100': dict(px=E.daily_m1('NSXUSD'), iv=vix, spr=lambda p: 1.0 / p,
                      fin=lambda i: dff.reindex(i, method='ffill') / 100 + 0.015 - 0.010),
        'DAX': dict(px=E.daily_m1('GRXEUR'), iv=vix, spr=lambda p: 1.0 / p,
                    fin=lambda i: ecb.reindex(i, method='ffill') / 100 + 0.015 - 0.025),
    }


def run_rand(m, hold, rng, n_ent, cm=1.0):
    px = m['px'].dropna()
    px = px[~px.index.duplicated()]
    px = holdout.drop(px)
    ret = px.pct_change().dropna()
    iv = m['iv'].reindex(px.index, method='ffill')
    rv = ret.rolling(22).std() * np.sqrt(252)
    gap = (iv / 100) ** 2 - rv ** 2
    thr = gap.rolling(252).quantile(2 / 3)
    ok = thr.shift(1).notna()
    idx = list(px.index)
    mond = [i for i, d in enumerate(idx) if d.dayofweek == 0 and bool(ok.iloc[i])]
    pick = rng.choice(mond, size=min(n_ent, len(mond)), replace=False)
    arr = np.zeros(len(idx))
    for i in pick:
        arr[i + 1:i + 1 + hold] = 1.0
    pos = pd.Series(arr, index=px.index)
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    lev = (0.10 / vol).clip(upper=3.0)
    expo = (pos * lev).reindex(ret.index).fillna(0.0)
    spr = m['spr'](px.shift(1)).reindex(ret.index) * cm
    d_expo = expo.diff().abs().fillna(0.0)
    fin = m['fin'](ret.index) * cm / 252
    r = expo * ret - d_expo * spr / 2 - expo * fin.fillna(0.0)
    valid = thr.shift(1).reindex(ret.index).notna()
    return r[valid], (expo[valid] != 0).mean()


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252)


def book_s(leg, base_legs):
    new, _ = B.combine(B.legs(without=['vrp_gap_equity_indices'], extra={'ctrl': leg}))
    mb = B.risk_layer(new)
    return sharpe(mb[mb.index >= '2018-01-01'])


def main():
    mk = markets()
    sig, ent, inm = {}, {}, {}
    for n, m in mk.items():
        r, e = V.run(m, 10)
        sig[n] = r
        inm[n] = (e != 0).mean()
        # entries = number of distinct signal starts
        ent[n] = int((e.diff().fillna(0) > 0).sum()) if False else int(round((e != 0).sum() / 10 / 1.0))
    vrp = pd.concat(sig, axis=1).mean(axis=1, skipna=True)
    base_legs = B.legs(without=['vrp_gap_equity_indices'])
    base, _ = B.combine(base_legs)
    mb = B.risk_layer(base)
    s0 = sharpe(mb[mb.index >= '2018-01-01'])
    g_vrp = book_s(vrp, base_legs) - s0
    sr_vrp = sharpe(vrp)
    sr_vrp2 = sharpe(vrp['2018':])
    print(f'book without VRP 2018+ Sharpe {s0:.3f}; VRP leg Sharpe all {sr_vrp:.2f} 2018+ {sr_vrp2:.2f} book gain {g_vrp:+.3f}')
    print('in-market share of the signal per market', {k: round(v, 2) for k, v in inm.items()},
          'entries used (in-market days / 10)', ent)
    srs, srs2, gains, shares = [], [], [], []
    for seed in range(NSEED):
        rng = np.random.default_rng(1000 + seed)
        rr, sh = {}, []
        for n, m in mk.items():
            r, s = run_rand(m, 10, rng, ent[n])
            rr[n] = r
            sh.append(s)
        c = pd.concat(rr, axis=1).mean(axis=1, skipna=True)
        srs.append(sharpe(c))
        srs2.append(sharpe(c['2018':]))
        gains.append(book_s(c, base_legs) - s0)
        shares.append(np.mean(sh))
    srs, srs2, gains = map(np.array, (srs, srs2, gains))
    print(f'{NSEED} random-long controls: in-market share mean {np.mean(shares):.2f}')
    print(f'  Sharpe all  mean {srs.mean():.2f} sd {srs.std():.2f}  VRP {sr_vrp:.2f} percentile {100*(srs < sr_vrp).mean():.0f}%')
    print(f'  Sharpe 2018+ mean {srs2.mean():.2f} sd {srs2.std():.2f}  VRP {sr_vrp2:.2f} percentile {100*(srs2 < sr_vrp2).mean():.0f}%')
    print(f'  book gain 2018+ mean {gains.mean():+.3f} sd {gains.std():.3f}  VRP {g_vrp:+.3f} percentile {100*(gains < g_vrp).mean():.0f}%')


if __name__ == '__main__':
    main()
