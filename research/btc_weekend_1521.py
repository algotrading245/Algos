"""Padysak-Vojtko: long crypto 15:00-21:00 UTC on Saturdays, Sundays and NYSE holidays only. Binance 1h.
Pre-registered, one parameter set. Same-day close, no swap. Cost round trip 5bp at 1x (spread+slippage).
Also reports the 21:00-23:00 variant on those days and the weekday placebo (15-21 on normal weekdays)."""
import sys
sys.path.insert(0, 'tools')
import pandas as pd, numpy as np
import holdout
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr, USPresidentsDay,
                                    USMemorialDay, USLaborDay, USThanksgivingDay, GoodFriday, nearest_workday)

class NYSE(AbstractHolidayCalendar):
    rules = [Holiday('NY', month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
             GoodFriday, USMemorialDay, Holiday('J', month=6, day=19, start_date='2022-01-01', observance=nearest_workday),
             Holiday('I', month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
             Holiday('X', month=12, day=25, observance=nearest_workday)]

def load(sym):
    d = pd.read_csv(f'marketdata/crypto/{sym}_1h.csv')
    d['t'] = pd.to_datetime(d.ts_utc, unit='s')
    return d.set_index('t')

def sharpe(r):
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0

def seg(d, h0, h1):
    o = d.open[d.index.hour == h0]; o.index = o.index.normalize()
    c = d.close[d.index.hour == h1 - 1]; c.index = c.index.normalize()
    g = (c / o - 1).dropna(); g.index.name = 'day'
    return g

hol = NYSE().holidays('2017-01-01', '2025-12-31')
out = {}
for sym in ['BTCUSDT', 'ETHUSDT', 'LTCUSDT']:
    d = load(sym)
    g = seg(d, 15, 21)
    g2 = seg(d, 21, 23)
    wk = g.index.dayofweek >= 5
    hd = g.index.isin(hol)
    on = wk | hd
    print(sym, 'days', len(g), 'on-days', on.sum(), 'holiday weekdays', (hd & ~wk).sum())
    # strategy daily series: return on on-days, 0 otherwise (flat). Cost only on traded days.
    res = {}
    for name, c in [('1x', 5), ('1.5x', 7.5), ('2x', 10)]:
        r = (g - c / 1e4).where(on, 0.0)
        res[name] = r
    out[sym] = res
    gon = g[on]
    print('  gross bp/trade on-days', round(gon.mean() * 1e4, 1), 'weekday placebo', round(g[~on].mean() * 1e4, 1),
          'sat', round(g[g.index.dayofweek == 5].mean() * 1e4, 1), 'sun', round(g[g.index.dayofweek == 6].mean() * 1e4, 1),
          'hol', round(g[hd & ~wk].mean() * 1e4, 1))
    for k, r in res.items():
        print('  ', k, 'mean bp/day', round(r.mean() * 1e4, 2), 'SR', round(sharpe(r), 2),
              'h<2018', round(sharpe(r[r.index < '2018-01-01']), 2), 'h>=2018', round(sharpe(r[r.index >= '2018-01-01']), 2),
              'h<2022', round(sharpe(r[r.index < '2022-01-01']), 2), 'h>=2022', round(sharpe(r[r.index >= '2022-01-01']), 2))
    on2 = pd.Series(on, index=g.index).reindex(g2.index).fillna(False).astype(bool)
    print('  21-23 on-days gross bp', round(g2[on2].mean() * 1e4, 1), 'net1x SR', round(sharpe((g2 - 5e-4).where(on2, 0)), 2))

b = out['BTCUSDT']
for nm, key in [('btc_weekend_1521', '1x'), ('btc_weekend_1521_stress', '1.5x')]:
    r = b[key].rename('r').reset_index()
    r['day'] = r['day'].dt.strftime('%Y-%m-%d')
    r.to_csv(f'marketdata/candidates/{nm}.csv', index=False)
m = pd.DataFrame({s: out[s]['1x'] for s in out}).dropna()
m.index = m.index.strftime('%Y-%m-%d')
m.reset_index().to_csv('marketdata/candidates/btc_weekend_1521_markets.csv', index=False)
