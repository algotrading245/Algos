"""Currency value (Menkhoff, Sarno, Schmeling, Schrimpf 2017), queue item paper_fx_value_rer_g10.
q = log CPI_US - log CPI_for - log s (s = USD per foreign unit); x = 5y change of q (CPI lagged 2 months).
Quarter-end: weight_j ~ (x_j - mean x) (long cheap = high x), vol-scaled to equal risk per currency, held a quarter.
Trade the 7 FTMO USD pairs from histdata; P&L = spot + (rate gap - markup 0.7%/yr) - half spread per exposure change.
No parameter sweep: 5y window and quarterly rebalance are the paper's. Stress 1.5x spread+markup, also 2x."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
F = M + 'fred/'
PAIRS = {'EUR': ('EURUSD', 1, 0.00012 / 1.1), 'GBP': ('GBPUSD', 1, 0.00015 / 1.3), 'AUD': ('AUDUSD', 1, 0.00015 / 0.7),
         'NZD': ('NZDUSD', 1, 0.00018 / 0.6), 'JPY': ('USDJPY', -1, 0.012 / 130), 'CAD': ('USDCAD', -1, 0.00018 / 1.3),
         'CHF': ('USDCHF', -1, 0.00016 / 0.9)}
RATES = {'USD': 'US', 'EUR': 'EZ', 'JPY': 'JP', 'GBP': 'GB', 'CAD': 'CA', 'AUD': 'AU', 'CHF': 'CH', 'NZD': 'NZ'}
CPI = {'USD': 'CPIAUCSL', 'EUR': 'CP0000EZ19M086NEST', 'GBP': 'GBRCPIALLMINMEI', 'CAD': 'CANCPIALLMINMEI',
       'CHF': 'CHECPIALLMINMEI', 'AUD': 'AUSCPIALLQINMEI', 'NZD': 'NZLCPIALLQINMEI', 'JPY': 'JPNCPIALLMINMEI'}
SPOT = {'EUR': ('DEXUSEU', False), 'GBP': ('DEXUSUK', False), 'AUD': ('DEXUSAL', False), 'NZD': ('DEXUSNZ', False),
        'JPY': ('DEXJPUS', True), 'CAD': ('DEXCAUS', True), 'CHF': ('DEXSZUS', True)}
ANN = {'JPY': 'FPCPITOTLZGJPN', 'NZD': 'FPCPITOTLZGNZL', 'AUD': 'FPCPITOTLZGAUS'}
MARKUP = 0.007


def rd(name):
    d = pd.read_csv(F + name + '.csv')
    d.columns = ['date', 'v']
    d['date'] = pd.to_datetime(d['date'])
    d['v'] = pd.to_numeric(d['v'], errors='coerce')
    return d.dropna().set_index('date')['v']


def cpi_monthly(c):
    s = rd(CPI[c])
    idx = pd.date_range(s.index[0], '2026-09-01', freq='MS')
    s = np.log(s).reindex(idx)
    if c in ('AUD', 'NZD'):  # quarterly: interpolate between quarter points
        last = s.last_valid_index()
        s = s.interpolate(limit_area='inside')
    last = s.last_valid_index()
    # extend beyond the end: annual inflation where the series is stale (JPY), else trailing 12m growth
    g12 = (s[last] - s[last - pd.DateOffset(months=12)]) / 12 if c not in ('JPY',) else None
    for t in s.index[s.index > last]:
        if c in ANN:
            a = rd(ANN[c])
            ys = a[a.index.year <= t.year]
            g = ys.iloc[-1] / 100 / 12 if len(ys) else 0
            if c in ('AUD', 'NZD') and g12 is not None:
                g = g12
        else:
            g = g12
        s[t] = s[t - pd.DateOffset(months=1)] + g
    return s


def daily(pair):
    d = pd.read_csv(M + f'histdata/{pair}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def main():
    px = pd.concat({c: daily(p[0]) for c, p in PAIRS.items()}, axis=1)
    px = holdout.drop(px).dropna()
    ret = pd.concat({c: px[c].pct_change() * PAIRS[c][1] for c in PAIRS}, axis=1).iloc[1:]
    days = ret.index
    # RER signal at month level
    cm = {c: cpi_monthly(c) for c in CPI}
    mi = pd.date_range('1995-01-01', '2025-10-01', freq='MS')
    q = {}
    for c in PAIRS:
        sp = rd(SPOT[c][0]).resample('MS').last()
        sp = 1 / sp if SPOT[c][1] else sp
        qc = (cm['USD'] - cm[c]).reindex(mi).shift(2) - np.log(sp.reindex(mi))  # CPI lagged 2 months
        q[c] = qc
    q = pd.DataFrame(q)
    x = q - q.shift(60)
    rates = pd.concat({c: rd('IR3TIB01' + RATES[c] + 'M156N') for c in list(PAIRS) + ['USD']}, axis=1).ffill()
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    w = pd.DataFrame(0.0, index=days, columns=list(PAIRS))
    qends = pd.Series(days, index=days).groupby(days.to_period('Q')).last()
    for p, d in qends.items():
        m0 = pd.Timestamp(d.year, d.month, 1)
        if m0 not in x.index or x.loc[m0].isna().any():
            continue
        xs = x.loc[m0]
        z = (xs - xs.mean()) / xs.std()
        nxt = (p + 1)
        sel = (days > d) & (days <= nxt.end_time.normalize())
        for c in PAIRS:
            w.loc[sel, c] = z[c]
    lev = (0.04 / vol).clip(upper=3.0)
    expo = (w * lev).where(w.abs().sum(axis=1) > 0)
    gap = pd.DataFrame({c: (rates[c] - rates['USD']).reindex(days, method='ffill').shift(1) / 100 for c in PAIRS})
    spr = pd.Series({c: PAIRS[c][2] for c in PAIRS})
    res = {}
    ok = expo.notna().all(axis=1) & rates.reindex(days, method='ffill').notna().all(axis=1)
    for cmult, tag in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
        carry = expo * gap / 260 - expo.abs() * MARKUP * cmult / 260
        pc = expo * ret + carry - expo.diff().abs().fillna(0) * spr * cmult / 2
        res[tag] = pc[ok].sum(axis=1)
        if tag == 'r':
            res['mk'] = pc[ok]
            res['spot'] = (expo * ret)[ok].sum(axis=1)
    r = res['r']
    print('start', r.index[0].date(), 'end', r.index[-1].date(), 'n', len(r))
    for k, nm in (('r', 'net 1x'), ('s', '1.5x'), ('d', '2x'), ('spot', 'spot only')):
        v = res[k]
        print(nm, 'SR', round(sharpe(v), 2), 'h1', round(sharpe(v[:'2017']), 2), 'h2', round(sharpe(v['2018':]), 2),
              'ann', round(v.mean() * 252, 4))
    for c in PAIRS:
        v = res['mk'][c]
        print('  ', c, 'SR', round(sharpe(v), 2), 'h1', round(sharpe(v[:'2017']), 2), 'h2', round(sharpe(v['2018':]), 2))
    print('signal last row', x.loc['2025-07-01'].round(3).to_dict())
    s = res['s']
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/fx_value_rer.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/fx_value_rer_stress.csv', index=False)
    mk = res['mk'].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/fx_value_rer_markets.csv', index=False)


if __name__ == '__main__':
    main()
