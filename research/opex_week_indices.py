"""Option-expiration-week long on index CFDs (Stivers & Sun; Quantpedia). Long Mon open -> Fri close of the week
whose Friday is the 3rd Friday. No parameters. Costs: spread once per round trip + FTMO swap per night (Wed x3)."""
import sys
sys.path.insert(0, 'tools')
import numpy as np
import pandas as pd
import holdout

MK = {  # file, spread pts, swap pts/night (long)
    'SPXUSD': (0.60, 1.6052),
    'NSXUSD': (1.73, 7.3072),
    'GRXEUR': (1.50, 5.04),
    'JPXJPY': (10.0, 9.95),
}


def daily(sym):
    d = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz')
    d['t'] = pd.to_datetime(d['time'] + 6 * 3600, unit='s')
    d['day'] = d['t'].dt.normalize()
    g = d.groupby('day')
    o = g['open'].first()
    c = g['close'].last()
    n = g.size()
    x = pd.DataFrame({'o': o, 'c': c, 'n': n})
    x = x[(x.index.dayofweek < 5) & (x.n > 100)]
    return holdout.drop(x)


def third_friday_week(idx):
    """True for days Mon-Fri of the week whose Friday is the 3rd Friday."""
    fri = idx + pd.to_timedelta(4 - idx.dayofweek, unit='D')
    return (fri.day >= 15) & (fri.day <= 21)


def leg(sym, mult=1.0, always=False):
    sp, sw = MK[sym]
    x = daily(sym)
    prev = x.c.shift(1)
    inw = pd.Series(third_friday_week(x.index), index=x.index)
    r = pd.Series(0.0, index=x.index)
    for i, dt in enumerate(x.index):
        if not inw.iloc[i]:
            continue
        dow = dt.dayofweek
        if dow == 0:
            base = x.o.iloc[i]
            gross = x.c.iloc[i] - base
            cost = sp * mult
            r.iloc[i] = (gross - cost) / base
        else:
            if i == 0:
                continue
            base = prev.iloc[i]
            r.iloc[i] = (x.c.iloc[i] - base) / base
        # swap charged on the night after each held day except Friday (Wed night counts 3)
        if dow < 4:
            nights = 3 if dow == 2 else 1
            r.iloc[i] -= sw * nights * mult / x.c.iloc[i]
    return r


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0


if __name__ == '__main__':
    out, outs = {}, {}
    for s in MK:
        out[s] = leg(s)
        outs[s] = leg(s, 1.5)
    R = pd.DataFrame(out).dropna(how='all').fillna(0)
    S = pd.DataFrame(outs).reindex(R.index).fillna(0)
    for s in MK:
        for nm, M in (('1x', R), ('1.5x', S)):
            r = M[s]
            a, b = r[r.index < '2018-01-01'], r[r.index >= '2018-01-01']
            print(s, nm, 'Sharpe all %.2f h1 %.2f h2 %.2f' % (sharpe(r), sharpe(a), sharpe(b)),
                  'ann ret %.2f%%' % (r.mean() * 252 * 100), 'start', r.index[0].date())
    # gross (no cost) check
    for s in MK:
        g = leg(s, 0.0)
        print(s, 'gross Sharpe %.2f' % sharpe(g))
    us = R[['SPXUSD', 'NSXUSD']].mean(axis=1)
    uss = S[['SPXUSD', 'NSXUSD']].mean(axis=1)
    a, b = us[us.index < '2018-01-01'], us[us.index >= '2018-01-01']
    print('US basket 1x halves %.2f %.2f; 1.5x %.2f' % (sharpe(a), sharpe(b), sharpe(uss)))
    for nm, v in (('opex_week_indices', us), ('opex_week_indices_stress', uss)):
        pd.DataFrame({'day': v.index.strftime('%Y-%m-%d'), 'r': v.values}).to_csv(f'marketdata/candidates/{nm}.csv', index=False)
    M = R.copy()
    M.insert(0, 'day', M.index.strftime('%Y-%m-%d'))
    M.to_csv('marketdata/candidates/opex_week_indices_markets.csv', index=False)
