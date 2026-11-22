"""Padysak-Vojtko: long crypto 21:00-23:00 UTC daily. Binance 1h, 2017-08..2025-09 (holdout dropped).
Cost per round trip (bp): spread/slippage 5 at 1x; swap -30%/yr percent = 8.2bp/day if held over the broker rollover
(modelled as always paid: pessimistic, the rollover falls 21:00/22:00 UTC). Report with and without swap."""
import sys, os
sys.path.insert(0, 'tools')
import pandas as pd, numpy as np
import holdout

def load(sym):
    d = pd.read_csv(f'marketdata/crypto/{sym}_1h.csv')
    d['t'] = pd.to_datetime(d.ts_utc, unit='s')
    return d.set_index('t')

def sharpe(r):
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0

out = {}
for sym in ['BTCUSDT', 'ETHUSDT', 'LTCUSDT']:
    d = load(sym)
    # bar stamped 21:00 covers 21-22; long 21:00->23:00 = open of 21:00 bar to close of 22:00 bar
    o = d.open; c = d.close
    h = d.index.hour
    ent = o[h == 21]; ent.index = ent.index.normalize()
    ex = c[h == 22]; ex.index = ex.index.normalize()
    g = (ex / ent - 1).dropna()
    g.index.name = 'day'
    res = {}
    for name, spread, swap in [('1x_noswap', 5, 0), ('1x_swap', 5, 8.2), ('1.5x_swap', 7.5, 12.3), ('2x_swap', 10, 16.4), ('1.5x_noswap', 7.5, 0)]:
        r = g - (spread + swap) / 1e4
        res[name] = r
    out[sym] = res
    gg = g
    print(sym, 'n', len(g), 'gross bp/day', round(g.mean() * 1e4, 2), 'gross SR', round(sharpe(g), 2),
          'h1(<2022)', round(sharpe(g[g.index < '2022-01-01']), 2), 'h2', round(sharpe(g[g.index >= '2022-01-01']), 2),
          'gross<=2022-02', round(g[g.index <= '2022-02-28'].mean() * 1e4, 2), '>2022-02', round(g[g.index > '2022-02-28'].mean() * 1e4, 2))
    for k, r in res.items():
        print('  ', k, 'mean bp', round(r.mean() * 1e4, 2), 'SR', round(sharpe(r), 2),
              'h1', round(sharpe(r[r.index < '2022-01-01']), 2), 'h2', round(sharpe(r[r.index >= '2022-01-01']), 2))

# write candidate (BTC, 1x with swap) and stress
b = out['BTCUSDT']
# generous version sent to the gates: swap left out (data ends 2025-10-01, before the holdout)
for nm, key in [('btc_hour_2123', '1x_noswap'), ('btc_hour_2123_stress', '1.5x_noswap')]:
    r = b[key].rename('r').reset_index()
    r['day'] = r['day'].dt.strftime('%Y-%m-%d')
    r.to_csv(f'marketdata/candidates/{nm}.csv', index=False)
m = pd.DataFrame({s: out[s]['1x_noswap'] for s in out}).dropna()
m.index = m.index.strftime('%Y-%m-%d')
m.reset_index().to_csv('marketdata/candidates/btc_hour_2123_markets.csv', index=False)
