"""Hau & Rey (2006) equity-flow FX (queue item paper_hau_rey_equity_fx_relative).
rel = 20d log return of foreign index minus 20d return of US500 (EURUSD: DAX-US500; USDJPY: Nikkei-US500;
EURJPY: DAX-Nikkei), z = rel / trailing-250d sd of rel (past only, shifted one day). Signal at the 21:00 snapshot close
of day t; z>+1 -> foreign currency depreciates (short EURUSD / long USDJPY / short EURJPY), z<-1 opposite.
Held 10 trading days (10 overlapping 1/10 tranches), return earned from day t+1. Fixed 20d/1sd/10d, no sweep.
Vol-scaled to 10%/yr per pair (trailing 60d), equal weight over 3 pairs. Cost: full spread/2 per turnover,
swap markup 0.7%/yr on |exposure|. Stress 1.5x. Contrarian sign reported as diagnostic only.
Outputs marketdata/candidates/hau_rey_fx{,_stress,_markets}.csv"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
# pair: (rel legs (a, b), sign of position when rel z>0, full spread in price units)
PAIRS = {'EURUSD': (('GRXEUR', 'SPXUSD'), -1, 1.2e-4),
         'USDJPY': (('JPXJPY', 'SPXUSD'), +1, 0.012),
         'EURJPY': (('GRXEUR', 'JPXJPY'), -1, 0.02)}
MARKUP = 0.007


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def build(px, flip=1.0, cm=1.0):
    out = {}
    for p, ((a, b), sgn, spr) in PAIRS.items():
        la, lb = np.log(px[a]), np.log(px[b])
        rel = (la - la.shift(20)) - (lb - lb.shift(20))
        z = rel / rel.rolling(250).std().shift(1)
        sig = pd.Series(0.0, index=px.index)
        sig[z > 1] = 1.0
        sig[z < -1] = -1.0
        sig[z.isna()] = np.nan
        pos = sig.rolling(10).mean() * sgn * flip      # tranche average, decided at close t
        ret = px[p].pct_change()
        vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
        expo = (pos * (0.10 / vol).clip(upper=3.0)).shift(1)   # earn from t+1
        fr = spr / px[p]
        r = expo * ret - expo.diff().abs() * fr * cm / 2 - expo.abs() * MARKUP * cm / 252
        out[p] = r
    return pd.DataFrame(out).dropna()


def main():
    syms = ['GRXEUR', 'JPXJPY', 'SPXUSD', 'EURUSD', 'USDJPY', 'EURJPY']
    px = pd.concat({s: daily(s) for s in syms}, axis=1).dropna()
    px = holdout.drop(px)
    print('days', px.index[0].date(), px.index[-1].date(), len(px))
    for tag, flip, cm in (('paper', 1, 1.0), ('1.5x', 1, 1.5), ('2x', 1, 2.0), ('contrarian', -1, 1.0)):
        r = build(px, flip, cm)
        b = r.mean(axis=1)
        print(tag, 'book SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
              'ann', round(b.mean() * 252, 4))
        for p in r:
            x = r[p]
            print('    ', p, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    r = build(px)
    s = build(px, cm=1.5)
    b, bs = r.mean(axis=1), s.mean(axis=1)
    for name, ser in (('hau_rey_fx', b), ('hau_rey_fx_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = r.copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/hau_rey_fx_markets.csv', index=False)


if __name__ == '__main__':
    main()
