"""Port of the gold bell / Tokyo / midday legs (Hydra defaults) to XAGUSD, same rules, silver costs.
Bell: fade the 15-min move into 16:00 New York when |move| >= 1.5 x its 60-day average, hold 10 min.
Tokyo: sell at 9:55 Tokyo on gotobi days (day%5==0 or the Friday before), hold 90 min.
Midday: sell 11:30 -> 13:00 London.
Cost: round trip in bp; base 4 bp (what the scanners assume, silver spread not measured yet), stress 1.5x and 2x,
and a pessimistic 10 bp case. 3 legs + their sum = 4 trials. Holdout dropped through tools/holdout.py.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

m = pd.read_csv('marketdata/histdata/XAGUSD_M1.csv.gz', usecols=['time', 'close'])
t = pd.to_datetime(m['time'] + 60 - 7 * 3600, unit='s').dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT')
ok = t.notna().to_numpy()
t, c = t[ok].reset_index(drop=True), m['close'].to_numpy()[ok]
ser = pd.Series(c, index=pd.DatetimeIndex(t)).groupby(level=0).last()


def mat(zone):
    z = ser.copy()
    z.index = z.index.tz_convert(zone).tz_localize(None)
    day = z.index.normalize()
    days = pd.DatetimeIndex(np.unique(day))
    p = np.full((len(days), 1440), np.nan)
    p[days.get_indexer(day), z.index.hour * 60 + z.index.minute] = z.to_numpy()
    return days, p


def at(p, minute, stale=5):
    out = np.full(len(p), np.nan)
    for k in range(stale + 1):
        out = np.where(np.isnan(out), p[:, minute - k], out)
    return out


def cost(bp):
    return bp * 1e-4


legs = {}
# bell
d, p = mat('America/New_York')
a, b, e = at(p, 16 * 60), at(p, 15 * 60 + 45), at(p, 16 * 60 + 10)
mv = pd.Series(a / b - 1, index=d)
avg = mv.abs().rolling(60, min_periods=30).mean().shift(1)
sig = np.where(mv.abs() >= 1.5 * avg, -np.sign(mv), 0.0)
legs['bell'] = pd.Series(sig * (e / a - 1), index=d), pd.Series(np.abs(sig), index=d)
# tokyo
d, p = mat('Asia/Tokyo')
ret = pd.Series(at(p, 9 * 60 + 55 + 90) / at(p, 9 * 60 + 55) - 1, index=d)
dm, dw = d.day, d.dayofweek
g = (dm % 5 == 0) | ((dw == 4) & (((dm + 1) % 5 == 0) | ((dm + 2) % 5 == 0)))
on = pd.Series(g & (dw < 5), index=d).astype(float)
legs['tokyo'] = -ret * on, on
# midday (London summer/winter handled by zone)
d, p = mat('Europe/London')
ret = pd.Series(at(p, 13 * 60) / at(p, 11 * 60 + 30) - 1, index=d)
on = pd.Series((d.dayofweek < 5), index=d).astype(float)
legs['midday'] = -ret * on, on


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 30 and x.std() > 0 else float('nan')


def stream(names, bp):
    tot = None
    for n in names:
        g, o = legs[n]
        r = (g - o * cost(bp)).dropna()
        tot = r if tot is None else tot.add(r, fill_value=0)
    tot = tot[tot.index.dayofweek < 5]
    return tot


for n in list(legs) + ['all']:
    names = list(legs) if n == 'all' else [n]
    for bp in (4, 6, 8, 10):
        r = holdout.drop(stream(names, bp))
        print(f'{n:7s} {bp:3d}bp  all {sh(r):5.2f}  to2017 {sh(r[:"2017"]):5.2f}  2018+ {sh(r["2018":]):5.2f}  '
              f'mean/day {r.mean()*1e4:6.2f}bp  trades/yr {(sum(legs[k][1] for k in names).sum()/ (len(r)/252)):.0f}')
r = holdout.drop(stream(list(legs), 4))
s = holdout.drop(stream(list(legs), 6))
r.rename('r').to_csv('marketdata/candidates/silver_legs_port.csv', index_label='day')
s.rename('r').to_csv('marketdata/candidates/silver_legs_port_stress.csv', index_label='day')
print('trials 4; stress file = 1.5x of 4bp')
