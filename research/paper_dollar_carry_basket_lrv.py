"""Lustig-Roussanov-Verdelhan dollar carry (NBER w16427). Month start: AFD = mean(foreign 3m rate: EUR GBP JPY CAD AUD CHF NZD)
minus US 3m rate, rates lagged one month (FRED monthly value dated previous month start). AFD>0 -> long all 7 foreign vs USD,
else short all. Equal risk per pair (5%/yr vol target each, trailing 60d, cap 3), hold the month. Costs: half spread on
exposure change, swap = rate gap minus 0.7%/yr markup on |exposure| (1x; stress 1.5x spread+markup). No parameters tuned.
Outputs marketdata/candidates/paper_dollar_carry_basket_lrv{,_stress,_markets}.csv."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
sys.path.insert(0, 'research')
import holdout
from fx_carry_g10 import PAIRS, RATES, MARKUP, daily, rate, sharpe

M = 'marketdata/'


def main():
    px = holdout.drop(pd.concat({c: daily(p[0]) for c, p in PAIRS.items()}, axis=1)).dropna()
    ret = pd.concat({c: px[c].pct_change() * PAIRS[c][1] for c in PAIRS}, axis=1).iloc[1:]
    rates = pd.concat({c: rate(RATES[c]) for c in list(PAIRS) + ['USD']}, axis=1).ffill()
    vol = ret.rolling(60).std().shift(1) * np.sqrt(252)
    days = ret.index
    month = days.to_period('M')
    first = pd.Series(days, index=days).groupby(month).first()
    sig = pd.Series(0.0, index=days)
    for m, d in first.items():
        rd = m.to_timestamp() - pd.offsets.MonthBegin(1)
        if rd not in rates.index or rates.loc[rd].isna().any():
            continue
        r8 = rates.loc[rd]
        afd = r8[list(PAIRS)].mean() - r8['USD']
        sel = (days > d) & (days <= m.end_time.normalize())
        sig[sel] = 1.0 if afd > 0 else -1.0
    w = pd.DataFrame({c: sig for c in PAIRS})
    lev = (0.05 / vol).clip(upper=3.0)
    expo = w * lev
    gap = pd.DataFrame({c: (rates[c] - rates['USD']).reindex(days, method='ffill').shift(1) / 100 for c in PAIRS})
    spr = pd.Series({c: PAIRS[c][2] for c in PAIRS})
    ok = expo.notna().all(axis=1) & (sig != 0) & gap.notna().all(axis=1)
    res = {}
    for cm, tag in ((1.0, 'r'), (1.5, 's'), (2.0, 'd')):
        carry = expo * gap / 260 - expo.abs() * MARKUP * cm / 260
        pc = expo * ret + carry - expo.diff().abs().fillna(0) * spr * cm / 2
        res[tag] = pc[ok].sum(axis=1) / len(PAIRS)
        if tag == 'r':
            res['m'] = pc[ok]
            res['nocarry'] = (expo * ret - expo.diff().abs().fillna(0) * spr / 2)[ok].sum(axis=1) / len(PAIRS)
    r, s, d = res['r'], res['s'], res['d']
    print('start', r.index[0].date(), 'end', r.index[-1].date(), 'n', len(r))
    print('SR all', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2), 'h2', round(sharpe(r['2018':]), 2),
          '1.5x', round(sharpe(s), 2), 'h2@1.5x', round(sharpe(s['2018':]), 2), '2x', round(sharpe(d), 2),
          'ann', round(r.mean() * 252, 4), 'h2 spot-only SR', round(sharpe(res['nocarry']['2018':]), 2))
    for c in PAIRS:
        x = res['m'][c]
        print('  ', c, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    print('share long days', round((sig[ok] > 0).mean(), 2), 'h2 long share', round((sig[ok]['2018':] > 0).mean(), 2))
    for name, x in (('', r), ('_stress', s)):
        pd.DataFrame({'day': x.index.strftime('%Y-%m-%d'), 'r': x.values}).to_csv(
            M + f'candidates/paper_dollar_carry_basket_lrv{name}.csv', index=False)
    mk = res['m'].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(M + 'candidates/paper_dollar_carry_basket_lrv_markets.csv', index=False)


if __name__ == '__main__':
    main()
