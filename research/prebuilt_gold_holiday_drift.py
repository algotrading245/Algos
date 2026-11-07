"""Gold holiday drift (Quantpedia/Dujava 2025): long at close D-2, out at close D+2 around Christmas, Eid al-Fitr,
Diwali, Lunar New Year. D0 = first trading day on/after the date; held returns of D0-1..D0+2. Spot XAUUSD from
Dukascopy M1 (UTC day close). Cost: 3e-4 round trip (gold spread, 1x) + 0.7e-4 per held night swap; 1.5x, 2x scale both.
Scaled to 10%/yr vol by trailing 60d daily std (past only). Pre-declared variant B: D-2..D+2 (extra day), counted."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

XMAS = [f'{y}-12-25' for y in range(2003, 2026)]
LNY = ['2004-01-22', '2005-02-09', '2006-01-29', '2007-02-18', '2008-02-07', '2009-01-26', '2010-02-14', '2011-02-03',
       '2012-01-23', '2013-02-10', '2014-01-31', '2015-02-19', '2016-02-08', '2017-01-28', '2018-02-16', '2019-02-05',
       '2020-01-25', '2021-02-12', '2022-02-01', '2023-01-22', '2024-02-10', '2025-01-29']
DIW = ['2003-10-25', '2004-11-12', '2005-11-01', '2006-10-21', '2007-11-09', '2008-10-28', '2009-10-17', '2010-11-05',
       '2011-10-26', '2012-11-13', '2013-11-03', '2014-10-23', '2015-11-11', '2016-10-30', '2017-10-19', '2018-11-07',
       '2019-10-27', '2020-11-14', '2021-11-04', '2022-10-24', '2023-11-12', '2024-11-01', '2025-10-20']
EID = ['2003-11-26', '2004-11-14', '2005-11-03', '2006-10-24', '2007-10-13', '2008-10-01', '2009-09-20', '2010-09-10',
       '2011-08-30', '2012-08-19', '2013-08-08', '2014-07-28', '2015-07-17', '2016-07-06', '2017-06-25', '2018-06-15',
       '2019-06-04', '2020-05-24', '2021-05-13', '2022-05-02', '2023-04-21', '2024-04-10', '2025-03-31']
EV = {'xmas': XMAS, 'lny': LNY, 'diwali': DIW, 'eid': EID}
SPR, SWAP = 3.0e-4, 0.7e-4

d = pd.read_csv('marketdata/dukascopy/XAUUSD_M1.csv.gz', usecols=['time', 'close'])
d.index = pd.to_datetime(d.time, unit='s')
c = d.close.groupby(d.index.normalize()).last()
c = c[c.index.dayofweek < 5]
c = holdout.drop(c)
ret = c.pct_change().dropna()
sd = ret.rolling(60).std().shift(1)
scale = (0.10 / np.sqrt(252)) / sd


def build(lo, hi, cm, evs):
    pos = pd.Series(0.0, index=ret.index)
    ntr = 0
    for name in evs:
        for ds in EV[name]:
            t = pd.Timestamp(ds)
            i = ret.index.searchsorted(t)
            if i + hi >= len(ret) or i + lo < 0:
                continue
            pos.iloc[i + lo:i + hi + 1] = 1.0
            ntr += 1
    gross = pos * ret
    ent = (pos.diff().fillna(0) > 0).astype(float)
    cost = ent * SPR * cm + pos * SWAP * cm
    r = ((gross - cost) * scale).dropna()
    return r, ntr


def sh(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan


if __name__ == '__main__':
    for lab, (lo, hi) in {'A D-1..D+2': (-1, 2), 'B D-2..D+2': (-2, 2)}.items():
        for evs in (list(EV), ['xmas'], ['lny'], ['diwali'], ['eid']):
            r, n = build(lo, hi, 1.0, evs)
            a, b = r[r.index < '2018-01-01'], r[r.index >= '2018-01-01']
            # per-event-day mean (only in-window days) for readability
            print(lab, evs if len(evs) < 4 else 'ALL', 'n', n, 'sh all %.2f  <2018 %.2f  2018+ %.2f' % (sh(r), sh(a), sh(b)))
    r1, n = build(-1, 2, 1.0, list(EV))
    r15, _ = build(-1, 2, 1.5, list(EV))
    r2, _ = build(-1, 2, 2.0, list(EV))
    print('A all cost sharpe 1x/1.5x/2x', sh(r1), sh(r15), sh(r2))
    print('gold buy-hold sharpe <2018, 2018+', sh(ret[ret.index < '2018']), sh(ret[ret.index >= '2018']))
    r1.rename('r').rename_axis('day').to_csv('marketdata/candidates/prebuilt_gold_holiday_drift.csv', date_format='%Y-%m-%d')
    r15.rename('r').rename_axis('day').to_csv('marketdata/candidates/prebuilt_gold_holiday_drift_stress.csv', date_format='%Y-%m-%d')
