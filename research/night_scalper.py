"""The "night scalper" concept of commercial FX EAs: fade stretched moves on quiet pairs in the hours after the
New York rollover, small target, wide stop, high win rate.

A fixed, conventional version (no fitting): 15-minute bid bars on the server clock (New York + 7); Bollinger band
20 bars, 2 standard deviations, on closes; entries only on bars closing between server 01:00 and 04:00 (18:00-21:00
New York, after the rollover's wide spreads); a close above the upper band sells, below the lower band buys, at
that close; target the middle band of the entry bar, stop 2.5 band half-widths beyond the entry, everything flat at
server 06:00; one trade at a time per pair.  Exits are checked on 5-minute highs and lows (stop first when a bar
touches both).  Costs per round trip in bp of price: 1, 2, 3 (night spreads on crosses are 1.5-4 pips).  Equal
risk per trade: the result is in units of the stop distance (R).

    python research/night_scalper.py

Result (2026-10-15): rejected, the edge is smaller than the night spread.  Before costs every pair but AUD/JPY earns
a little (+0.02 to +0.09 R a trade, 57-61% winners) - with stops of 12-32 bp that is 1-2 bp a trade.  At 1 bp a
round trip only AUD/CAD (+0.12) and GBP/CHF (+0.10) stay above zero and both are negative from 2018; all pairs
together -1.48 at 1 bp, -4.68 at 2 bp, -7.44 at 3 bp, worse from 2018 than before.  Commercial night scalpers that
lived on this relied on raw-spread night quotes that brokers since widened.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
PAIRS = ["EURCHF", "EURGBP", "AUDCAD", "AUDNZD", "NZDCAD", "GBPCHF", "USDCHF", "EURUSD", "GBPUSD", "USDCAD", "AUDJPY"]


def bars(s, minutes):
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz")
    m = m[pd.to_datetime(m.time, unit="s").dt.dayofweek < 5]
    g = m.assign(time=m.time // (60 * minutes) * (60 * minutes)).groupby("time").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    g.index = pd.to_datetime(g.index, unit="s")
    return g


def run(s):
    q = bars(s, 15)
    f = bars(s, 5)
    mid = q.close.rolling(20).mean()
    sd = q.close.rolling(20).std()
    end_bar = q.index + pd.Timedelta(minutes=15)                 # signal known at the bar's close
    hrs = end_bar.hour + end_bar.minute / 60
    sig = pd.Series(0, index=q.index)
    sig[(q.close > mid + 2 * sd)] = -1
    sig[(q.close < mid - 2 * sd)] = 1
    sig[~((hrs > 1.0) & (hrs <= 4.0))] = 0
    fh, fl, fc, ft = f.high.to_numpy(), f.low.to_numpy(), f.close.to_numpy(), f.index.to_numpy()
    out, busy = [], np.datetime64("1970-01-01")
    for t in sig.index[sig != 0]:
        t_in = np.datetime64(t + pd.Timedelta(minutes=15))
        if t_in < busy or np.isnan(sd[t]) or sd[t] <= 0:
            continue
        side, e = sig[t], q.close[t]
        tgt, stop = mid[t], e - side * 2.5 * 2 * sd[t]
        R = abs(e - stop)
        flat = np.datetime64(pd.Timestamp(t.date()) + pd.Timedelta(hours=6))
        i, j = np.searchsorted(ft, t_in), np.searchsorted(ft, flat)
        x, k_end = None, j
        for k in range(i, j):
            if side * ((fl[k] if side > 0 else fh[k]) - stop) <= 0:
                x, k_end = stop, k
                break
            if side * ((fh[k] if side > 0 else fl[k]) - tgt) >= 0:
                x, k_end = tgt, k
                break
        if x is None:
            if j == 0 or j > len(fc):
                continue
            x = fc[j - 1]
        busy = ft[min(k_end, len(ft) - 1)]
        out.append((pd.Timestamp(t.date()), side * (x - e) / R, R / e))
    return pd.DataFrame(out, columns=["day", "r", "rel"])


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    hy = pd.read_csv(CACHE, index_col=0, parse_dates=True).sum(axis=1)
    hy = hy[hy.index.dayofweek < 5]
    port = {c: [] for c in (1, 2, 3)}
    for s in PAIRS:
        T = run(s)
        line = []
        for c in (1, 2, 3):
            r = T.r - c * 1e-4 / T.rel                         # cost in R
            d = r.groupby(T.day).sum()
            port[c].append(d.rename(s))
            line.append(f"{c}bp {r.mean():+.3f}R win {(r > 0).mean():.0%} Sharpe {sharpe(d):+.2f} "
                        f"(to2017 {sharpe(d[:'2017']):+.2f}, 2018+ {sharpe(d['2018':]):+.2f})")
        print(f"{s}: {len(T)} trades, stop {T.rel.median() * 1e4:.0f} bp  gross {T.r.mean():+.3f}R | " + " | ".join(line),
              flush=True)
    for c in (1, 2, 3):
        p = pd.concat(port[c], axis=1, sort=True).fillna(0).mean(axis=1)
        p = p.reindex(hy.index).fillna(0) * 0.003                # 0.3% risk per trade, averaged over pairs
        best = max(((sharpe((hy + w * p)[:"2017"]), w) for w in (0.25, 0.5, 1.0, 2.0)))
        print(f"all pairs at {c} bp: Sharpe {sharpe(p):+.2f} (to2017 {sharpe(p[:'2017']):+.2f}, 2018+ "
              f"{sharpe(p['2018':]):+.2f})  corr Hydra {p.corr(hy):+.2f}  Hydra + {best[1]}x: 2018+ "
              f"{sharpe((hy + best[1] * p)['2018':]):.3f} (3.371)")
