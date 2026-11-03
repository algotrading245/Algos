"""Cross-session momentum in gold and silver: does one trading session's return predict the next session's?

Idea from the title and abstract of W. Wei, "Who Moves the Price? Trading-Session Return Decomposition and
Cross-Session Momentum in Gold and Silver Markets" (SSRN 7257240, 2026); the paper itself could not be read (SSRN
blocks this environment), so this is a plain test of the idea, with session bounds fixed in advance and no tuning.

Sessions on the New York clock from the half-hour bid closes of research/atlas_scan.py (server = New York + 7, a
server day runs 17:00-17:00 New York): Asia 18:00-03:00, London 03:00-08:00, New York 08:00-17:00.  Rule: take the
sign of the previous session's return (or of the previous two sessions together) and hold it through the next
session; also the sign of the previous whole day for each session.  Costs per round trip: gold 1 bp, silver 4 bp
(CFD spreads).  Split: to 2017 and 2018 on.

    python research/cross_session_metals.py

Result (2026-10-15): rejected.  Gold, best rule New York <- sign(Asia + London): gross Sharpe 0.45 (t 1.9; to 2017
0.07, 2018+ 0.84, 2023+ 1.48), after 1 bp 0.23 (-0.14 to 2017): it works only in the 2023-26 rally, where the
sign of the morning is mostly long.  New York <- London 0.17 net, London <- Asia -0.07 net, the overnight and
previous-day rules negative (London <- previous day reverses, -0.68 net).  Silver after 4 bp: all negative.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_scan import half  # noqa: E402

COST = {"XAUUSD": 1.0, "XAGUSD": 4.0}
# half-hour column index on the server day: 0 = 17:00-17:30 New York
B = {"asia_open": 2, "london_open": 20, "ny_open": 30, "close": 47}


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    data, days = half()
    for s, c in COST.items():
        M = pd.DataFrame(data[s]).ffill(axis=1).to_numpy(dtype=float)
        a, lo, ny, cl = (M[:, B[k]] for k in ("asia_open", "london_open", "ny_open", "close"))
        prev_cl = np.r_[np.nan, cl[:-1]]
        R = pd.DataFrame({"asia": lo / a - 1, "london": ny / lo - 1, "ny": cl / ny - 1,
                          "day": cl / prev_cl - 1}, index=days)
        R = R[(R.index.dayofweek < 5)].replace([np.inf, -np.inf], np.nan)
        R = R[R.abs().max(axis=1) < 0.2]
        prevny = R.ny.shift(1)
        prevday = R.day.shift(1)
        rules = {
            "London <- Asia": (np.sign(R.asia), R.london),
            "NY <- London": (np.sign(R.london), R.ny),
            "NY <- Asia+London": (np.sign(R.asia + R.london), R.ny),
            "Asia <- previous NY": (np.sign(prevny), R.asia),
            "Asia <- previous day": (np.sign(prevday), R.asia),
            "London <- previous day": (np.sign(prevday), R.london),
            "NY <- previous day": (np.sign(prevday), R.ny),
        }
        print(s)
        for name, (sig, ret) in rules.items():
            for k, cost in (("gross", 0.0), ("net", c)):
                x = (sig * ret - cost * 1e-4 * (sig != 0)).dropna()
                t = x.mean() / x.std() * np.sqrt(len(x))
                print(f"  {name:24s} {k:5s} Sharpe {sharpe(x):+.2f} (to 2017 {sharpe(x[:'2017']):+.2f}, 2018+ "
                      f"{sharpe(x['2018':]):+.2f}, 2023+ {sharpe(x['2023':]):+.2f})  {x.mean() * 1e4:+.2f} bp/day  t {t:+.1f}")
