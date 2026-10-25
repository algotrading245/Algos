"""Gatev-Goetzmann-Rouwenhorst pairs rule on CFD spreads, days horizon. Parameters fixed before the test, no sweep:
s=log(A)+sgn*log(B) on daily closes (last M1 close before 22:00 data clock), z=(s-mean60)/sd60 (past only, shifted),
enter short-spread z>=2, long-spread z<=-2, exit z crossing 0, time exit 20 days, stop |z|>=4 (then flat until z back
inside 2). Exposure per unit: 10%/yr vol of the spread via 60d sd of spread changes, cap 3. Costs: full spread per leg
(fraction of price) split half per side on each change, plus swap 1bp/day per leg on held notional (both legs, cm scaled).
Signal at close t, position earns the change of s from t to t+1.
Items: paper_gatev_ratio_xau_xag (XAU/XAG), _fx_pairs (EUR/GBP, AUD/NZD, EUR/CHF), _nsx_spx (NSX/SPX, GRX/SPX).
Markets file = all 6 spreads with identical parameters. Book per item = equal weight of its spreads."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'XAUUSD': 3.0e-4, 'XAGUSD': 8.0e-4, 'EURUSD': 0.4e-4, 'GBPUSD': 0.8e-4, 'AUDUSD': 0.8e-4,
       'NZDUSD': 1.5e-4, 'USDCHF': 1.0e-4, 'NSXUSD': 1.5e-4, 'SPXUSD': 1.5e-4, 'GRXEUR': 1.5e-4}
SWAP = 1.0e-4
PAIRS = {'XAU_XAG': ('XAUUSD', 'XAGUSD', -1), 'EUR_GBP': ('EURUSD', 'GBPUSD', -1),
         'AUD_NZD': ('AUDUSD', 'NZDUSD', -1), 'EUR_CHF': ('EURUSD', 'USDCHF', 1),
         'NSX_SPX': ('NSXUSD', 'SPXUSD', -1), 'GRX_SPX': ('GRXEUR', 'SPXUSD', -1)}
ITEMS = {'paper_gatev_ratio_xau_xag': ['XAU_XAG'], 'paper_gatev_ratio_fx_pairs': ['EUR_GBP', 'AUD_NZD', 'EUR_CHF'],
         'paper_gatev_ratio_nsx_spx': ['NSX_SPX', 'GRX_SPX']}
W, ZIN, ZSTOP, MAXD = 60, 2.0, 4.0, 20


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close'])
    d.index = pd.to_datetime(d.time, unit='s')
    d = d[(d.index.hour < 22)]
    c = d.close.groupby(d.index.normalize()).last()
    c = c[c.index.dayofweek < 5]
    return holdout.drop(c)


def run(a, b, sg, cm):
    A, B = daily(a), daily(b)
    df = pd.concat([A, B], axis=1, keys=['a', 'b']).dropna()
    s = np.log(df.a) + sg * np.log(df.b)
    z = ((s - s.rolling(W).mean()) / s.rolling(W).std()).shift(0)  # uses s up to t, known at close t
    ds = s.diff()
    sd = ds.rolling(W).std().shift(1)
    expo = (0.10 / (sd * np.sqrt(252))).clip(upper=3.0)
    cost_side = (SPR[a] + SPR[b]) / 2 * cm
    pos = np.zeros(len(s))
    days = 0
    blocked = False
    zv = z.values
    for i in range(W + 1, len(s) - 1):
        p = pos[i - 1]
        zi = zv[i]
        if not np.isfinite(zi):
            continue
        if blocked and abs(zi) < ZIN:
            blocked = False
        if p != 0:
            days += 1
            if abs(zi) >= ZSTOP:
                p = 0
                blocked = True
            elif (p == 1 and zi >= 0) or (p == -1 and zi <= 0) or days >= MAXD:
                p = 0
        if p == 0 and not blocked:
            if zi >= ZIN:
                p, days = -1, 0
            elif zi <= -ZIN:
                p, days = 1, 0
        pos[i] = p
    # position decided at close i earns ds[i+1]
    P = pd.Series(pos, index=s.index)
    e = expo.shift(0).fillna(0)
    gross = P.shift(1).fillna(0) * ds.fillna(0) * e.shift(1).fillna(0)
    trade = P.diff().abs().fillna(0) * e
    cost = trade * cost_side + P.shift(1).abs().fillna(0) * e.shift(1).fillna(0) * 2 * SWAP / 1.0 * cm * 0 \
        + P.shift(1).abs().fillna(0) * e.shift(1).fillna(0) * 2 * SWAP * cm
    r = gross - cost
    return r.loc['2010':], int((P.diff().abs() > 0).sum())


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    res = {1.0: {}, 1.5: {}, 2.0: {}}
    for k, (a, b, sg) in PAIRS.items():
        for cm in res:
            r, n = run(a, b, sg, cm)
            res[cm][k] = r
        x = res[1.0][k]
        print(k, x.index[0].date(), x.index[-1].date(), 'changes', n, 'SR', round(sharpe(x), 2),
              'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
              '1.5x', round(sharpe(res[1.5][k]), 2), '2x', round(sharpe(res[2.0][k]), 2), flush=True)
    R = {cm: pd.DataFrame(v).fillna(0) for cm, v in res.items()}
    for name, ks in ITEMS.items():
        b, bs = R[1.0][ks].mean(axis=1), R[1.5][ks].mean(axis=1)
        print(name, 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
              '1.5x', round(sharpe(bs), 2), '2x', round(sharpe(R[2.0][ks].mean(axis=1)), 2))
        for nm, ser in ((name, b), (name + '_stress', bs)):
            pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
                f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/paper_gatev_ratio_markets.csv', index=False)
    for name in ITEMS:
        mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
