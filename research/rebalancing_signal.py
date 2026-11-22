"""Harvey-Mazzoleni-Melone (2025) rebalancing signal, equity side only on US500 (and NSX, GRX, JPX as belief check).
60/40 portfolio of S&P 500 and 10y Treasury; signal at close t predicts next-day equity return negatively.
Threshold signal: mean over delta in 0..2.5% (step 0.1) of (w - 0.60) with reset when |w-0.6|>delta.
Calendar signal: w - 0.60 reset on last business day of month, used in last 5 trading days of month.
Position for day t+1 = -sign(signal_t) (calendar: only in window). Cost: spread per position change, swap by side.
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'tools')
import holdout

SPREAD_BP = 1.0          # US500 60 points on ~6000 = 1.0bp full spread (round-trip counted on each change)
SWAP_LONG_BP = 2.3       # -160 points/day on ~7000
SWAP_SHORT_BP = 0.35     # -24 points/day


def load_spx():
    d = pd.read_csv('marketdata/histdata/SPX_D1.csv', parse_dates=['date']).set_index('date')['close']
    return d


def load_m1(sym):
    d = pd.read_csv(f'marketdata/histdata/{sym}_M1.csv.gz')
    d['t'] = pd.to_datetime(d['time'], unit='s')
    s = d.set_index('t')['close']
    return s.resample('1D').last().dropna()


def r10(dgs):
    y = dgs.ffill()
    dy = y.diff() / 100
    return -8 * dy + y.shift(1) / 100 / 252


def signals(spx):
    dgs = pd.read_csv('marketdata/fred/DGS10.csv', parse_dates=['observation_date'], na_values=['.', '']).set_index('observation_date')['DGS10']
    dgs = dgs.reindex(spx.index).ffill()
    rs = spx.pct_change().fillna(0).values
    rb = r10(dgs).fillna(0).values
    n = len(spx)
    deltas = np.arange(0, 0.0251, 0.001)
    w = np.full(len(deltas), 0.6)
    wc = 0.6
    thr = np.zeros(n)
    cal = np.zeros(n)
    idx = spx.index
    ym = idx.to_period('M')
    last_of_month = np.r_[ym[1:] != ym[:-1], True]
    # trading day rank from month end
    rank_from_end = np.zeros(n, int)
    k = 0
    for i in range(n - 1, -1, -1):
        if last_of_month[i]:
            k = 0
        else:
            k += 1
        rank_from_end[i] = k
    for i in range(1, n):
        w = w * (1 + rs[i]) / (w * (1 + rs[i]) + (1 - w) * (1 + rb[i]))
        wc = wc * (1 + rs[i]) / (wc * (1 + rs[i]) + (1 - wc) * (1 + rb[i]))
        thr[i] = np.mean(w - 0.6)
        cal[i] = wc - 0.6
        w = np.where(np.abs(w - 0.6) > deltas, 0.6, w)
        if last_of_month[i]:
            wc = 0.6
    thr = pd.Series(thr, idx)
    cal = pd.Series(cal, idx)
    win = pd.Series(rank_from_end <= 4, idx)
    # calendar uses signal value before reset; recompute without reset effect on the last day: value stored pre-reset
    return thr, cal, win


def run(px, thr, cal, win, mode, cost_mult=1.0):
    ret = px.pct_change()  # return of day t, earned by the position set at close t-1 (pos shifted below)
    if mode == 'thr':
        pos = -np.sign(thr)
    elif mode == 'cal':
        pos = -np.sign(cal) * win.astype(float)
    else:
        pos = -np.sign(thr + cal * win.astype(float))
    pos = pos.reindex(px.index).fillna(0).shift(1).fillna(0)
    gross = pos * ret
    chg = pos.diff().abs().fillna(0)
    spread = chg * SPREAD_BP / 1e4 * cost_mult
    swap = (np.where(pos > 0, SWAP_LONG_BP, np.where(pos < 0, SWAP_SHORT_BP, 0)) / 1e4) * cost_mult
    r = (gross - spread - swap).dropna()
    # shift index: return earned on day t+1 booked on day t+1
    r.index = px.index[1:][:len(r)] if False else r.index
    return r


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0


def main():
    spx = load_spx()
    thr, cal, win = signals(spx)
    out = {}
    for mode in ['thr', 'cal', 'both']:
        r = run(spx, thr, cal, win, mode)
        r = holdout.drop(r)
        a = r[:'2017']
        b = r['2018':]
        print(mode, 'full', round(sharpe(r), 2), 'to2017', round(sharpe(a), 2), '2018on', round(sharpe(b), 2), 'n', len(r),
              'ann%', round(r.mean() * 252 * 100, 2), 'inmarket', round((r != 0).mean(), 2))
    return spx, thr, cal, win


if __name__ == '__main__':
    main()
