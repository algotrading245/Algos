"""Policy-rate gap change as FX trend signal (queue item paper_policy_gap_eurusd_weeks). Rule fixed in advance:
gap = foreign policy rate - USD rate (EUR: ECBDFR-DFF, GBP: IUDSOIA-DFF, JP: IR3TIB01JP monthly - DFF, sign for USDJPY
flipped). Signal = sign(gap_t - gap_{t-63 bus. days}), rates lagged 1 day. Monday-close decision, hold 1 week,
vol-scaled to 10%/yr per pair (trailing 60d). Variant 126d computed as second fixed setting (not the headline).
P&L = spot + carry on held side (rate diff) - markup 0.7%/yr - half-spread per change. Stress 1.5x."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
PAIRS = {'EURUSD': (1, 0.00012 / 1.1), 'GBPUSD': (1, 0.00015 / 1.3), 'USDJPY': (-1, 0.012 / 130)}
MARKUP = 0.007


def daily(pair):
    d = pd.read_csv(M + f'histdata/{pair}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def fred(name):
    d = pd.read_csv(M + f'fred/{name}.csv')
    d.columns = ['date', 'v']
    d['date'] = pd.to_datetime(d['date'])
    d['v'] = pd.to_numeric(d['v'], errors='coerce')
    return d.dropna().set_index('date')['v']


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def run(lookback, px, rates, tag):
    days = px.index
    ret = px.pct_change()
    for p, (sg, _) in PAIRS.items():
        ret[p] = ret[p] * sg  # currency-vs-USD (+ = foreign ccy up)
    cols = {'EURUSD': 'EUR', 'GBPUSD': 'GBP', 'USDJPY': 'JPY'}
    gap = pd.DataFrame({p: (rates[cols[p]] - rates['USD']).reindex(days, method='ffill').shift(1) for p in PAIRS})
    sig = np.sign(gap - gap.shift(lookback))
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    # Monday decision (first business day of week), position held from following day through next Monday close
    wk = days.to_period('W')
    first = pd.Series(days, index=days).groupby(wk).first()
    pos = pd.DataFrame(np.nan, index=days, columns=list(PAIRS))
    pos.loc[first.values] = sig.loc[first.values]
    pos = pos.ffill().shift(1)  # decision on close of first day, effective next day
    lev = (0.10 / vol).clip(upper=4.0)
    expo = pos * lev
    spr = pd.Series({p: PAIRS[p][1] for p in PAIRS})
    out = {}
    for cm, t in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
        carry = expo * (gap / 100) / 260 - expo.abs() * MARKUP * cm / 260
        pc = expo * ret + carry - expo.diff().abs().fillna(0) * spr * cm / 2
        ok = expo.notna().all(axis=1) & gap.notna().all(axis=1) & vol.notna().all(axis=1)
        pc = pc[ok]
        out[t] = pc.sum(axis=1) / 3 * 1.0
        if t == 'r':
            out['m'] = pc
    r, s, d = out['r'], out['s'], out['d']
    print(tag, lb_str(lookback), r.index[0].date(), 'SR', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2),
          'h2', round(sharpe(r['2018':]), 2), '1.5x', round(sharpe(s), 2), '2x', round(sharpe(d), 2),
          'ann', round(r.mean() * 252, 4))
    for p in PAIRS:
        x = out['m'][p]
        print('   ', p, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    return out


def lb_str(x):
    return f'lookback {x}'


def main():
    px = pd.concat({p: daily(p) for p in PAIRS}, axis=1)
    px = holdout.drop(px).dropna()
    rates = pd.concat({'USD': fred('DFF'), 'EUR': fred('ECBDFR'), 'GBP': fred('IUDSOIA'),
                       'JPY': fred('IR3TIB01JPM156N')}, axis=1)
    rates = rates.sort_index().ffill()
    print('px', px.index[0].date(), px.index[-1].date(), 'rates first valid', rates.dropna().index[0].date())
    a = run(63, px, rates, 'A')
    run(126, px, rates, 'B')
    r = a['r']; s = a['s']
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/policy_gap.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/policy_gap_stress.csv', index=False)
    mk = a['m'].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/policy_gap_markets.csv', index=False)


if __name__ == '__main__':
    main()
