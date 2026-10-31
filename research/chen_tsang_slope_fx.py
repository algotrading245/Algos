"""Relative term-spread FX rule (queue item paper_chen_tsang_relative_slope_fx), fixed in advance, no sweep.
TS = 10y yield - 3m interbank rate per country (FRED monthly, lagged one month: at the last business day of month t
only the value dated month t-1 is used). TS_rel = TS_foreign - TS_US. Position for the next month: long foreign
currency vs USD if TS_rel < 0, short if > 0. EURUSD GBPUSD AUDUSD USDJPY(inverted) USDCAD(inverted). Vol-scaled to
10%/yr per pair (trailing 60d), P&L = spot + rate-difference carry on held side - 0.7%/yr markup - half-spread per
change. Diagnostics: flipped sign, correlation of position with carry sign (3m gap)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/'
# pair: (sign for currency-vs-USD, half-spread-ish fraction as in policy_gap, long code, short code)
PAIRS = {'EURUSD': (1, 0.00012 / 1.1, 'EZ'), 'GBPUSD': (1, 0.00015 / 1.3, 'GB'), 'AUDUSD': (1, 0.00012 / 0.7, 'AU'),
         'USDJPY': (-1, 0.012 / 130, 'JP'), 'USDCAD': (-1, 0.00015 / 1.3, 'CA')}
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


def build(flip, px, lt, st):
    days = px.index
    ret = px.pct_change()
    for p, (sg, _, _) in PAIRS.items():
        ret[p] = ret[p] * sg
    ts = {c: (lt[c] - st[c]) for c in lt}
    ts_rel, gap = {}, {}
    for p, (_, _, c) in PAIRS.items():
        # month-start-dated series; lagged: value of month m-1 available from first day of month m+? -> use shift(1) on month index
        a = (ts[c] - ts['US']).dropna()
        g = (st[c] - st['US']).dropna()
        # value dated month m is usable from the 1st of month m+1, so the month-end decision in t uses month t-1
        a.index = a.index + pd.offsets.MonthBegin(1)
        g.index = g.index + pd.offsets.MonthBegin(1)
        ts_rel[p] = a.reindex(days, method='ffill')
        gap[p] = g.reindex(days, method='ffill')
    ts_rel = pd.DataFrame(ts_rel)
    gap = pd.DataFrame(gap)
    sig = -np.sign(ts_rel) * (-1 if flip else 1)
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    me = pd.Series(days, index=days).groupby(days.to_period('M')).last()
    pos = pd.DataFrame(np.nan, index=days, columns=list(PAIRS))
    pos.loc[me.values] = sig.loc[me.values]
    pos = pos.ffill().shift(1)
    lev = (0.10 / vol).clip(upper=4.0)
    expo = pos * lev
    spr = pd.Series({p: PAIRS[p][1] for p in PAIRS})
    ok = expo.notna().all(axis=1) & gap.notna().all(axis=1)
    out = {}
    for cm, t in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
        carry = expo * (gap / 100) / 260 - expo.abs() * MARKUP * cm / 260
        pc = expo * ret + carry - expo.diff().abs().fillna(0) * spr * cm / 2
        pc = pc[ok]
        out[t] = pc.sum(axis=1) / len(PAIRS)
        if t == 'r':
            out['m'] = pc
    out['pos'] = pos[ok]
    out['gap'] = gap[ok]
    return out


def rep(tag, o):
    r, s, d = o['r'], o['s'], o['d']
    print(tag, r.index[0].date(), 'SR', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2), 'h2',
          round(sharpe(r['2018':]), 2), '1.5x', round(sharpe(s), 2), '2x', round(sharpe(d), 2), 'ann', round(r.mean() * 252, 4))
    for p in PAIRS:
        x = o['m'][p]
        print('   ', p, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))


def main():
    px = pd.concat({p: daily(p) for p in PAIRS}, axis=1)
    px = holdout.drop(px).dropna()
    lt = {'US': fred('IRLTLT01USM156N'), 'EZ': fred('IRLTLT01EZM156N'), 'GB': fred('IRLTLT01GBM156N'),
          'AU': fred('IRLTLT01AUM156N'), 'JP': fred('IRLTLT01JPM156N'), 'CA': fred('IRLTLT01CAM156N')}
    st = {'US': fred('IR3TIB01USM156N'), 'EZ': fred('IR3TIB01EZM156N'), 'GB': fred('IR3TIB01GBM156N'),
          'AU': fred('IR3TIB01AUM156N'), 'JP': fred('IR3TIB01JPM156N'), 'CA': fred('IR3TIB01CAM156N')}
    print('px', px.index[0].date(), px.index[-1].date())
    a = build(False, px, lt, st)
    rep('A rule', a)
    b = build(True, px, lt, st)
    rep('B flipped', b)
    # overlap with carry: sign agreement of position with sign of 3m gap (long foreign when gap>0)
    pos, gap = a['pos'], a['gap']
    agree = (np.sign(pos) == np.sign(gap)).mean().round(2).to_dict()
    cr = {p: round(np.corrcoef(np.sign(pos[p]), np.sign(gap[p]))[0, 1], 2) for p in PAIRS}
    print('sign agreement with carry', agree, 'corr', cr)
    r, s = a['r'], a['s']
    pd.DataFrame({'day': r.index.strftime('%Y-%m-%d'), 'r': r.values}).to_csv(M + 'candidates/chen_tsang_slope_fx.csv', index=False)
    pd.DataFrame({'day': s.index.strftime('%Y-%m-%d'), 'r': s.values}).to_csv(M + 'candidates/chen_tsang_slope_fx_stress.csv', index=False)
    mk = a['m'].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/chen_tsang_slope_fx_markets.csv', index=False)


if __name__ == '__main__':
    main()
