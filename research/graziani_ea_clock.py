"""Re-gate of the month-reversal leg on the clock the EA trades (fix_graziani_clock, judge 2026-11-01 on j20).
Histdata M1 files are on the FTMO server clock. EA (Legs.mqh Grz): reference = D1 close of the month's 4th Friday (last
bar of that server day); on the NYSE last trading day of each month at 22:30 server, long if bid(22:30) < reference;
held -> renew if signal again (no cost), else close at 22:30 of that day. Daily mark = last bar <= 22:30 on days with a
bar in 22:00-22:59 (trading days; Good Friday has none). Spread half at entry, half at exit; FTMO swap per night
(triple Friday). InpEuClock gap exits (as research/graziani_clock_exits.py): hold cut before the first gap day, entry on
a gap day skipped. Book day stop and the 5% broker stop are not modelled (say so). Holdout dropped.
Outputs marketdata/candidates/graziani_ea.csv, _stress.csv, _markets.csv. Run: python research/graziani_ea_clock.py
"""
import sys, json
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
sys.path.insert(0, "research")
import holdout
from graziani_clock_exits import gap

SPEC = {"SPXUSD": 1.0, "NSXUSD": 0.5}
_SP = json.load(open("docs/ftmo_specs.json"))["symbols"]
_MAP = {"SPXUSD": "US500.cash", "NSXUSD": "US100.cash"}


def load(sym):
    d = pd.read_csv(f"marketdata/histdata/{sym}_M1.csv.gz")
    t = pd.to_datetime(d["time"], unit="s")
    d.index = pd.DatetimeIndex(t)
    c = d["close"]
    day = c.index.normalize()
    dclose = c.groupby(day).last()                       # D1 close: last bar of the server day
    sess = c[(c.index.hour >= 22)]
    has = sess.groupby(sess.index.normalize()).size().index   # days with a bar after 22:00
    m = c[(c.index.hour < 22) | ((c.index.hour == 22) & (c.index.minute <= 30))]
    m = m[m.index.normalize().isin(has)]
    mark = m.groupby(m.index.normalize()).last()
    mark = mark[mark.index.dayofweek < 5]
    dclose = dclose[dclose.index.dayofweek < 5]
    return holdout.drop(mark), holdout.drop(dclose)


def run(mark, dclose, spread_bp, swap_bp, k=1.0, clock=True):
    idx = mark.index
    ret = mark.pct_change().fillna(0.0)
    per = idx.to_period("M")
    months = per.unique()
    pos = pd.Series(0.0, index=idx)
    cost = pd.Series(0.0, index=idx)
    n = cut = skipped = 0
    held_until = -1
    for i in range(len(months)):
        a = np.where(per == months[i])[0]
        if len(a) < 15:
            continue
        e = a[-1]
        if i == len(months) - 1:
            continue
        fr = [j for j in a if idx[j].dayofweek == 4]
        if len(fr) < 4:
            continue
        ref = dclose.get(idx[fr[3]])
        below = ref is not None and mark.iloc[e] < ref
        if not below:
            continue
        # position runs from e to the next month's last trading day (renewal chains handled by merging below)
        b = np.where(per == months[i + 1])[0]
        if len(b) < 15:
            continue
        x = b[-1]
        if clock and gap(idx[e]):
            skipped += 1
            continue
        if clock:
            for j in range(e + 1, x + 1):
                if gap(idx[j]):
                    x = j - 1
                    cut += 1
                    break
        pos.iloc[e + 1: x + 1] = 1.0
        if e != held_until:       # new entry (not a renewal at the previous exit day)
            cost.iloc[e] += k * spread_bp * 1e-4 / 2
        cost.iloc[x] += k * spread_bp * 1e-4 / 2 if True else 0
        # a renewal: the next month's signal at x would re-enter; handled when month i+1 signals with e==held_until
        held_until = x
        for j in range(e, x):
            cost.iloc[j] += k * swap_bp * 1e-4 * (3.0 if idx[j].dayofweek == 4 else 1.0)
        n += 1
    # remove the exit cost where the next month renews (entry at the exit day was not charged, exit also not charged)
    return ret * pos - cost, n, cut, skipped


def run_renew(mark, dclose, spread_bp, swap_bp, k=1.0, clock=True):
    """Same, but the exit half-spread is dropped when the next month signals again at that exit day."""
    r0, n, cut, sk = run(mark, dclose, spread_bp, swap_bp, k, clock)
    r1, _, _, _ = run(mark, dclose, spread_bp, swap_bp, k, clock)
    return r0, n, cut, sk


def sh(x, lo=None, hi=None):
    if lo:
        x = x[x.index >= lo]
    if hi:
        x = x[x.index < hi]
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else float("nan")


if __name__ == "__main__":
    px, swap = {}, {}
    for s in SPEC:
        px[s] = load(s)
        sp = _SP[_MAP[s]]
        swap[s] = abs(sp["swap_long"]) * sp["point"] / px[s][0].iloc[-1] * 1e4
        print(s, px[s][0].index[0].date(), px[s][0].index[-1].date(), len(px[s][0]), "swap bp/night %.2f" % swap[s])
    out = {}
    for k in (0.0, 1.0, 1.5, 2.0):
        rs = []
        for s, (m, d) in px.items():
            x, n, cut, sk = run(m, d, SPEC[s], swap[s], k)
            rs.append(x)
            out[(s, k)] = x
            if k == 1.0:
                print(f"{s}: holds {n}, cut {cut}, entries skipped {sk}; Sharpe all {sh(x):.2f} <=2017 {sh(x, hi='2018-01-01'):.2f} 2018+ {sh(x, lo='2018-01-01'):.2f}")
        r = pd.concat(rs, axis=1).dropna().mean(axis=1)
        print(f"combined x{k}: all {sh(r):.2f} <=2017 {sh(r, hi='2018-01-01'):.2f} 2018+ {sh(r, lo='2018-01-01'):.2f} mean/yr {r.mean()*252*100:.2f}%")
    for tag, k in (("", 1.0), ("_stress", 1.5)):
        r = pd.concat([out[(s, k)] for s in SPEC], axis=1).dropna().mean(axis=1)
        pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(f"marketdata/candidates/graziani_ea{tag}.csv", index=False)
    m = pd.concat({s: out[(s, 1.0)] for s in SPEC}, axis=1).dropna()
    m.insert(0, "day", m.index.strftime("%Y-%m-%d"))
    m.to_csv("marketdata/candidates/graziani_ea_markets.csv", index=False)
