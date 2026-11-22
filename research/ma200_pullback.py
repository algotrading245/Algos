"""Quantpedia (2026) MA200 trend filter + 2 down days, long at close, exit next close (1-day hold). Fixed parameters, no sweep.
Signal at close t: close_t > SMA200_t and ret_t<0 and ret_{t-1}<0 -> long from close t to close t+1.
Cost: full spread per entry+exit (round trip, bp) + long swap per calendar night held. Basket: one unit of risk split over active signals.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

# (spread round trip bp, long swap bp per night) from docs/ftmo_specs.json, rounded up
COST = {'US500': (1.0, 2.3), 'NSXUSD': (1.5, 3.0), 'XAUUSD': (2.0, 2.5), 'GRXEUR': (2.0, 2.5), 'JPXJPY': (2.0, 2.5),
        'EURUSD': (1.0, 0.9), 'USDJPY': (1.0, 0.0), 'AUDCAD': (1.5, 0.5)}


def load(sym):
    if sym == 'US500':
        return pd.read_csv('marketdata/histdata/SPX_D1.csv', parse_dates=['date']).set_index('date')['close']
    d = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz')
    d['t'] = pd.to_datetime(d['time'], unit='s')
    s = d.set_index('t')['close'].resample('1D').last().dropna()
    return s


def leg(px, mult=1.0):
    px = px[px.index.dayofweek < 5]
    ret = px.pct_change()
    sma = px.rolling(200).mean()
    sig = (px > sma) & (ret < 0) & (ret.shift(1) < 0)
    pos = sig.astype(float)  # set at close t
    nxt = px.pct_change().shift(-1)  # return t -> t+1
    nights = pd.Series(px.index, index=px.index).diff().shift(-1).dt.days.fillna(1)
    return pos, nxt, nights


def daily(sym, mult=1.0):
    px = holdout.drop(load(sym))
    pos, nxt, nights = leg(px)
    sp, sw = COST[sym]
    g = pos * nxt - pos * (sp / 1e4) * mult - pos * nights * sw / 1e4 * mult
    # book return on day t+1 (when earned)
    g = g.shift(1)
    pos = pos.shift(1)
    return g.dropna(), pos.dropna()


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def rep(name, r):
    r = holdout.drop(r)
    print(f'{name:12s} full {sharpe(r):5.2f} to2017 {sharpe(r[:"2017"]):5.2f} 2018on {sharpe(r["2018":]):5.2f} n {len(r)} inmkt {(r!=0).mean():.2f} ann% {r.mean()*252*100:.2f}')


def basket(syms, mult):
    gs, ps = {}, {}
    for s in syms:
        gs[s], ps[s] = daily(s, mult)
    G = pd.DataFrame(gs)
    P = pd.DataFrame(ps)
    act = P.notna() & G.notna()
    n = P.where(act).sum(axis=1)
    # unit risk split over active signals; days with no signal -> 0 ; markets not yet started excluded
    w = P.div(n.replace(0, np.nan), axis=0)
    ret = (G.div(P.replace(0, np.nan)).fillna(0) * w.fillna(0)).sum(axis=1)  # per-unit-return * weight
    return ret, G


if __name__ == '__main__':
    syms = ['US500', 'NSXUSD', 'XAUUSD', 'GRXEUR', 'JPXJPY', 'EURUSD', 'USDJPY', 'AUDCAD']
    out = {}
    for m in (1.0, 1.5, 2.0):
        print('--- cost x', m)
        for s in syms:
            g, p = daily(s, m)
            rep(s, g)
            if m == 1.0:
                out[s] = g
            if m == 1.5:
                out[s + '_s'] = g
    core = ['US500', 'NSXUSD', 'XAUUSD', 'GRXEUR', 'JPXJPY', 'EURUSD']
    res = {}
    for m in (1.0, 1.5, 2.0):
        b, _ = basket(core, m)
        rep(f'basket x{m}', b)
        res[m] = b
    b = res[1.0]
    b = holdout.drop(b)
    b.index = pd.to_datetime(b.index)
    b.rename_axis('day').rename('r').to_csv('marketdata/candidates/ma200_pullback.csv')
    res[1.5].rename_axis('day').rename('r').pipe(holdout.drop).to_csv('marketdata/candidates/ma200_pullback_stress.csv')
    mk = pd.DataFrame({s: out[s] for s in syms})
    mk.rename_axis('day').to_csv('marketdata/candidates/ma200_pullback_markets.csv')
