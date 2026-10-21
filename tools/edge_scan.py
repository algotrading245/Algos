"""Edge search by brute force with honest bookkeeping: tries every simple rule of a few families on every instrument,
picks rules on the days before 2018 only, keeps the ones that still work from 2018 after costs (and at 1.5x costs),
and hands each survivor to the fixed gates (tools/gates.py) as marketdata/candidates/<id>.csv (+ _stress.csv).

    python tools/edge_scan.py                       # all families, write the 5 best survivors, log the search
    python tools/edge_scan.py --family slot --top 3
    python tools/edge_scan.py --dry-run             # print only: no candidates written, no trial logged

Families (all on the half-hour bid grid, half-hours 3-46 only, see FIRST/LAST of research/atlas_scan.py, server day = 17:00 to 17:00 New York):
  slot   hold one instrument from half-hour a for L half-hours every day, long or short (time-of-day drift)
  own    the same window, but only on the day after the instrument's own unusually large move (top 15% of its last
         250 days), in the direction of that move or against it (continuation / reversal)
  cal    the same window on one weekday only (mon..fri), or on the first / last two trading days of the month
         (turn-of-month flows: pension and index rebalancing, month-end fixings)
  vol    the same window only when the instrument's 20-day realized volatility is in the top or bottom third of its
         last 250 days (known the day before): drifts that exist in one volatility regime only
Cross-instrument conditions are research/atlas_scan.py's family; they are not repeated here.

Every rule looked at counts as a trial: the whole search is logged as one line of docs/trials.jsonl with "count" =
the number of rules, so the gates' Deflated Sharpe bar rises with it (gates.trials_logged sums the counts). A big
search therefore makes every later candidate harder to pass; that is the price of searching, not a bug.
A survivor here is a candidate, not an edge: it still has to pass gates.py (halves, costs, DSR, correlation with the
Hydra legs, goal), and an idea that passes still needs a reason (a paper read in full, a known flow) before an EA.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
from atlas_scan import COST, close, half  # noqa: E402  (the shared half-hour grid and cost table)
sys.path.insert(0, str(ROOT / "tools"))
from holdout import START as HOLDOUT_START  # noqa: E402

CANDIDATES = ROOT / "marketdata" / "candidates"
TRIALS = ROOT / "docs" / "trials.jsonl"
LENS = (2, 4, 8)                       # hold, in half-hours
CUT = np.datetime64("2018-01-01")
T_TRAIN = 4.0                          # |t| needed before 2018 to be picked (about 0.006% by chance per rule)
T_TEST = 2.0                           # t needed from 2018, same side
MIN_TRADES = 200                       # trades from 2018 (metals' first half-hours are mostly empty)
# Windows run from half-hour 3 (18:30 New York) to half-hour 46 (16:30). The data is bid only, and the spread widens
# around the 17:00 rollover: the bid falls into it and climbs back after, which a first scan read as t = 20-30
# "drift" (short into 17:00, long out of it) that no one can trade.
FIRST, LAST = 3, 46
FAMILIES = ("slot", "own", "cal", "vol")
SKIP = {"SPXUSD", "GRXEUR", "JPXJPY", "WTIUSD"}   # index and oil CFDs: histdata bid only, costs not in the table


def tstat(x):
    n = (~np.isnan(x)).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nanmean(x, axis=0) / np.nanstd(x, axis=0) * np.sqrt(n), n


def big_move(P, s, q=0.85):
    """+1/-1 on the day after an unusually large daily move of s, else 0 (the same rule as atlas_scan.signals)."""
    r = pd.Series(np.diff(np.log(close(P[s])), prepend=np.nan))
    a = r.abs()
    big = a >= a.rolling(250, min_periods=120).quantile(q).shift(1)
    return pd.Series(np.where(big, np.sign(r), 0.0)).shift(1).fillna(0.0).to_numpy()


def calendar(days):
    """1/0 masks: one per weekday, and the first / last two trading days of each month."""
    d = pd.Series(days)
    month = d.dt.to_period("M")
    k = d.groupby(month).cumcount()
    n = d.groupby(month).transform("size")
    out = {f"cal_{w}": (d.dt.dayofweek == i).astype(float).to_numpy()
           for i, w in enumerate(("mon", "tue", "wed", "thu", "fri"))}
    out["cal_tomfirst"] = (k < 2).astype(float).to_numpy()
    out["cal_tomlast"] = (k >= n - 2).astype(float).to_numpy()
    return out


def vol_regime(P, s):
    """1/0 masks for days whose prior-day 20-day realized vol is in the top / bottom third of its last 250 days."""
    r = pd.Series(np.diff(np.log(close(P[s])), prepend=np.nan))
    v = r.rolling(20, min_periods=15).std()
    hi = v >= v.rolling(250, min_periods=120).quantile(2 / 3)
    lo = v <= v.rolling(250, min_periods=120).quantile(1 / 3)
    return {"vol_high": hi.shift(1, fill_value=False).astype(float).to_numpy(),
            "vol_low": lo.shift(1, fill_value=False).astype(float).to_numpy()}


def scan(families):
    P, days = half()
    tr = days.to_numpy() < CUT
    seen = days.to_numpy() < np.datetime64(HOLDOUT_START)   # the owner's holdout is never looked at
    cal = calendar(days) if "cal" in families else {}
    found, tried = [], 0
    for y in sorted(set(P) - SKIP):
        lp = np.log(P[y].astype(np.float64))
        c = COST.get(y, 1.5) * 1e-4
        conds = {}
        if "slot" in families:
            conds["slot"] = np.ones(len(days))
        if "own" in families:
            conds["own"] = big_move(P, y)
        conds.update(cal)
        if "vol" in families:
            conds.update(vol_regime(P, y))
        for fam, sg in conds.items():
            for L in LENS:
                starts = np.arange(FIRST, LAST + 1 - L)
                R = lp[:, starts + L] - lp[:, starts]
                X = np.where(sg[:, None] != 0, sg[:, None] * R, np.nan)
                tried += X.shape[1]
                t1, _ = tstat(X[tr])
                for a in np.flatnonzero(np.abs(np.nan_to_num(t1)) >= T_TRAIN):
                    side = float(np.sign(t1[a]))
                    g = side * X[:, a]
                    test = g[~tr & seen]
                    t2 = np.nanmean(test) / np.nanstd(test) * np.sqrt((~np.isnan(test)).sum())
                    net, stress = np.nanmean(test) - c, np.nanmean(test) - 1.5 * c
                    if t2 < T_TEST or stress <= 0 or (~np.isnan(test)).sum() < MIN_TRADES:
                        continue
                    kind = ("follow" if side > 0 else "fade") if fam == "own" else ("long" if side > 0 else "short")
                    found.append({"id": f"scan_{fam}_{y}_s{starts[a]}_L{L}_{kind}", "family": fam.split("_")[0],
                                  "symbol": y,
                                  "slot": int(starts[a]), "len": L, "side": side, "t_train": float(abs(t1[a])),
                                  "t_test": float(t2), "bp_test_net": 1e4 * net, "bp_test_stress": 1e4 * stress,
                                  "trades_test": int((~np.isnan(test)).sum()), "series": g, "cost": c})
    return found, tried, days


def write(c, days):
    """Daily return at 1x notional on the days the rule trades (0 otherwise), at the real and at 1.5x the cost."""
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    keep = days < HOLDOUT_START
    g = c["series"][keep]
    on = ~np.isnan(g)
    for suffix, k in (("", 1.0), ("_stress", 1.5)):
        r = np.where(on, np.nan_to_num(g) - k * c["cost"], 0.0)
        pd.DataFrame({"day": days[keep].strftime("%Y-%m-%d"), "r": r}).to_csv(
            CANDIDATES / f"{c['id']}{suffix}.csv", index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", action="append", choices=FAMILIES, help="default: all")
    ap.add_argument("--top", type=int, default=5, help="survivors to write as candidates (best t from 2018)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    families = a.family or list(FAMILIES)
    found, tried, days = scan(families)
    found.sort(key=lambda c: -c["t_test"])
    print(f"rules tried {tried}; picked before 2018 and still positive from 2018 at 1.5x cost: {len(found)}")
    print(f"chance alone: about {tried * 6.3e-5:.1f} rules reach |t| >= {T_TRAIN} before 2018")
    cols = ["id", "t_train", "t_test", "bp_test_net", "bp_test_stress", "trades_test"]
    if found:
        print(pd.DataFrame(found)[cols].round(2).to_string(index=False))
    if a.dry_run:
        return
    for c in found[:a.top]:
        write(c, days)
        print(f"wrote marketdata/candidates/{c['id']}.csv; next: python tools/gates.py {c['id']}")
    with TRIALS.open("a") as f:
        f.write(json.dumps({"id": "edge_scan:" + "+".join(families), "when": datetime.now().isoformat(timespec="seconds"),
                            "verdict": f"{len(found)} survivors, {min(len(found), a.top)} written",
                            "count": tried}) + "\n")
    print(f"logged {tried} trials in docs/trials.jsonl")


if __name__ == "__main__":
    main()
