"""Liu-Tsyvinski-Wu: weekly cross-sectional crypto momentum, market-neutral. Binance daily (open 00:00 UTC).
Pre-registered main: 2-week return, long top 2 / short bottom 2 of the large-coin universe, vol-weighted (30d), weekly
rebalance on Sunday 00:00 UTC (the signal uses closes to Saturday), gross exposure 1. 1/3/4 week are robustness only.
Costs: 10bp round trip per traded notional at 1x (5bp each way), swap -30%/yr on gross notional (both legs pay) at 1x
(the earlier crypto rejections used the same); 'noswap' shown too. 1.5x/2x scale spread and swap."""
import sys
sys.path.insert(0, 'tools')
import pandas as pd, numpy as np
import holdout

MAIN = ['BTC', 'ETH', 'LTC', 'XRP', 'ADA', 'BNB', 'DOGE', 'XLM']
BROAD = MAIN + ['BCH', 'DASH', 'ETC', 'LINK', 'XMR']

def load(c):
    d = pd.read_csv(f'marketdata/crypto/{c}USDT_1d.csv')
    d['day'] = pd.to_datetime(d.ts_utc, unit='s').dt.normalize()
    return d.set_index('day').close

def sharpe(r):
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0

def run(coins, lb=14, k=2, spread=5.0, swap=0.30, minn=6, rebal_dow=6):
    px = pd.DataFrame({c: load(c) for c in coins})
    px = px[px.index < '2025-10-13']
    ret = px.pct_change()
    vol = ret.rolling(30).std()
    mom = px.pct_change(lb)
    w = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    cur = pd.Series(0.0, index=px.columns)
    turn = pd.Series(0.0, index=px.index)
    for i, t in enumerate(px.index):
        if t.dayofweek == rebal_dow and i > 0:
            s = mom.iloc[i - 1]; v = vol.iloc[i - 1]
            ok = s.notna() & v.notna() & (v > 0)
            new = pd.Series(0.0, index=px.columns)
            if ok.sum() >= minn:
                ss = s[ok].sort_values()
                lo, hi = ss.index[:k], ss.index[-k:]
                for names, sg in ((hi, 1), (lo, -1)):
                    iv = 1 / v[names]; new[names] = sg * 0.5 * iv / iv.sum()
            turn[t] = (new - cur).abs().sum()
            cur = new
        w.iloc[i] = cur
    gross = (w.shift(0) * ret.shift(0)).sum(axis=1)  # weights set at 00:00 open of t; close-to-close of t approximates open-to-close
    # entry at open t: use open-to-close for rebalance day is ignored; weights apply to day t return (open->close ~ close->close)
    res = {}
    for nm, m in (('1x', 1.0), ('1.5x', 1.5), ('2x', 2.0)):
        r = gross - turn * spread * m / 1e4 - w.abs().sum(axis=1) * swap * m / 365
        res[nm] = r[w.abs().sum(axis=1) > 0].copy()
    res['noswap'] = (gross - turn * spread / 1e4)[w.abs().sum(axis=1) > 0]
    res['gross'] = gross[w.abs().sum(axis=1) > 0]
    return res, w, turn

def rep(tag, res):
    print(tag)
    for k, r in res.items():
        print(f'  {k:7s} n={len(r)} SR {sharpe(r):5.2f} h<2018 {sharpe(r[r.index < "2018-01-01"]):5.2f} '
              f'h>=2018 {sharpe(r[r.index >= "2018-01-01"]):5.2f} <2022 {sharpe(r[r.index < "2022-01-01"]):5.2f} '
              f'>=2022 {sharpe(r[r.index >= "2022-01-01"]):5.2f} mean bp/d {r.mean()*1e4:5.1f}')

res, w, turn = run(MAIN)
rep('MAIN 2w top2/bot2', res)
print('avg weekly turnover', round(turn[turn > 0].mean(), 2), 'first day', res['1x'].index[0].date())
for lb in (7, 21, 28):
    r2, _, _ = run(MAIN, lb=lb); rep(f'robust lb={lb}d', {k: r2[k] for k in ('gross', '1x', 'noswap')})
r2, _, _ = run(BROAD, k=3); rep('BROAD k=3', {k: r2[k] for k in ('gross', '1x', 'noswap', '1.5x')})
# markets: same parameters on subsets (drop one coin family) -> robustness across universes
mk = {}
for nm, cs in (('main', MAIN), ('broad3', BROAD)):
    r2, _, _ = run(cs, k=2 if nm == 'main' else 3); mk[nm] = r2['1x']
r3, _, _ = run(['BTC', 'ETH', 'LTC', 'XRP', 'BCH', 'DASH', 'ETC', 'XMR', 'LINK'], k=2); mk['alt_a'] = r3['1x']; rep('alt_a', {'1x': r3['1x']})
tag = {0: 'a'}
out = res['1x'].rename('r').reset_index(); out['day'] = out['day'].dt.strftime('%Y-%m-%d')
out.to_csv('marketdata/candidates/crypto_xs_mom.csv', index=False)
out = res['1.5x'].rename('r').reset_index(); out['day'] = out['day'].dt.strftime('%Y-%m-%d')
out.to_csv('marketdata/candidates/crypto_xs_mom_stress.csv', index=False)
m = pd.DataFrame(mk).dropna(); m.index = m.index.strftime('%Y-%m-%d')
m.reset_index().rename(columns={'index': 'day', 'day': 'day'}).to_csv('marketdata/candidates/crypto_xs_mom_markets.csv', index=False)
