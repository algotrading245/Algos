"""Intraday overreaction: do large 15-minute moves reverse over the next hour?  (Grant, Wolf, Yu 2005, "Intraday
price reversals in the US stock index futures market: a 15-year study", J. Banking & Finance - large opening moves
in S&P 500 futures partly reverse; tested here before only on gold ticks, research/burst_fade_ticks.py.)

Own test, rules fixed in advance: 15-minute bid bars on the server clock; a shock is a bar whose |return| exceeds
4 x the mean |return| of the same bar-of-day over the previous 20 days; fade it from the bar's close for 60 minutes;
one trade at a time.  Costs a round trip: FX majors 1 bp, crosses 2 bp, gold 1 bp, index CFDs 0.75 bp (wider
spreads right after shocks are not modelled, so these are the best case).

    python research/shock_reversal_fx.py

Result (2026-10-15): rejected.  About 7,000-8,500 shocks per instrument since 2009; before cost the fade earns
-0.40 to +0.52 bp a trade on every one (FX majors, yen crosses, gold, S&P 500, Nasdaq) - big 15-minute moves neither
reverse nor continue over the next hour - so after cost all lose (t -1.7 to -9.9), in both halves.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
SYMS = {"EURUSD": 1.0, "GBPUSD": 1.0, "USDJPY": 1.0, "AUDUSD": 1.0, "USDCAD": 1.0, "USDCHF": 1.0, "EURJPY": 2.0,
        "GBPJPY": 2.0, "XAUUSD": 1.0, "SPXUSD": 0.75, "NSXUSD": 0.75}


def run(s, cost):
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz", usecols=["time", "close"])
    c = m.groupby(m.time // 900).close.last()
    c.index = pd.to_datetime(c.index * 900, unit="s")
    c = c[c.index.dayofweek < 5]
    full = c.resample("15min").last()
    r = np.log(full).diff()
    slot = r.index.hour * 4 + r.index.minute // 15
    a = r.abs()
    usual = a.groupby(slot).transform(lambda z: z.rolling(20, min_periods=10).mean().shift(1))
    shock = (a > 4 * usual) & usual.notna()
    fwd = np.log(full).shift(-4) - np.log(full)               # next 60 minutes
    out, busy = [], None
    for t in r.index[shock.to_numpy()]:
        if busy is not None and t < busy:
            continue
        f = fwd.get(t, np.nan)
        if np.isnan(f) or np.isnan(r[t]):
            continue
        out.append((t, -np.sign(r[t]) * f - cost * 1e-4))
        busy = t + pd.Timedelta(minutes=60)
    return pd.Series([o[1] for o in out], index=pd.DatetimeIndex([o[0] for o in out]))


def tt(x):
    return x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else 0.0


if __name__ == "__main__":
    for s, cost in SYMS.items():
        x = run(s, cost)
        print(f"{s}: {len(x)} shocks, {x.mean() * 1e4:+.2f} bp a trade (t {tt(x):+.1f}); to 2017 {x[:'2017'].mean() * 1e4:+.2f} "
              f"(t {tt(x[:'2017']):+.1f}), 2018+ {x['2018':].mean() * 1e4:+.2f} (t {tt(x['2018':]):+.1f}); before cost "
              f"{(x.mean() + cost * 1e-4) * 1e4:+.2f} bp", flush=True)
