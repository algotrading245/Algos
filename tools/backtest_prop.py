"""Prop-firm challenge simulator on the daily returns of the Hydra legs.

A challenge is a sequence of phases, each with a profit target, and two loss limits that hold throughout: a
daily loss and a maximum loss, both in % of the initial balance.  The maximum loss is either static (equity may
not fall below 100 - max) or trails the highest end-of-day balance.  Positions are sized on the initial balance,
so the account's daily result is `scale` times the sum of the chosen legs, in % of the initial balance.  The EA's
own daily stop (`guard`) flattens the day at that loss; a day that would have lost more than the guard is booked
at the guard times `slip`.  A challenge is started on every trading day of the history and walked forward until
it passes, breaches a limit or runs for `limit` days.

Daily data only: a day that dips below a limit and recovers before the close is not seen, so the pass rates are
an upper bound.  The legs come from tools/backtest_hydra.py (see `legs`), cached in marketdata/hydra_legs_daily.

    python tools/backtest_prop.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
SPLIT = "2018-01-01"
# name: (phase targets %, daily loss %, maximum loss %, trailing)
RULES = {"2-step 10/5, 5 daily, 10 static": ((10.0, 5.0), 5.0, 10.0, False),
         "2-step 8/5, 5 daily, 10 static": ((8.0, 5.0), 5.0, 10.0, False),
         "1-step 10, 3 daily, 6 static": ((10.0,), 3.0, 6.0, False),
         "1-step 10, 3 daily, 10 trailing": ((10.0,), 3.0, 10.0, True)}
SETS = {"all eight": None, "no grid": ("grid",), "no grid, no hold": ("grid", "hold"),
        "no quartet": ("quartet",), "quartet only": ("grid", "hold", "fix", "cross", "fall", "morning", "after")}


def legs():
    """Daily returns of the eight Hydra legs at the EA's default sizes, as fractions of the balance."""
    if CACHE.exists():
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    import backtest_hydra as B
    h = B.hourly()
    f = pd.DataFrame({"quartet": B.quartet(0.67, 0.80),
                      "grid": 0.035 * B.grid(h.AUDCAD, 5, 1.0, 4, 1.8, 1.0, swap=(0.42, -0.95)),
                      "hold": B.hold(h.XAUUSD, 0.107, 0.068), "fix": B.fix(0.005, cost=1.2),
                      "cross": B.fix(0.005, cost=2.0, pairs=B.FIXCROSS, name="HYDRA_FIXX", after=False),
                      "fall": B.fall(0.005, cost=1.2), "morning": B.morning(0.005),
                      "after": B.after(0.01)}).loc["2010-06-01":].fillna(0.0)
    f.to_csv(CACHE)
    return f


def challenge(x, start, targets, daily, most, trailing, guard, slip=1.2, limit=500):
    """Walk one challenge from day `start` of the daily results `x` (% of initial balance).  Returns
    (outcome, days): outcome 1 passed, -1 daily loss breached, -2 maximum loss breached, 0 still open."""
    day = start
    for target in targets:
        equity = peak = 0.0
        while True:
            if day >= len(x) or day - start >= limit:
                return 0, day - start
            r = x[day]
            day += 1
            if guard and r < -guard:
                r = -guard * slip
            if r <= -daily:
                return -1, day - start
            equity += r
            peak = max(peak, equity)
            if equity <= (peak if trailing else 0.0) - most:
                return -2, day - start
            if equity >= target:
                break
    return 1, day - start


def run(x, rule, guard, every=1, **kw):
    targets, daily, most, trailing = RULES[rule] if isinstance(rule, str) else rule
    out = [challenge(x, s, targets, daily, most, trailing, guard, **kw) for s in range(0, len(x) - 20, every)]
    o, d = np.array([a for a, _ in out]), np.array([b for _, b in out])
    done = o != 0
    return {"pass": (o[done] == 1).mean() * 100, "daily": (o[done] == -1).mean() * 100,
            "max": (o[done] == -2).mean() * 100, "open": (~done).mean() * 100,
            "days": np.median(d[o == 1]) if (o == 1).any() else np.nan,
            "p90": np.quantile(d[o == 1], 0.9) if (o == 1).any() else np.nan}


def cell(k):
    return (f"pass {k['pass']:5.1f}%  daily {k['daily']:4.1f}%  max {k['max']:4.1f}%  "
            f"days {k['days']:4.0f} (90%: {k['p90']:4.0f})")


def funded(x, daily, most, trailing, guard, slip=1.2, months=12):
    """A funded account started on every day: share still alive after `months` months, and the mean profit paid
    out over that time in % of the balance (profits withdrawn monthly, losses carried)."""
    alive, paid = [], []
    for s in range(0, len(x) - 21 * months, 5):
        equity = peak = out = 0.0
        ok = True
        for i, r in enumerate(x[s:s + 21 * months]):
            if guard and r < -guard:
                r = -guard * slip
            equity += r
            peak = max(peak, equity)
            if r <= -daily or equity <= (peak if trailing else 0.0) - most:
                ok = False
                break
            if i % 21 == 20 and equity > 0:
                out, equity, peak = out + equity, 0.0, 0.0
        alive.append(ok)
        paid.append(out)
    return np.mean(alive) * 100, np.mean(paid)


if __name__ == "__main__":
    f = legs() * 100
    sh = lambda y: y.mean() / y.std() * np.sqrt(252)
    for name, drop in SETS.items():
        b = f.drop(columns=list(drop or ())).sum(axis=1)
        print(f"\n=== {name}: Sharpe {sh(b):.2f} ({sh(b[:SPLIT]):.2f} to 2017, {sh(b[SPLIT:]):.2f} from 2018), "
              f"vol {b.std() * np.sqrt(252):.1f}% a year, worst day {b.min():.2f}% at scale 1")
        for rule, (targets, daily, most, trailing) in RULES.items():
            print(f"  {rule}")
            for scale in (0.15, 0.25, 0.35, 0.5, 0.7, 1.0):
                x = (b * scale).to_numpy()
                guard = daily * 0.6
                k, a, c = run(x, rule, guard), run(b[:SPLIT].to_numpy() * scale, rule, guard), \
                    run(b[SPLIT:].to_numpy() * scale, rule, guard)
                live, paid = funded(x, daily, most, trailing, guard)
                print(f"    scale {scale:4.2f}  {cell(k)}   to 2017 {a['pass']:5.1f}%  2018+ {c['pass']:5.1f}%   "
                      f"funded 12m: alive {live:5.1f}%  paid {paid:5.1f}%")
