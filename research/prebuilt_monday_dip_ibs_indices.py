"""Monday Dip (MQL5 CodeBase 78343): Monday D1 close < prior close AND IBS<=0.25 AND close < SMA180 -> long, exit Wed close.
Fixed rule, no sweep. Days on 21:00-snapshot boundary (as baltussen_mac5). Exposure vol-scaled to 10%/yr (trailing 60d).
Cost: spread (full, round trip = SPR) + 2.5bp/night swap x2 nights, times cm. Markets US500, US100, GER40, JPN225.
Book candidate = equal-weight US500+US100; others are belief markets."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4, 'GRXEUR': 1.5e-4, 'JPXJPY': 3e-4}
SWAP = 2.5e-4


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close', 'high', 'low'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    g = d.groupby(t.dt.normalize())
    o = pd.DataFrame({'c': g['close'].last(), 'h': g['high'].max(), 'l': g['low'].min()})
    return o[o.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def build(sym, df, cm=1.0):
    c = df.c
    ret = c.pct_change()
    ibs = (c - df.l) / (df.h - df.l)
    sig = (df.index.dayofweek == 0) & (c < c.shift(1)) & (ibs <= 0.25) & (c < c.rolling(180).mean())
    sig = pd.Series(sig, index=df.index)
    sd = ret.rolling(60).std().shift(0)
    expo_size = (0.10 / (sd * np.sqrt(252))).clip(upper=3.0)
    pos = pd.Series(0.0, index=df.index)
    cost = pd.Series(0.0, index=df.index)
    idx = np.where(sig.values)[0]
    for i in idx:
        if i + 2 >= len(df):
            continue
        e = expo_size.iloc[i]
        if not np.isfinite(e):
            continue
        pos.iloc[i + 1] = e
        pos.iloc[i + 2] = e
        cost.iloc[i + 1] += e * SPR[sym] * cm / 2 + e * SWAP * cm   # entry half spread + night
        cost.iloc[i + 2] += e * SPR[sym] * cm / 2 + e * SWAP * cm   # exit half spread + night
    r = pos * ret - cost
    return r, len(idx)


def main():
    px = {s: daily(s) for s in SPR}
    px = {s: holdout.drop(v) for s, v in px.items()}
    res, resS, ntr = {}, {}, {}
    for s, df in px.items():
        res[s], ntr[s] = build(s, df)
        resS[s], _ = build(s, df, 1.5)
        r2, _ = build(s, df, 2.0)
        x = res[s]
        print(s, df.index[0].date(), df.index[-1].date(), 'trades', ntr[s], 'SR', round(sharpe(x), 2),
              'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
              '1.5x', round(sharpe(resS[s]), 2), '2x', round(sharpe(r2), 2))
    R = pd.DataFrame(res).dropna()
    RS = pd.DataFrame(resS).dropna()
    book = ['SPXUSD', 'NSXUSD']
    b, bs = R[book].mean(axis=1), RS[book].mean(axis=1)
    print('book', 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          '1.5x', round(sharpe(bs), 2), 'ann', round(b.mean() * 252, 4))
    for name, ser in (('prebuilt_monday_dip_ibs_indices', b), ('prebuilt_monday_dip_ibs_indices_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = R.copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/prebuilt_monday_dip_ibs_indices_markets.csv', index=False)


if __name__ == '__main__':
    main()
