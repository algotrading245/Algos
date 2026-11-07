"""Crabel NR7 opening-range breakout (MQL5 CodeBase 78259). Fixed rule, no sweep (k=0.3 stated before test).
Session open 08:00 (histdata clock), only if yesterday's D1 range is the narrowest of last 7 days (NR7),
buy stop at open+k*ATR14(D1), sell stop at open-k*ATR, stop = opposite level, close 13h after open, one fill.
Day = calendar day of the data clock. Markets XAUUSD, NSXUSD, SPXUSD, GRXEUR. Book = XAU+NSX+SPX equal weight of
vol-scaled returns? No: each trade return = pnl / open price, scaled to 10%/yr vol via trailing 60d daily-return std.
Cost: full spread SPR (fraction of price) per round trip + stop-slip none. Costs at cm 1, 1.5, 2."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'XAUUSD': 3.0e-4, 'NSXUSD': 1.5e-4, 'SPXUSD': 1.5e-4, 'GRXEUR': 1.5e-4}
K = 0.3
OPEN_H = 8
HOLD_H = 13


def load(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'open', 'high', 'low', 'close'])
    d.index = pd.to_datetime(d.time, unit='s')
    return d.drop(columns='time')


def trades(sym, d):
    day = d.index.normalize()
    g = d.groupby(day)
    D = pd.DataFrame({'h': g['high'].max(), 'l': g['low'].min(), 'c': g['close'].last()})
    D = D[D.index.dayofweek < 5]
    rng = D.h - D.l
    nr7 = rng == rng.rolling(7).min()
    atr = rng.rolling(14).mean()
    # D1 true range approx by range
    sig_days = D.index[(nr7.shift(1).fillna(False)) & atr.shift(1).notna()]
    ret_d = D.c.pct_change()
    sd = ret_d.rolling(60).std().shift(1)
    out = {}
    nsig = 0
    for t in sig_days:
        a = atr.shift(1)[t]
        st = t + pd.Timedelta(hours=OPEN_H)
        en = st + pd.Timedelta(hours=HOLD_H)
        w = d.loc[st:en]
        if len(w) < 60 or not np.isfinite(sd[t]):
            continue
        o = w.open.iloc[0]
        up, dn = o + K * a, o - K * a
        side = 0
        px = None
        for i in range(len(w)):
            hi, lo = w.high.iloc[i], w.low.iloc[i]
            if hi >= up and lo <= dn:
                side = 0
                px = None
                break  # ambiguous bar, skip
            if hi >= up:
                side, entry, stop = 1, up, dn
                break
            if lo <= dn:
                side, entry, stop = -1, dn, up
                break
        if side == 0:
            continue
        rest = w.iloc[i + 1:]
        exitp = rest.close.iloc[-1] if len(rest) else entry
        for j in range(len(rest)):
            if side == 1 and rest.low.iloc[j] <= stop:
                exitp = stop
                break
            if side == -1 and rest.high.iloc[j] >= stop:
                exitp = stop
                break
        gross = side * (exitp - entry) / entry
        expo = min(0.10 / (sd[t] * np.sqrt(252)), 3.0)
        out[t] = (gross * expo, expo)
        nsig += 1
    return out, nsig, D


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    res = {1.0: {}, 1.5: {}, 2.0: {}}
    nn = {}
    for s in SPR:
        d = load(s)
        d = holdout.drop(d) if 'time' not in d.columns else d
        tr, n, D = trades(s, d)
        nn[s] = n
        idx = D.index
        for cm in res:
            r = pd.Series(0.0, index=idx)
            for t, (g, e) in tr.items():
                r[t] = g - e * SPR[s] * cm
            res[cm][s] = holdout.drop(r)
        x = res[1.0][s]
        print(s, x.index[0].date(), x.index[-1].date(), 'trades', n, 'SR', round(sharpe(x), 2),
              'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
              '1.5x', round(sharpe(res[1.5][s]), 2), '2x', round(sharpe(res[2.0][s]), 2), flush=True)
    R = {cm: pd.DataFrame(v).fillna(0) for cm, v in res.items()}
    for cm in R:
        R[cm] = R[cm].loc['2010':]
    book = [s for s in ('XAUUSD',) if s in R[1.0]]
    b, bs = R[1.0][book].mean(axis=1), R[1.5][book].mean(axis=1)
    print('gold-only', 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          '1.5x', round(sharpe(bs), 2))
    ball = R[1.0].mean(axis=1)
    bsall = R[1.5].mean(axis=1)
    print('all4', 'SR', round(sharpe(ball), 2), 'h1', round(sharpe(ball[:'2017']), 2), 'h2', round(sharpe(ball['2018':]), 2),
          '1.5x', round(sharpe(bsall), 2))
    name = 'prebuilt_crabel_nr7_orb_gold'
    for nm, ser in ((name, ball), (name + '_stress', bsall)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
