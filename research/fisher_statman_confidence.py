"""Fisher & Statman consumer-confidence contrarian monthly hold on US100 (control US500).
UMCSENT (FRED, value of month m is final at end of m) -> 1-month change d_m. At the close of the first trading day of
m+1: change in top tercile of the past 60 changes (excluding current) -> short for the month, bottom tercile -> long,
else flat. Earned from the next day to the last trading day of the month. Fixed rules, no sweep.
Exposure 1.0 x notional (no vol scaling). Cost: spread/2 = 0.75bp per side on 1.5bp full + swap markup 3%/yr on |expo|.
Outputs marketdata/candidates/fisher_statman_confidence{,_stress,_markets}.csv"""
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


def positions(px_index, flip=1.0):
    u = pd.read_csv('marketdata/fred/UMCSENT.csv', parse_dates=['observation_date']).dropna()
    u = u.set_index(u.observation_date.dt.to_period('M'))['UMCSENT']
    d = u.diff()
    hi = d.shift(1).rolling(60).quantile(2 / 3)
    lo = d.shift(1).rolling(60).quantile(1 / 3)
    sig = pd.Series(0.0, index=d.index)
    sig[d > hi] = -1.0
    sig[d < lo] = 1.0
    sig = sig * flip
    pos = pd.Series(0.0, index=px_index)
    per = px_index.to_period('M')
    for m in sorted(set(per)):
        prev = m - 1
        if prev not in sig.index or sig[prev] == 0:
            continue
        days = px_index[per == m]
        # entry at close of first day, earn from day 2 .. last day of month (position held on day i earns ret i)
        pos.loc[days[1:]] = sig[prev]
    return pos


def build(px, cm=1.0, flip=1.0):
    ret = px.pct_change()
    pos = positions(px.index, flip)
    # position is applied to same-day return (set for days 2..end); entry at previous close
    r = pos * ret - pos.diff().abs() * SPR * cm / 2 - pos.abs() * MARKUP * cm / 252
    return r.dropna()


def main():
    px = {s: holdout.drop(daily(s)) for s in ('NSXUSD', 'SPXUSD')}
    print('days', px['NSXUSD'].index[0].date(), px['NSXUSD'].index[-1].date())
    for tag, cm, fl in (('paper', 1.0, 1), ('1.5x', 1.5, 1), ('2x', 2.0, 1), ('flip-diag', 1.0, -1)):
        for s in px:
            r = build(px[s], cm, fl)
            print(tag, s, 'SR', round(sharpe(r), 2), 'h1', round(sharpe(r[:'2017']), 2), 'h2', round(sharpe(r['2018':]), 2),
                  'ann', round(r.mean() * 252, 4), 'n_days_in', int((r != 0).sum()))
    r = build(px['NSXUSD'])
    rs = build(px['NSXUSD'], 1.5)
    for name, ser in (('fisher_statman_confidence', r), ('fisher_statman_confidence_stress', rs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = pd.DataFrame({s: build(px[s]) for s in px}).dropna()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/fisher_statman_confidence_markets.csv', index=False)


if __name__ == '__main__':
    main()
