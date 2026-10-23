"""G10 FX carry, monthly, net of broker swap markup (queue item paper_fx_carry_g10_monthly_swapadj; the NBER link
w14013 was not readable here - rule is the one written in the queue item, Lustig et al 2011 / Menkhoff et al 2012 style).
First trading day each month: rank USD,EUR,JPY,GBP,CAD,AUD,CHF,NZD by the 3m rate of the PREVIOUS month (FRED monthly
value dated month start, so we use the value dated one month earlier). Long top 2, short bottom 2 vs USD, vol-scaled
equal risk (trailing 60d vol, 10%/yr per leg /4 legs... = 5% per leg), hold the month. Variant B: flat when the mean
22d realised vol of the pairs is above its trailing-252d 80th percentile.
Cost: P&L = spot + (rate gap - markup 0.7%/yr per unit) ; spread half per exposure change. Stress: 1.5x spread+markup.
Outputs marketdata/candidates/fx_carry_g10{,_stress,_markets}.csv (headline variant A, fixed in advance)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
# currency -> (pair, sign: +1 if currency is base of pair vs USD), half-spread fraction
PAIRS = {'EUR': ('EURUSD', 1, 0.00012 / 1.1), 'GBP': ('GBPUSD', 1, 0.00015 / 1.3), 'AUD': ('AUDUSD', 1, 0.00015 / 0.7),
         'NZD': ('NZDUSD', 1, 0.00018 / 0.6), 'JPY': ('USDJPY', -1, 0.012 / 130), 'CAD': ('USDCAD', -1, 0.00018 / 1.3),
         'CHF': ('USDCHF', -1, 0.00016 / 0.9)}
RATES = {'USD': 'US', 'EUR': 'EZ', 'JPY': 'JP', 'GBP': 'GB', 'CAD': 'CA', 'AUD': 'AU', 'CHF': 'CH', 'NZ': 'NZ', 'NZD': 'NZ'}
MARKUP = 0.007


def daily(pair):
    d = pd.read_csv(M + f'histdata/{pair}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def rate(code):
    d = pd.read_csv(M + f'fred/IR3TIB01{code}M156N.csv')
    d.columns = ['date', 'v']
    d['date'] = pd.to_datetime(d['date'])
    d['v'] = pd.to_numeric(d['v'], errors='coerce')
    return d.dropna().set_index('date')['v']


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    px = pd.concat({c: daily(p[0]) for c, p in PAIRS.items()}, axis=1)
    px = holdout.drop(px).dropna()
    # currency-vs-USD return (positive = currency strengthens)
    ret = pd.concat({c: px[c].pct_change() * PAIRS[c][1] for c in PAIRS}, axis=1).iloc[1:]
    rates = pd.concat({c: rate(RATES[c]) for c in list(PAIRS) + ['USD']}, axis=1).ffill()
    print('rates start', rates.dropna().index[0].date(), 'px', px.index[0].date(), px.index[-1].date())
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    rv_mean = ret.rolling(22).std().mean(axis=1) * np.sqrt(252)
    rv_thr = rv_mean.rolling(252).quantile(0.8).shift(1)
    days = ret.index
    month = days.to_period('M')
    first = pd.Series(days, index=days).groupby(month).first()
    w = pd.DataFrame(0.0, index=days, columns=list(PAIRS))
    cur = None
    for m, d in first.items():
        rd = (m.to_timestamp() - pd.offsets.MonthBegin(1))  # previous month value
        if rd not in rates.index or rates.loc[rd].isna().any():
            continue
        r8 = rates.loc[rd]
        order = r8.sort_values()
        longs, shorts = list(order.index[-2:]), list(order.index[:2])
        cur = (longs, shorts, d)
        end = m.end_time.normalize()
        sel = (days > d) & (days <= end + pd.Timedelta(days=0))
        # position decided with first-day close, held from next day on to the month's last day
        for c in longs:
            if c != 'USD':
                w.loc[sel, c] += 1.0
        for c in shorts:
            if c != 'USD':
                w.loc[sel, c] -= 1.0
    res = {}
    for variant in ('A', 'B'):
        ww = w.copy()
        if variant == 'B':
            off = (rv_mean > rv_thr).reindex(days).fillna(False)
            ww[off] = 0.0
        lev = (0.05 / vol).clip(upper=3.0)
        expo = ww * lev
        gap = pd.DataFrame(index=days, columns=list(PAIRS), dtype=float)
        for c in PAIRS:
            gap[c] = (rates[c] - rates['USD']).reindex(days, method='ffill').shift(1) / 100  # rate known, lagged one day
        spr = pd.Series({c: PAIRS[c][2] for c in PAIRS})
        for cm, tag in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
            carry = expo * gap / 260 - expo.abs() * MARKUP * cm / 260
            rr = (expo * ret + carry - expo.diff().abs().fillna(0) * spr * cm / 2).sum(axis=1)
            res[(variant, tag)] = rr[expo.notna().all(axis=1) & (rates.reindex(days, method='ffill').notna().all(axis=1))]
            if tag == 'r':
                pc = (expo * ret - expo.diff().abs().fillna(0) * spr / 2 + carry)
                res[(variant, 'markets')] = pc.loc[res[(variant, 'r')].index]
    for v in ('A', 'B'):
        r, s, d = res[(v, 'r')], res[(v, 's')], res[(v, 'd')]
        r = r[r.index >= '2002-06-01']; s = s.loc[r.index]; d = d.loc[r.index]
        print(v, r.index[0].date(), 'SR all', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2),
              'h2', round(sharpe(r['2018':]), 2), '1.5x', round(sharpe(s), 2), '2x', round(sharpe(d), 2),
              'ann ret', round(r.mean() * 252, 4))
        for c in PAIRS:
            x = res[(v, 'markets')][c].loc[r.index]
            print('   ', c, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    r = res[('A', 'r')]; r = r[r.index >= '2002-06-01']
    s = res[('A', 'r')]
    s = res[('A', 's')].loc[r.index]
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/fx_carry_g10.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/fx_carry_g10_stress.csv', index=False)
    mk = res[('A', 'markets')].loc[r.index]
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/fx_carry_g10_markets.csv', index=False)


if __name__ == '__main__':
    main()
