"""Carver / qoppac range-position breakout forecast (blog 2016-05 'a simple breakout trading rule').

For N in 10..320: raw = 40 (p - mid)/(max - min) over N daily closes, EWMA span N/4, average of the variants,
capped +/-20.  Position = forecast/10 x (10% / ewm vol), equal weight over 7 markets, daily rebalance on closes
up to yesterday (shift 1).  Day = 17:00 New York to 17:00.  Cost: half round-trip spread per unit of change
(bp: XAU 1.5, XAG 2, WTI 2, SPX 1, USDJPY 0.7, EURUSD 0.5, AUDCAD 1.5; XAG/WTI assumed, not measured), plus 0.5 bp/day
swap on |position|.  Trials: set A (20-320, 5 lookbacks), set B (10-320, 6 lookbacks) = 2.  Holdout dropped.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

HALF = {'XAUUSD': 1.5, 'XAGUSD': 2.0, 'WTIUSD': 2.0, 'SPXUSD': 1.0, 'USDJPY': 0.7, 'EURUSD': 0.5, 'AUDCAD': 1.5}


def daily(sym):
    m = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(m['time'] + 60 - 7 * 3600 + 7 * 3600, unit='s')   # NY 17:00 roll: server+... ~ day boundary
    d = (t - pd.Timedelta(hours=0)).dt.floor('D')
    s = pd.Series(m['close'].to_numpy(), index=d).groupby(level=0).last()
    s = s[s.index.dayofweek < 5]
    return s


def forecast(p, lbs):
    f = []
    for n in lbs:
        mx, mn = p.rolling(n).max(), p.rolling(n).min()
        raw = 40 * (p - (mx + mn) / 2) / (mx - mn)
        f.append(raw.ewm(span=max(int(n / 4), 1)).mean())
    return (sum(f) / len(f)).clip(-20, 20)


def run(P, lbs, mult):
    R = P.pct_change(fill_method=None).clip(-0.2, 0.2)
    vol = R.ewm(com=30).std().shift(1) * np.sqrt(252)
    pos = pd.DataFrame({c: forecast(P[c].dropna(), lbs) for c in P}).reindex(P.index).shift(1) / 10 * 0.10 / vol
    pos = pos.clip(-3, 3).fillna(0) / P.shape[1]
    half = pd.Series(HALF)[P.columns] * 1e-4 * mult
    cost = pos.diff().abs().mul(half).sum(axis=1) + pos.abs().sum(axis=1) * 0.5e-4 * mult
    return ((pos * R.fillna(0)).sum(axis=1) - cost)


def sh(x):
    return x.mean() / x.std() * np.sqrt(252)


if __name__ == '__main__':
    P = pd.DataFrame({s: daily(s) for s in HALF}).sort_index()
    P = P[P.index.dayofweek < 5].ffill(limit=3)
    P = P.loc[P.index >= '2010-01-01']
    out = {}
    for name, lbs in (('A', (20, 40, 80, 160, 320)), ('B', (10, 20, 40, 80, 160, 320))):
        for mult in (1, 1.5, 2):
            r = holdout.drop(run(P, lbs, mult)).dropna()
            r = r.loc[r.index >= '2011-06-01']
            out[(name, mult)] = r
            print(name, mult, f'Sharpe {sh(r):+.2f} to2017 {sh(r[:"2017"]):+.2f} from2018 {sh(r["2018":]):+.2f} '
                  f'ann {r.mean()*252*100:+.2f}% vol {r.std()*np.sqrt(252)*100:.1f}%')
    for k in ('A', 'B'):
        pass
    import pickle
    pickle.dump(out, open('research/carver_out.pkl', 'wb'))
    for (n, m), r in out.items():
        pass
    # per-market sharpe for A at 1x
    R = P.pct_change(fill_method=None)
    for c in P:
        one = P[[c]]
        r = holdout.drop(run(one, (20, 40, 80, 160, 320), 1)).dropna()
        r = r.loc[r.index >= '2011-06-01']
        print(c, f'{sh(r):+.2f} to2017 {sh(r[:"2017"]):+.2f} from2018 {sh(r["2018":]):+.2f}')
