"""The overnight drift (Boyarchenko, Larsen, Whelan, NY Fed Staff Report 917, 2020 / Review of Financial Studies).

S&P 500 e-mini futures earn 1.5 bp between 2:00 and 3:00 New York (European open) on 1998-2020, the only hour
that survives multiple-testing thresholds, and it comes from nights after a closing sell-off: order imbalance
over 15:15-16:15 is negative (Table VII), more so when the VIX is high (Table IV: 7-13 bp in the top VIX
tercile).  Table IX, 2004-2020: long 2:00-3:00 Sharpe 1.10 before costs and -0.54 after; long 1:30-3:30 1.30 and
0.26; 1:30-3:30 only after a negative close ("buy the dip") 1.78 and 1.10.  The effect follows London's clock
(Table VIII).  No order flow here, so the sign of the 15:15-16:15 return stands in for the imbalance.

    python research/overnight_drift.py

Result on histdata minute bars (2010-11 to 2026-10), not added to any EA:
  S&P 500: 2:00-3:00 earns 1.47 bp (t 4.3) to 2017, as in the paper, and 0.63 bp (t 1.8) from 2018; nothing in
           2021-2024.  1:30-3:30 earns 2.4 and 1.1 bp.  Every night after 1 bp: Sharpe 0.4 (1.0 to 2017, 0.1 from
           2018); after the paper's 1.7 bp it is zero.  London's clock gives the same numbers.
  The conditioning holds up: after a falling 15:15-16:15 the 1:30-3:30 return is 2.7 bp against 0.9 after a rising
           one, and in the top volatility tercile 4.5 bp (5.3 after a falling close) against 0.3 in the other two.
           But buy-the-dip after 1 bp is Sharpe 0.64 (1.17 to 2017, 0.30 from 2018) and high volatility only 0.85
           (1.30, 0.73) - the price proxy is weaker than the paper's order flow (1.1 after costs).
  DAX: data for these hours only from 2018, 1.5 bp (t 1.8).  Nikkei: 2.1 bp to 2017, 0.3 bp since.
  As a Hydra leg the best variant (high volatility, any close) moves the combined Sharpe from 3.01 to 3.08 and
           lowers it from 2018 (3.37 to 3.30-3.38) at any size that matters.  Not enough to earn a place.
"""
import numpy as np
import pandas as pd

from intraday_momentum import SPLIT, at, minutes
from overnight_intraday_reversal import NY, matrix, stats

LONDON = "Europe/London"
MARKETS = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0}
# name: (clock, in, out)
WINDOWS = {"OD 2:00-3:00 NY": (NY, "02:00", "03:00"), "OD+ 1:30-3:30 NY": (NY, "01:30", "03:30"),
           "1:00-4:00 NY": (NY, "01:00", "04:00"), "7:00-8:00 London": (LONDON, "07:00", "08:00"),
           "6:30-8:30 London": (LONDON, "06:30", "08:30")}
SIGNALS = {"15:15-16:15": ("15:15", "16:15"), "15:15-16:00": ("15:15", "16:00"), "15:45-16:00": ("15:45", "16:00"),
           "14:00-16:00": ("14:00", "16:00"), "9:30-16:00": ("09:30", "16:00")}
COSTS = (0.0, 1.0, 1.7)


def frame(symbol):
    """Per weekday: each window's log return, and what was known at the previous close - the return over each
    signal window and the tercile of 20-day volatility (0 low, 2 high)."""
    out = {}
    for name, (zone, a, b) in WINDOWS.items():
        days, p = matrix(symbol, zone)
        lp = np.log(p.astype(float))
        out[name] = pd.Series(at(lp, minutes(b)) - at(lp, minutes(a)), index=days)
    days, p = matrix(symbol, NY)
    lp = np.log(p.astype(float))
    week = days.dayofweek < 5
    r = pd.DataFrame(out).reindex(days[week])
    for name, (a, b) in SIGNALS.items():
        s = pd.Series(at(lp, minutes(b)) - at(lp, minutes(a)), index=days)[week]
        r[f"s {name}"] = s.shift(1)
    c = pd.Series(at(lp, minutes("16:00")), index=days)[week]
    vol = c.diff().rolling(20, min_periods=15).std()
    lo = vol.rolling(750, min_periods=250).quantile(1 / 3)
    hi = vol.rolling(750, min_periods=250).quantile(2 / 3)
    r["vol"] = ((vol > lo).astype(int) + (vol > hi).astype(int)).where(lo.notna()).shift(1)
    hours = pd.DataFrame({h: at(lp, minutes(f"{h:02d}:59")) - at(lp, minutes(f"{h:02d}:00")) for h in range(24)},
                         index=days)[week]
    return r, hours


def row(name, x):
    x = x.dropna()
    print(f"    {name:34s} all {stats(x)}   to 2017 {stats(x[:SPLIT])}   2018+ {stats(x[SPLIT:])}"
          f"   mean {x.mean() * 1e4:5.2f} / {x[:SPLIT].mean() * 1e4:5.2f} / {x[SPLIT:].mean() * 1e4:5.2f} bp"
          f"   n {len(x):4d}   win {(x > 0).mean() * 100:4.1f}%")


def traded(x, on, cost):
    """Daily series of a window traded only on the flagged days (zero otherwise), after the round-trip cost."""
    on = on.reindex(x.index).fillna(False).astype(bool)
    return ((x - cost * 1e-4) * on).where(x.notna())


if __name__ == "__main__":
    for s, cost in MARKETS.items():
        r, hours = frame(s)
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {cost} bp round trip")
        print("  hour (New York), mean bp (t):  all | to 2017 | 2018+      paper 2011-2020: 02-03 1.55 (4.65)")
        for h in range(24):
            cells = []
            for x in (hours[h], hours[h][:SPLIT], hours[h][SPLIT:]):
                x = x.dropna()
                cells.append(f"{x.mean() * 1e4:6.2f} ({x.mean() / x.std() * np.sqrt(len(x)):5.2f})")
            print(f"    {h:02d}-{(h + 1) % 24:02d}   " + "   ".join(cells))
        print("  every night, before costs")
        for w in WINDOWS:
            row(w, r[w])
        if s != "SPXUSD":
            continue
        print("  by year, bp a night:  " + "  ".join(
            f"{y} {x.mean() * 1e4:4.1f}" for y, x in r["OD+ 1:30-3:30 NY"].groupby(r.index.year)))
        for c in COSTS:
            print(f"  after {c} bp")
            for w in WINDOWS:
                row(f"{w}, every night", traded(r[w], r[w].notna(), c))
        for w in ("OD 2:00-3:00 NY", "OD+ 1:30-3:30 NY", "6:30-8:30 London"):
            print(f"  {w}: after a falling / rising close, before costs")
            for name in SIGNALS:
                sig = r[f"s {name}"]
                row(f"{name} < 0", r[w][sig < 0])
                row(f"{name} > 0", r[w][sig > 0])
            sig = r["s 15:15-16:15"]
            print(f"  {w}: by volatility tercile known at the close (0 low, 2 high), before costs")
            for v in (0, 1, 2):
                row(f"vol {v}, every night", r[w][r["vol"] == v])
                row(f"vol {v}, close < 0", r[w][(r["vol"] == v) & (sig < 0)])
                row(f"vol {v}, close > 0", r[w][(r["vol"] == v) & (sig > 0)])
            small = sig.abs().rolling(250, min_periods=60).median().shift(1)
            row("close < 0, larger than median", r[w][(sig < 0) & (sig.abs() > small)])
            for c in COSTS[1:]:
                print(f"  {w}: traded as a daily series after {c} bp")
                row("buy the dip (close < 0)", traded(r[w], sig < 0, c))
                row("dip, vol not low", traded(r[w], (sig < 0) & (r["vol"] >= 1), c))
                row("dip, vol high", traded(r[w], (sig < 0) & (r["vol"] == 2), c))
                row("vol high, any close", traded(r[w], r["vol"] == 2, c))
