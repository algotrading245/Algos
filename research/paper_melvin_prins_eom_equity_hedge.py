"""Melvin & Prins (2013/2015) month-end equity-hedging flow, pre-registered, no sweep.
Signal s (known at the close of the second-last business day, past only): US equity return from the previous
month's last close to the second-last close, minus the foreign index return for EUR (GRXEUR) and JPY (JPXJPY);
GBP/AUD/CAD use US alone. Trade only when |s| > expanding median of past |s| (same rule for every pair).
US outperformance -> USD sold in the London 15:00-16:00 hour: long EURUSD/GBPUSD/AUDUSD, short USDJPY/USDCAD.
A: enter London 15:00 on the last business day, exit 16:00.   B: enter 16:00, exit next business day 12:00,
direction opposite to that day's 15:00-16:00 move (the paper's reversion).   C = A + B.
Costs: round trip SP bp per trade (x1, 1.5, 2). Clock: histdata server = NY+7, converted to London (matrix()).
Holdout dropped. Run: python research/paper_melvin_prins_eom_equity_hedge.py"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'research')
sys.path.insert(0, 'tools')
import holdout
from intraday_momentum import at, minutes
from overnight_intraday_reversal import matrix

FX = {'EURUSD': (1, 0.85, 'GRXEUR'), 'GBPUSD': (1, 1.1, None), 'AUDUSD': (1, 1.1, None),
      'USDJPY': (-1, 0.85, 'JPXJPY'), 'USDCAD': (-1, 1.2, None)}


def sharpe(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 30 and x.std() > 0 else float('nan')


def px(sym):
    d, p = matrix(sym, 'Europe/London')
    lp = np.log(p.astype(float))
    return pd.DataFrame({'p15': at(lp, minutes('15:00')), 'p16': at(lp, minutes('16:00')),
                         'p12': at(lp, minutes('12:00'))}, index=d)


def eq_close(sym):
    d, p = matrix(sym, 'Europe/London')
    return pd.Series(at(np.log(p.astype(float)), minutes('16:00')), index=d)


def signals():
    us = eq_close('SPXUSD').dropna()
    fo = {k: eq_close(k).dropna() for k in ('GRXEUR', 'JPXJPY')}
    return us, fo


def month_ret(c, last2, prev_last):
    return c.get(last2, np.nan) - c.get(prev_last, np.nan)


def run(sym, us, fo):
    sign, sp, fidx = FX[sym]
    P = px(sym)
    P = P[P.index.dayofweek < 5]
    days = P.index
    ym = pd.Series(days.year * 100 + days.month, index=days)
    last = ym.groupby(ym).apply(lambda s: s.index[-1])
    rows = []
    prev = None
    for k, (m, t) in enumerate(last.items()):
        if prev is not None:
            idx = days.get_loc(t)
            if idx >= 2 and idx + 1 < len(days):
                d2 = days[idx - 1]
                s = month_ret(us, d2, prev)
                if fidx:
                    s -= month_ret(fo[fidx], d2, prev)
                rows.append((t, days[idx + 1], s))
        prev = t
    E = pd.DataFrame(rows, columns=['t', 'nxt', 's']).dropna()
    med = E.s.abs().expanding().median().shift(1)
    E['on'] = E.s.abs() > med
    E = E[E.on & med.notna()]
    a_gr = sign * np.sign(E.s.values) * (P.p16.reindex(E.t).values - P.p15.reindex(E.t).values)
    mv = P.p16.reindex(E.t).values - P.p15.reindex(E.t).values
    b_gr = -np.sign(mv) * (P.p12.reindex(E.nxt).values - P.p16.reindex(E.t).values)
    out = pd.DataFrame({'A': a_gr, 'B': b_gr}, index=pd.DatetimeIndex(E.t.values)).dropna(how='all')
    cost = sp * 1e-4
    return out, cost


def main():
    us, fo = signals()
    res = {}
    for sym in FX:
        g, cost = run(sym, us, fo)
        g = g.loc['2005':]
        g = g[g.index < holdout.START]
        print(sym, 'events', g.A.notna().sum(), g.index[0].date())
        for v in ('A', 'B', 'C'):
            gv = g.A.fillna(0) + g.B.fillna(0) if v == 'C' else g[v].fillna(0)
            ntr = (g.A.notna().astype(int) + g.B.notna().astype(int)) if v == 'C' else g[v].notna().astype(int)
            for cm in (1.0, 1.5, 2.0):
                res[(sym, v, cm)] = gv - ntr * cost * cm
    # daily frame, weekday index from 2005
    idx = pd.bdate_range('2005-01-03', holdout.START - pd.Timedelta(days=1))
    D = lambda sym, v, cm: res[(sym, v, cm)].reindex(idx).fillna(0.0)
    # pooled per-event stats (ret per event, bp) and daily-series Sharpe (pooled, equal weight)
    for v in ('A', 'B', 'C'):
        print('== variant', v)
        for cm in (1.0, 1.5, 2.0):
            pool = pd.concat([D(s, v, cm) for s in FX], axis=1).mean(axis=1)
            ev = pd.concat([res[(s, v, cm)] for s in FX])
            ev = ev[ev != 0]
            print(' cost x', cm, 'pooled SR', round(sharpe(pool), 2), 'h1', round(sharpe(pool[:'2017']), 2),
                  'h2', round(sharpe(pool['2018':]), 2), 'mean/event bp', round(ev.mean() * 1e4, 2),
                  'events', len(ev), 'hit', round((ev > 0).mean(), 2))
        for s in FX:
            x = D(s, v, 1.0)
            print('   ', s, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    import pickle
    pickle.dump((res, idx), open('research/melvin_prins_res.pkl', 'wb'))


if __name__ == '__main__':
    main()
