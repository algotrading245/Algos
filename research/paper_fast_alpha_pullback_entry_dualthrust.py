"""Zarattini-Pagani 'Fast Alphas' pullback overlay on the four-index Dual Thrust leg (k1 0.3 / k2 0.7, N=4, same params).
Rule (single variant, no sweep): when a breakout/stop level is touched (M1 bars), do not fill at the level; wait for the
first completed 5-min bar after the signal bar whose return goes against the trade direction (long: close<open,
short: close>open) and fill at that bar's close. A stop exit does the same (long stop waits for an up bar), and the
reversal fills on that same bar. No bar before 22:00 -> entry skipped / open position closed at the 22:00 close.
Costs as in the baseline script (half the round-trip spread per fill). Baseline is re-run in the same file for the
comparison. Run: python research/paper_fast_alpha_pullback_entry_dualthrust.py"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, 'research')
sys.path.insert(0, 'tools')
import holdout
import prebuilt_dual_thrust_fx_gold as dt

dt.K1, dt.K2 = 0.3, 0.7
dt.MAXOPEN = 75
SPR = {'SPXUSD': 1.5e-4, 'NSXUSD': 1.5e-4, 'GRXEUR': 2.0e-4, 'JPXJPY': 3.0e-4}
sharpe = dt.sharpe
N = dt.N


def sim_pb(sym, d):
    day = d.index.normalize()
    g = d.groupby(day)
    D = pd.DataFrame({'h': g['high'].max(), 'l': g['low'].min(), 'c': g['close'].last()})
    D = D[D.index.dayofweek < 5]
    hh = D.h.rolling(N).max(); ll = D.l.rolling(N).min()
    hc = D.c.rolling(N).max(); lc = D.c.rolling(N).min()
    rng = np.maximum(hh - lc, hc - ll).shift(1)
    sd = D.c.pct_change().rolling(60).std().shift(1)
    mod = (d.index.hour * 60 + d.index.minute).to_numpy()
    sel = (mod >= dt.START_MIN) & (mod < dt.END_MIN) & (d.index.dayofweek < 5)
    ds = d[sel]
    gross, fills = {}, {}
    for t, w in ds.groupby(ds.index.normalize()):
        if t not in rng.index or not np.isfinite(rng[t]) or not np.isfinite(sd[t]) or len(w) < 120:
            continue
        if w.index[0].hour * 60 + w.index[0].minute > dt.MAXOPEN:
            continue
        o = w.open.iloc[0]
        up, dn = o + dt.K1 * rng[t], o - dt.K2 * rng[t]
        H, L, C, O = w.high.to_numpy(), w.low.to_numpy(), w.close.to_numpy(), w.open.to_numpy()
        m = (w.index.hour * 60 + w.index.minute).to_numpy()
        b = m // 5
        # 5-min bars: bin id -> (first idx, last idx)
        ub, first = np.unique(b, return_index=True)
        last = np.r_[first[1:] - 1, len(b) - 1]
        o5, c5 = O[first], C[last]

        def fill_after(k, direction):
            """first bin after bin of k with return against `direction`; returns (price, next M1 pos) or None"""
            j = np.searchsorted(ub, b[k], side='right')
            while j < len(ub):
                if (direction == 1 and c5[j] < o5[j]) or (direction == -1 and c5[j] > o5[j]):
                    return c5[j], last[j] + 1
                j += 1
            return None

        side, pos, pnl, nf, entry = 0, 0, 0.0, 0, 0.0
        while True:
            if side == 0:
                iu = np.flatnonzero(H[pos:] >= up); idn = np.flatnonzero(L[pos:] <= dn)
                iu = iu[0] + pos if len(iu) else 10**9
                idn = idn[0] + pos if len(idn) else 10**9
                if min(iu, idn) == 10**9 or iu == idn:
                    break
                s, k = (1, iu) if iu < idn else (-1, idn)
                f = fill_after(k, s)
                if f is None:
                    break
                side, entry, pos = s, f[0], f[1]
                nf += 1
            else:
                lvl = dn if side == 1 else up
                hit = np.flatnonzero(L[pos:] <= lvl) if side == 1 else np.flatnonzero(H[pos:] >= lvl)
                if len(hit) == 0:
                    pnl += side * (C[-1] - entry); nf += 1
                    break
                k = hit[0] + pos
                f = fill_after(k, -side)
                if f is None:
                    pnl += side * (C[-1] - entry); nf += 1
                    break
                pnl += side * (f[0] - entry); nf += 1
                side, entry, pos = -side, f[0], f[1]
                nf += 1
                if pos >= len(H):
                    pnl += side * (C[-1] - entry) * 0  # reversal at the close: flat
                    break
        if nf == 0:
            continue
        expo = min(0.10 / (sd[t] * np.sqrt(252)), 3.0)
        gross[t] = pnl / o * expo
        fills[t] = nf * 0.5 * expo
    return pd.Series(gross), pd.Series(fills), D.index


def main():
    out = {}
    for tag, fn in (('base', dt.sim), ('pull', sim_pb)):
        res = {1.0: {}, 1.5: {}, 2.0: {}}
        for s in SPR:
            gr, fl, idx = fn(s, dt.load(s))
            for cm in res:
                res[cm][s] = holdout.drop((gr - fl * SPR[s] * cm).reindex(idx).fillna(0.0))
            x = res[1.0][s]
            print(tag, s, 'SR', round(sharpe(x), 2), 'h1', round(sharpe(x[:'2017']), 2), 'h2', round(sharpe(x['2018':]), 2),
                  'trades/fills', int(fl.sum() / 0.5), flush=True)
        R = {cm: pd.DataFrame(v).fillna(0).loc['2010':] for cm, v in res.items()}
        out[tag] = R
        b, bs, b2 = R[1.0].mean(axis=1), R[1.5].mean(axis=1), R[2.0].mean(axis=1)
        print(tag, 'four EW SR', round(sharpe(b), 2), 'h1', round(sharpe(b[:'2017']), 2), 'h2', round(sharpe(b['2018':]), 2),
              '1.5x', round(sharpe(bs), 2), '2x', round(sharpe(b2), 2), flush=True)
    print('corr base vs pull', round(out['base'][1.0].mean(axis=1).corr(out['pull'][1.0].mean(axis=1)), 3))
    R = out['pull']
    name = 'paper_fast_alpha_pullback_entry_dualthrust'
    for nm, ser in ((name, R[1.0].mean(axis=1)), (name + '_stress', R[1.5].mean(axis=1))):
        pd.DataFrame({'day': ser.index.strftime('%Y-%m-%d'), 'r': ser.values}).to_csv(
            f'marketdata/candidates/{nm}.csv', index=False)
    mk = R[1.0].copy()
    mk.insert(0, 'day', mk.index.strftime('%Y-%m-%d'))
    mk.to_csv(f'marketdata/candidates/{name}_markets.csv', index=False)


if __name__ == '__main__':
    main()
