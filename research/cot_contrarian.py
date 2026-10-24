"""COT non-commercial extreme, contrarian, weekly (queue item paper_cot_extreme_contrarian_weekly).
Rule fixed in advance (from the queue item, no tuning): net = noncomm long - short over open interest; percentile of net
over the trailing 156 reports (own value included, known Friday). >=90th -> short the currency, <=10th -> long it; exit
when the percentile crosses 50 or after 6 reports. Report is Tuesday data released Friday: position starts after the
next Monday's close (we skip Monday's return, conservative vs Monday open). Sizing: 10%/yr vol target per market
(trailing 60d), equal-weight mean across markets. Cost: half spread per exposure change, stress 1.5x, 2x.
Markets: EUR GBP AUD (base), JPY CAD CHF (quote vs USD, inverted), GOLD."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
# name: (histdata file, sign, half spread fraction)
MK = {'EUR': ('EURUSD', 1, 0.00012 / 1.1), 'GBP': ('GBPUSD', 1, 0.00015 / 1.3), 'AUD': ('AUDUSD', 1, 0.00015 / 0.7),
      'JPY': ('USDJPY', -1, 0.012 / 130), 'CAD': ('USDCAD', -1, 0.00018 / 1.3), 'CHF': ('USDCHF', -1, 0.00016 / 0.9),
      'GOLD': ('XAUUSD', 1, 0.15 / 1500)}
W, HI, LO, MAXH = 156, 90, 10, 6


def daily(pair):
    d = pd.read_csv(M + f'histdata/{pair}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def signal(name, days):
    c = pd.read_csv(M + f'cot/{name}.csv')
    c['d'] = pd.to_datetime(c.report_date_as_yyyy_mm_dd).dt.normalize()
    c = c.sort_values('d').drop_duplicates('d').set_index('d')
    net = (c.noncomm_positions_long_all - c.noncomm_positions_short_all) / c.open_interest_all
    pct = net.rolling(W).apply(lambda x: (x[:-1] < x[-1]).mean() * 100 + (x[:-1] == x[-1]).mean() * 50, raw=True)
    pos = 0.0
    age = 0
    seq = {}
    for d, p in pct.dropna().items():
        if pos != 0:
            age += 1
            if (pos > 0 and p >= 50) or (pos < 0 and p <= 50) or age > MAXH:
                pos = 0.0
        if pos == 0:
            if p >= HI:
                pos, age = -1.0, 0
            elif p <= LO:
                pos, age = 1.0, 0
        seq[d + pd.Timedelta(days=3)] = pos  # Friday release
    s = pd.Series(seq)
    # Friday release -> effective after the following Monday close
    w =pd.Series(np.nan, index=days)
    for f, v in s.items():
        mon = f + pd.Timedelta(days=3)
        if mon in w.index:
            w.loc[mon] = v
    w = w.ffill().fillna(0.0)
    # position held from the day after Monday close: shift one day (Tuesday return onwards)
    return w.shift(1).fillna(0.0)


def main():
    px = pd.concat({c: daily(p[0]) for c, p in MK.items()}, axis=1)
    px = holdout.drop(px)
    ret = pd.concat({c: px[c].pct_change() * MK[c][1] for c in MK}, axis=1)
    days = px.index
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    out = {}
    sig = pd.concat({c: signal(c, days) for c in MK}, axis=1)
    lev = (0.10 / vol).clip(upper=4.0)
    expo = sig * lev
    spr = pd.Series({c: MK[c][2] for c in MK})
    res = {}
    for cm, tag in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
        pc = expo * ret - expo.diff().abs().fillna(0) * spr * cm / 2
        pc = pc.where(expo.notna() & ret.notna(), 0.0)
        res[tag] = pc
    start = '2001-01-01'
    for tag in ('r', 's', 'd'):
        pc = res[tag].loc[start:]
        r = pc.mean(axis=1)
        print(tag, 'SR all', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2), 'h2', round(sharpe(r['2018':]), 2),
              'ann', round(r.mean() * 252, 4))
        if tag == 'r':
            for c in MK:
                x = pc[c]
                print('   ', c, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
                      'inpos', round((sig[c].loc[start:] != 0).mean(), 2))
    r = res['r'].loc[start:].mean(axis=1)
    s = res['s'].loc[start:].mean(axis=1)
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/cot_contrarian.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/cot_contrarian_stress.csv', index=False)
    mk = res['r'].loc[start:].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/cot_contrarian_markets.csv', index=False)


if __name__ == '__main__':
    main()
