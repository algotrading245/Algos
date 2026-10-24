"""Safari & Schmidhuber (2025, arXiv 2501.16772) trend strength with cubic reversion.
R = (r - mu)/sigma (past-only 250d, shifted 1). phi_T = sum_n w_T(n) R(t-n), w=M*n*exp(-2n/T), sum w^2=1,
lags truncated at 1000 and renormalised, clipped +/-2.5, T=2^k k=1..10; phi_bar = mean. Signal b*phi+c*phi^3,
b=1.29 c=-0.62 (published, not refitted), clipped +/-1, scaled to 10%/yr by trailing 60d vol, earned from t+1.
Also extreme-only: -sign(phi) when |phi|>1.44. Costs: full spread/2 per turnover, swap markup 3%/yr.
Outputs marketdata/candidates/safari_cubic{,_stress,_markets}.csv"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

M = 'marketdata/histdata/'
SPR = {'XAUUSD': 2.5e-4, 'EURUSD': 1e-4, 'USDJPY': 1.2e-4, 'GBPUSD': 1.5e-4, 'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4,
       'AUDCAD': 3e-4}
MARKUP = 0.03
B, C = 1.29, -0.62
LAGS = 1000


def daily(sym):
    d = pd.read_csv(M + f'{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(d.time, unit='s') - pd.Timedelta(hours=21)
    s = d.groupby(t.dt.normalize())['close'].last()
    return s[s.index.dayofweek < 5]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else float('nan')


def phibar(ret):
    lr = np.log1p(ret)
    mu = lr.rolling(250).mean().shift(1)
    sd = lr.rolling(250).std().shift(1)
    R = ((lr - mu) / sd).fillna(0.0).values
    n = np.arange(1, LAGS + 1)
    acc = np.zeros(len(R))
    for k in range(1, 11):
        T = 2 ** k
        w = n * np.exp(-2 * n / T)
        w = w / np.sqrt((w ** 2).sum())
        # phi(t) = sum_n w(n) R(t-n)
        conv = np.convolve(R, np.concatenate([[0.0], w]))[:len(R)]
        acc += np.clip(conv, -2.5, 2.5)
    out = pd.Series(acc / 10, index=ret.index)
    out[:500] = np.nan
    return out


def build(px, mode='full', cm=1.0):
    out = {}
    for p in px:
        ret = px[p].pct_change()
        phi = phibar(ret)
        if mode == 'full':
            sig = (B * phi + C * phi ** 3).clip(-1, 1)
        elif mode == 'extreme':
            sig = -np.sign(phi) * (phi.abs() > 1.44)
        else:  # weak-trend side only
            sig = (B * phi) .clip(-1, 1) * (phi.abs() <= 1.44)
        sd = ret.rolling(60).std().shift(1)
        vol = sd * np.sqrt(252)
        expo = (sig * (0.10 / vol).clip(upper=3.0)).shift(1)
        r = expo * ret - expo.diff().abs() * SPR[p] * cm / 2 - expo.abs() * MARKUP * cm / 252
        out[p] = r
    return pd.DataFrame(out).dropna()


def rep(tag, r, cols):
    b = r[cols].mean(axis=1)
    print(tag, 'SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
          'ann', round(b.mean() * 252, 4))
    return b


def main():
    px = pd.concat({s: daily(s) for s in SPR}, axis=1)
    px = holdout.drop(px)
    px = px.ffill(limit=3)
    print('days', px.index[0].date(), px.index[-1].date(), len(px))
    cols = list(SPR)
    res = {}
    for mode in ('full', 'extreme', 'weak'):
        for cm in (1.0, 1.5, 2.0):
            r = build(px.dropna(how='all'), mode, cm)
            res[(mode, cm)] = r
            rep(f'{mode} {cm}x', r, cols)
        r = res[(mode, 1.0)]
        for p in cols:
            x = r[p]
            print('    ', p, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2))
    r, s = res[('full', 1.0)], res[('full', 1.5)]
    b, bs = r[cols].mean(axis=1), s[cols].mean(axis=1)
    for name, ser in (('safari_cubic', b), ('safari_cubic_stress', bs)):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{name}.csv', index=False)
    mk = r.copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv('marketdata/candidates/safari_cubic_markets.csv', index=False)


if __name__ == '__main__':
    main()
