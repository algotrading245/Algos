"""Average pairwise industry correlation (Li et al. 2020 / Pollet-Wilson) monthly timing of US500 / US100.
AC_m = mean pairwise correlation of daily returns of the French 48 industries within month m (industries with a
full month of data only; -99.99 = missing). At the start of month t use AC_{t-2} (primary, as in the paper) :
AC above the median of its expanding history (all months before, min 60) -> flat, else long the index for the month.
Check variants (reported, counted in DSR N): lag 1, short instead of flat. No sweep.
Cost: 1.5bp full spread per change + 3%/yr swap markup on |expo|.
Outputs marketdata/candidates/avg_industry_correlation{,_stress,_markets}.csv"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = 1.5e-4
MARKUP = 0.03


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def monthly_ac():
    f = pd.read_csv('marketdata/french_48ind_daily.csv')
    f.index = pd.to_datetime(f.date.astype(str), format='%Y%m%d')
    f = f.drop(columns='date').replace(-99.99, np.nan).replace(-999, np.nan)
    out = {}
    for m, g in f.groupby(f.index.to_period('M')):
        g = g.dropna(axis=1)
        if g.shape[0] < 15 or g.shape[1] < 10:
            continue
        c = np.corrcoef(g.values.T)
        n = c.shape[0]
        out[m] = (c.sum() - n) / (n * (n - 1))
    return pd.Series(out)


def positions(px_index, ac, lag=2, short=False):
    med = ac.shift(1).expanding(60).median()  # history strictly before month m
    hi = ac > med
    sig = pd.Series(np.where(hi, -1.0 if short else 0.0, 1.0), index=ac.index)
    sig[med.isna()] = np.nan
    pos = pd.Series(0.0, index=px_index)
    per = px_index.to_period('M')
    for m in sorted(set(per)):
        src = m - lag
        if src not in sig.index or np.isnan(sig[src]):
            continue
        pos.loc[px_index[per == m]] = sig[src]
    return pos


def build(px, ac, cm=1.0, lag=2, short=False):
    ret = px.pct_change()
    pos = positions(px.index, ac, lag, short)
    r = pos * ret - pos.diff().abs() * SPR * cm / 2 - pos.abs() * MARKUP * cm / 252
    r = r.dropna()
    first = r.index[(pos.loc[r.index] != 0).argmax()] if (pos != 0).any() else r.index[0]
    return r[first:]


def rep(tag, s, r):
    print(tag, s, 'SR', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2), 'h2', round(sharpe(r['2018':]), 2),
          'ann', round(r.mean() * 252, 4), 'days_in', int((r != 0).sum()))


def main():
    ac = monthly_ac()
    print('AC months', ac.index[0], ac.index[-1], 'mean', round(ac.mean(), 3))
    px = {s: holdout.drop(daily(s)) for s in ('NSXUSD', 'SPXUSD')}
    print('days', px['NSXUSD'].index[0].date(), px['NSXUSD'].index[-1].date())
    for s in px:
        bh = px[s].pct_change().dropna()
        rep('buyhold', s, bh)
        for tag, cm, lag, sh in (('paper lag2', 1.0, 2, False), ('1.5x', 1.5, 2, False), ('2x', 2.0, 2, False),
                                 ('lag1', 1.0, 1, False), ('short lag2', 1.0, 2, True)):
            rep(tag, s, build(px[s], ac, cm, lag, sh))
    r = build(px['SPXUSD'], ac)
    rs = build(px['SPXUSD'], ac, 1.5)
    for name, ser in (('avg_industry_correlation', r), ('avg_industry_correlation_stress', rs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = pd.DataFrame({s: build(px[s], ac) for s in px}).dropna()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/avg_industry_correlation_markets.csv', index=False)


if __name__ == '__main__':
    main()
