"""Dual Thrust daily-range breakout (je-suis-tm/quant-trading), fixed rule, no sweep.
range = max(HH-LC, HC-LL) over the previous N=4 daily bars (calendar day of the data clock, past only).
Day open = first M1 bar at/after server 01:00 (after the 23:00-01:00 rollover, lesson 9); buy stop open+0.5*range,
sell stop open-0.5*range; reverse on the opposite touch; flat at the 22:00 close. A bar touching both levels at once
while flat is skipped. Markets: EURUSD, USDJPY, XAUUSD, SPXUSD, NSXUSD (identical parameters, belief = 3+ markets).
Costs: round-trip spread SPR as a fraction of price, half per fill (entry, reversal = 2 fills, exit); 1x/1.5x/2x.
Returns scaled to 10%/yr vol with trailing 60d std (cap 3x). Equal-weight book of the markets.
Holdout days dropped via tools/holdout.py. Run: python research/prebuilt_dual_thrust_fx_gold.py"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'EURUSD': 0.8e-4, 'USDJPY': 1.2e-4, 'XAUUSD': 3.0e-4, 'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4}
N, K1, K2 = 4, 0.5, 0.5
START_MIN, END_MIN = 60, 22 * 60
MAXOPEN = None  # minutes of day; None = no skip (original runs)


def load(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'open', 'high', 'low', 'close'])
    d.index = pd.to_datetime(d.time, unit='s')
    d = d.drop(columns='time')
    return d[d.index < holdout.START]


def sim(sym, d):
    day = d.index.normalize()
    g = d.groupby(day)
    D = pd.DataFrame({'h': g['high'].max(), 'l': g['low'].min(), 'c': g['close'].last()})
    D = D[D.index.dayofweek < 5]
    hh = D.h.rolling(N).max(); ll = D.l.rolling(N).min()
    hc = D.c.rolling(N).max(); lc = D.c.rolling(N).min()
    rng = np.maximum(hh - lc, hc - ll).shift(1)
    sd = D.c.pct_change().rolling(60).std().shift(1)
    mod = (d.index.hour * 60 + d.index.minute).to_numpy()
    sel = (mod >= START_MIN) & (mod < END_MIN) & (d.index.dayofweek < 5)
    ds = d[sel]
    gi = ds.groupby(ds.index.normalize())
    gross, fills = {}, {}
    for t, w in gi:
        if t not in rng.index or not np.isfinite(rng[t]) or not np.isfinite(sd[t]) or len(w) < 120:
            continue
        if MAXOPEN is not None and w.index[0].hour * 60 + w.index[0].minute > MAXOPEN:
            continue  # EA needs a bar by 01:15 (Legs.mqh:2497), else it skips the day
        o = w.open.iloc[0]
        up, dn = o + K1 * rng[t], o - K2 * rng[t]
        H, L, C = w.high.to_numpy(), w.low.to_numpy(), w.close.to_numpy()
        side, pos, pnl, nf, entry = 0, 0, 0.0, 0, 0.0
        while True:
            if side == 0:
                iu = np.flatnonzero(H[pos:] >= up); idn = np.flatnonzero(L[pos:] <= dn)
                iu = iu[0] + pos if len(iu) else 10**9
                idn = idn[0] + pos if len(idn) else 10**9
                if min(iu, idn) == 10**9 or iu == idn:
                    break
                if iu < idn:
                    side, entry, pos = 1, up, iu + 1
                else:
                    side, entry, pos = -1, dn, idn + 1
                nf += 1
            else:
                lvl = dn if side == 1 else up
                hit = np.flatnonzero(L[pos:] <= lvl) if side == 1 else np.flatnonzero(H[pos:] >= lvl)
                if len(hit) == 0:
                    pnl += side * (C[-1] - entry); nf += 1
                    break
                pnl += side * (lvl - entry); nf += 1
                side, entry, pos = -side, lvl, hit[0] + pos + 1
                nf += 1
                if pos >= len(H):
                    break
        if nf == 0:
            continue
        expo = min(0.10 / (sd[t] * np.sqrt(252)), 3.0)
        gross[t] = pnl / o * expo
        fills[t] = nf * 0.5 * expo
    return pd.Series(gross), pd.Series(fills), D.index


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    res = {1.0: {}, 1.5: {}, 2.0: {}}
    for s in SPR:
        gr, fl, idx = sim(s, load(s))
        for cm in res:
            r = (gr - fl * SPR[s] * cm).reindex(idx).fillna(0.0)
            res[cm][s] = holdout.drop(r)
        x = res[1.0][s]
        print(s, x.index[0].date(), x.index[-1].date(), 'tradedays', len(gr), 'SR', round(sharpe(x), 2),
              'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
              '1.5x', round(sharpe(res[1.5][s]), 2), '2x', round(sharpe(res[2.0][s]), 2),
              'gross', round(sharpe(holdout.drop(gr.reindex(idx).fillna(0))), 2), flush=True)
    R = {cm: pd.DataFrame(v).fillna(0).loc['2010':] for cm, v in res.items()}
    name = 'prebuilt_dual_thrust_fx_gold'
    for label, cols in (('all5', list(SPR)), ('fx_gold', ['EURUSD', 'USDJPY', 'XAUUSD'])):
        b, bs = R[1.0][cols].mean(axis=1), R[1.5][cols].mean(axis=1)
        print(label, 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
              '1.5x', round(sharpe(bs), 2), '2x', round(sharpe(R[2.0][cols].mean(axis=1)), 2))
        if label == 'fx_gold':
            for nm, ser in ((name, b), (name + '_stress', bs)):
                pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
                    f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
