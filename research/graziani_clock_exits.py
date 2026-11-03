"""Lesson 21 check, part 2, for the month-reversal leg: the Strategy Tester closes everything (CloseEverything) on every
day the clock check fails. In the tester with InpEuClock, ClockOk() is false when EU and US summer time differ
(AurumFunded.mq5:291-299): from the 2nd Sunday of March to the last Sunday of March and from the last Sunday of October
to the 1st Sunday of November. That is what closed both index holds at 2024.10.28 00:05 in j19 (log: "no trading today,
European and US summer time differ", then the 10018 close retries).
Model: same signal and holds as research/graziani_reversal.py (variant 0); a hold is cut at the close before the first
gap day inside it (exit cost = half spread), an entry on a gap day is skipped (the leg never opens). Reports Sharpe and
the cut / skipped counts against the plain leg. Live is not affected (ClockOk tests the real server offset there).
Run: python research/graziani_clock_exits.py
"""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "research")
import graziani_reversal as g


def sunday(y, m, n):
    d = pd.Timestamp(y, m, 1)
    s = d + pd.Timedelta(days=(6 - d.dayofweek) % 7)
    if n > 0:
        return s + pd.Timedelta(days=7 * (n - 1))
    e = d + pd.offsets.MonthEnd(0)
    return e - pd.Timedelta(days=(e.dayofweek + 1) % 7)


def gap(day):
    y = day.year
    return (sunday(y, 3, 2) <= day < sunday(y, 3, -1)) or (sunday(y, 10, -1) <= day < sunday(y, 11, 1))


def run(c, spread_bp, swap_bp, k=1.0, clock=True):
    idx = c.index
    ret = c.pct_change().fillna(0.0)
    per = idx.to_period("M")
    months = per.unique()
    pos = pd.Series(0.0, index=idx)
    cost = pd.Series(0.0, index=idx)
    n = cut = skipped = 0
    for i in range(len(months) - 1):
        a = np.where(per == months[i])[0]
        b = np.where(per == months[i + 1])[0]
        if len(a) < 15 or len(b) < 15:
            continue
        fr = [j for j in a if idx[j].dayofweek == 4]
        if len(fr) < 4 or not c.iloc[a[-1]] / c.iloc[fr[3]] - 1 < 0:
            continue
        e, x = a[-1], b[-1]
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
        cost.iloc[e] += k * spread_bp * 1e-4 / 2
        cost.iloc[x] += k * spread_bp * 1e-4 / 2
        for j in range(e, x):
            cost.iloc[j] += k * swap_bp * 1e-4 * (3.0 if idx[j].dayofweek == 4 else 1.0)
        n += 1
    return ret * pos - cost, n, cut, skipped


if __name__ == "__main__":
    px = {s: g.daily(s) for s in g.SPEC}
    swap = {}
    for s, c in px.items():
        sp = g._SP[g._MAP[s]]
        swap[s] = abs(sp["swap_long"]) * sp["point"] / c.iloc[-1] * 1e4
    for clock in (False, True):
        for k in (1.0, 1.5):
            rs = []
            for s, c in px.items():
                x, n, cut, sk = run(c, g.SPEC[s], swap[s], k, clock)
                rs.append(x)
                if k == 1.0:
                    print(f"clock={clock} {s}: holds {n}, cut {cut}, entries skipped {sk}")
            r = pd.concat(rs, axis=1).dropna().mean(axis=1)
            print(f"clock={clock} x{k} combined: Sharpe all {g.sh(r):.2f} <=2017 {g.sh(r, hi='2018-01-01'):.2f} "
                  f"2018+ {g.sh(r, lo='2018-01-01'):.2f}; 2024.01-2025.09 sum {r[(r.index >= '2024-01-01')].sum()*100:.2f}%")
