"""Gold-silver spread mean reversion (Wahab/Cohn/Lashgari 1994 style). Pre-registered: z window 60, entry 2, exit 0,
max hold 20 days, one setting, no tuning. Daily closes at 17:00 New York. Signal at close t, earns day t+1.
Weights: gold = volAG/(volAU+volAG), silver = volAU/(volAU+volAG) (equal risk, 60d vol, past only).
Costs per unit of notional traded (round trip in bp): gold 3, silver 8 (assumed; 1x), stress 1.5x, 2x. Holdout dropped.
Also reports a z-window 120 and entry 1.5 as sensitivity only (not chosen from)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout


def daily(sym):
    m = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz', usecols=['time', 'close'])
    t = pd.to_datetime(m['time'] + 60 - 7 * 3600, unit='s').dt.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT')
    ok = t.notna().to_numpy()
    s = pd.Series(m['close'].to_numpy()[ok], index=pd.DatetimeIndex(t[ok]))
    s = s.groupby(level=0).last()
    s.index = s.index.tz_localize(None) + pd.Timedelta(hours=7)  # trading day rolls at 17:00 NY
    d = s.groupby(s.index.normalize()).last()
    return d[d.index.dayofweek < 5]


au, ag = daily('XAUUSD'), daily('XAGUSD')
df = pd.concat([au, ag], axis=1, keys=['au', 'ag']).dropna()
ra, rg = df.au.pct_change(), df.ag.pct_change()
print('days', len(df), df.index[0].date(), df.index[-1].date(), 'max |ret| au/ag', ra.abs().max(), rg.abs().max())


def run(win, ent, ex=0.0, maxh=20, ca=3, cg=8, mult=1.0):
    sp = np.log(df.au / df.ag)
    z = ((sp - sp.rolling(win).mean()) / sp.rolling(win).std()).to_numpy()
    va = ra.rolling(60).std().shift(0).to_numpy()
    vg = rg.rolling(60).std().to_numpy()
    n = len(df)
    pos = np.zeros(n)  # position decided at close of day i, held over day i+1
    h = 0
    for i in range(n):
        p = pos[i - 1] if i else 0
        if p != 0:
            h += 1
            if (p > 0 and z[i] >= -ex) or (p < 0 and z[i] <= ex) or h >= maxh:
                p = 0
        if p == 0 and not np.isnan(z[i]):
            if z[i] > ent:
                p, h = -1, 0  # spread rich: short gold, long silver
            elif z[i] < -ent:
                p, h = 1, 0
        pos[i] = p
    wa = vg / (va + vg)
    wg = va / (va + vg)
    pa = pd.Series(pos, index=df.index).shift(1).fillna(0)
    gross = pa * (wa * ra - wg * rg)
    # turnover: change in position * weights
    chg = (pd.Series(pos, index=df.index).diff().abs().fillna(0)).shift(1).fillna(0)
    # cost on entry/exit days (day when position changes = day after decision, approximated at decision close)
    dpos = pd.Series(pos, index=df.index).diff().abs().fillna(0)
    cst = dpos * (wa * ca + wg * cg) * 1e-4 * mult / 2 * 1  # half round trip per change
    cst = cst.shift(1).fillna(0)
    r = (gross - cst).dropna()
    return r, int((dpos > 0).sum())


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 30 and x.std() > 0 else float('nan')


for win, ent in ((60, 2.0), (120, 2.0), (60, 1.5)):
    for mult in (1, 1.5, 2):
        r, nt = run(win, ent, mult=mult)
        r = holdout.drop(r)
        print(f'win {win} ent {ent} cost x{mult}: all {sh(r):5.2f} to2017 {sh(r[:"2017"]):5.2f} 2018+ {sh(r["2018":]):5.2f} '
              f'mean/day {r.mean()*1e4:5.2f}bp changes {nt}')

r, _ = run(60, 2.0, mult=1)
s, _ = run(60, 2.0, mult=1.5)
holdout.drop(r).rename('r').to_csv('marketdata/candidates/paper_gold_silver_spread_meanrev.csv', index_label='day')
holdout.drop(s).rename('r').to_csv('marketdata/candidates/paper_gold_silver_spread_meanrev_stress.csv', index_label='day')
print('trials 3 settings x 3 costs; candidate = win60 ent2')
