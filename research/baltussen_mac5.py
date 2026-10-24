"""Baltussen, van Bekkum & Da (2019) MAC(5) index reversal (queue item paper_baltussen_mac5_index_reversal).
Daily 21:00-snapshot closes. s_t = 4r(t) + 3r(t-1) + 2r(t-2) + r(t-3) (past 4 closes, known at close t);
position = -clip(s / (sigma_60d_shifted * sqrt(30)), -1, 1), vol-scaled to 10%/yr (trailing 60d), earned from t+1.
Fixed, no sweep. Sign-only variant reported. Book = US500 + US100 equal weight; GER40 and Nikkei as belief markets.
Cost: full spread/2 per turnover (US 1.5bp, DAX 1.5bp, Nikkei 3bp full), swap markup 3%/yr on |exposure|.
Outputs marketdata/candidates/baltussen_mac5{,_stress,_markets}.csv"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4, 'GRXEUR': 1.5e-4, 'JPXJPY': 3e-4}
MARKUP = 0.03


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def build(px, sign_only=False, flip=1.0, cm=1.0):
    out = {}
    for p in px:
        ret = px[p].pct_change()
        s = 4 * ret + 3 * ret.shift(1) + 2 * ret.shift(2) + ret.shift(3)
        sd = ret.rolling(60).std().shift(1)
        z = s / (sd * np.sqrt(30))
        sig = -np.sign(z) if sign_only else -z.clip(-1, 1)
        vol = sd * np.sqrt(252)
        expo = (sig * flip * (0.10 / vol).clip(upper=3.0)).shift(1)
        r = expo * ret - expo.diff().abs() * SPR[p] * cm / 2 - expo.abs() * MARKUP * cm / 252
        out[p] = r
    return pd.DataFrame(out).dropna()


def rep(tag, r, cols):
    b = r[cols].mean(axis=1)
    print(tag, cols, 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          'ann', round(b.mean() * 252, 4))
    return b


def main():
    px = pd.concat({s: daily(s) for s in SPR}, axis=1).dropna()
    px = holdout.drop(px)
    print('days', px.index[0].date(), px.index[-1].date(), len(px))
    book = ['SPXUSD', 'NSXUSD']
    for tag, so, flip, cm in (('paper', 0, 1, 1.0), ('1.5x', 0, 1, 1.5), ('2x', 0, 1, 2.0),
                              ('signonly', 1, 1, 1.0), ('momentum-diag', 0, -1, 1.0)):
        r = build(px, bool(so), flip, cm)
        rep(tag, r, book)
        for p in r:
            x = r[p]
            print('    ', p, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    r = build(px)
    s = build(px, cm=1.5)
    b, bs = r[book].mean(axis=1), s[book].mean(axis=1)
    for name, ser in (('baltussen_mac5', b), ('baltussen_mac5_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = r.copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/baltussen_mac5_markets.csv', index=False)


if __name__ == '__main__':
    main()
