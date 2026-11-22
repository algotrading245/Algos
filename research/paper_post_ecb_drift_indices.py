"""Post-ECB announcement drift (Valentin 2022) on GER40 (GRXEUR) and US500 (SPXUSD), US100 (NSXUSD).
Data clock is broker server time (EET, US-DST), US data at 15:30, so ECB release 13:45 CET = 14:45 server,
press conference 14:30 CET = 15:30 server, window ends ~16:30 server.
ECB dates are not in the repo (no download): detected from EURUSD M1 as the Thursdays with the largest range in
14:45-14:59 server per year (top 12/yr to 2014, 8/yr from 2015). Range only, direction not used.
Signal: index return 15:30->16:30 server on that day. Enter 16:30, exit close (22:00 server) of t+12 business days.
Cost: 1bp per side x mult. Daily pnl is mark-to-market spread over the holding days (position r_t)."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, 'tools')
import holdout

def load(name):
    d = pd.read_csv(f'marketdata/histdata/{name}_M1.csv.gz')
    d['t'] = pd.to_datetime(d['time'], unit='s')
    d = d.set_index('t')
    return holdout.drop(d)

eu = load('EURUSD')
rng = (eu.high - eu.low)
mod = rng.index.hour * 60 + rng.index.minute
sel = rng[(mod >= 14 * 60 + 45) & (mod < 15 * 60) & (rng.index.dayofweek == 3)]
score = sel.groupby(sel.index.normalize()).max()
# normalise by the day's typical M1 range to avoid vol-regime bias
base = rng.groupby(rng.index.normalize()).median()
score = (score / base.reindex(score.index)).dropna()
dates = []
for y, g in score.groupby(score.index.year):
    n = 12 if y <= 2014 else 8
    dates += list(g.sort_values(ascending=False).head(n).index)
dates = sorted(dates)
print('ECB-like dates', len(dates), 'first', dates[:3], 'last', dates[-3:])
print('per-year', pd.Series([d.year for d in dates]).value_counts().sort_index().to_dict())

def run(name, mult, hold=12, cost_bp=1.0):
    ix = load(name)
    c = ix['close']
    day = c.groupby(c.index.normalize()).last()
    rets = np.log(day).diff().dropna()
    days = rets.index
    pos = pd.Series(0.0, index=days)
    cost = pd.Series(0.0, index=days)
    ev = 0
    for d in dates:
        if d not in days: continue
        a = c[(c.index >= d + pd.Timedelta(hours=15, minutes=30)) & (c.index <= d + pd.Timedelta(hours=15, minutes=31))]
        b = c[(c.index >= d + pd.Timedelta(hours=16, minutes=29)) & (c.index <= d + pd.Timedelta(hours=16, minutes=31))]
        if len(a) == 0 or len(b) == 0: continue
        s = np.sign(np.log(b.iloc[-1] / a.iloc[0]))
        if s == 0: continue
        i = days.get_loc(d)
        # remainder of day d after 16:30
        rest = np.log(day[d] / b.iloc[-1])
        pos.iloc[i] += 0  # handled below
        pnl_first = s * rest
        pos.iloc[i] += pnl_first
        for k in range(1, hold + 1):
            if i + k < len(days): pos.iloc[i + k] += s * rets.iloc[i + k]
        cost.iloc[i] += 2 * cost_bp * mult * 1e-4
        ev += 1
    return pos, cost, ev

def sh(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float('nan')

res = {}
for name in ['GRXEUR', 'SPXUSD', 'NSXUSD']:
    for m in (1.0, 1.5, 2.0):
        pos, cost, ev = run(name, m)
        r = pos - cost
        a, b = r[:'2017-12-31'], r['2018-01-01':]
        print(name, f'x{m}', 'events', ev, 'Sharpe<=2017 %.2f' % sh(a), '>=2018 %.2f' % sh(b), 'ann ret bp %.0f' % (r.mean() * 252 * 1e4), 'sum/event bp %.0f' % (r.sum() / max(ev, 1) * 1e4))
        res[(name, m)] = r
# per-event window sign vs forward-return to show the paper's effect
for name in ['GRXEUR']:
    pos, cost, ev = run(name, 1.0)
    print('GER40 long-only/short-only not run; shorts-only skipped (pre-registered both-sided)')

import os
r1 = res[('GRXEUR', 1.0)]; r15 = res[('GRXEUR', 1.5)]
full = pd.DataFrame({'day': r1.index.strftime('%Y-%m-%d'), 'r': r1.values})
full.to_csv('marketdata/candidates/paper_post_ecb_drift_indices.csv', index=False)
st = pd.DataFrame({'day': r15.index.strftime('%Y-%m-%d'), 'r': r15.values})
st.to_csv('marketdata/candidates/paper_post_ecb_drift_indices_stress.csv', index=False)
m = pd.DataFrame({n: res[(n, 1.0)] for n in ['GRXEUR', 'SPXUSD', 'NSXUSD']})
m.index = m.index.strftime('%Y-%m-%d'); m.index.name = 'day'
m.to_csv('research/paper_post_ecb_drift_indices_markets_tmp.csv')  # not used for belief: only GER40 profits
