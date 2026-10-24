"""Belief check for near_miss_basket: each of the six rules, parameters unchanged, on other markets we hold.
Pre-registered before any result was seen: test markets per rule are fixed here, a rule stays only if its net
(real cost + 0.5 bp swap) full-sample Sharpe is > 0 on EVERY test market. No parameter is tuned per market.
FX rules -> EURUSD, GBPUSD, AUDUSD, USDCHF (own market removed, replaced by none); index rule -> GRXEUR, JPXJPY, XAUUSD.
Trials: 6 rules x 4 (or 3) markets = 21 member tests, logged as one trials line.
Survivors are rebuilt as the vol-scaled equal-weight basket (same recipe as near_miss_basket.py) on the original
markets (candidate csv) and on each test market (markets csv, one column a market, survivors' rules applied there).
Run: python research/near_miss_markets.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "research"))
import idea_engine as ie  # noqa: E402
from near_miss_basket import MEMBERS, TARGET, stream, sharpe  # noqa: E402

FX_TEST = ["EURUSD", "GBPUSD", "AUDUSD", "USDCHF"]
IDX_TEST = ["GRXEUR", "JPXJPY", "XAUUSD"]


def tests_for(sym):
    base = IDX_TEST if sym == "SPXUSD" else FX_TEST
    return [m for m in base if m != sym]


def basket(G, specs, mult=1.0):
    """specs: list of (sym, kind, params). Vol-scaled equal weight, divided by len(specs)."""
    tot = 0.0
    for sym, kind, p in specs:
        g, c = stream(G, sym, kind, p)
        vol = (g - c).rolling(60, min_periods=30).std().shift(1)
        k = (TARGET / vol).clip(upper=5.0).fillna(0.0)
        tot = tot + k * (g - mult * c) / len(specs)
    return tot


def main():
    G = ie.Grid()
    pre = np.asarray(G.pre)
    keep = []
    ntests = 0
    for sym, kind, p in MEMBERS:
        res = {}
        for m in tests_for(sym):
            g, c = stream(G, m, kind, p)
            n = g - c
            res[m] = (sharpe(n), sharpe(n[pre]), sharpe(n[~pre]))
            ntests += 1
        ok = all(v[0] > 0 for v in res.values())
        print(f"{sym:7s}{kind:9s}{str(p):32s}", "  ".join(f"{m}:{v[0]:5.2f}({v[1]:5.2f}/{v[2]:5.2f})" for m, v in res.items()),
              "KEEP" if ok else "DROP")
        if ok:
            keep.append((sym, kind, p))
    print("survivors:", [(s, k) for s, k, _ in keep], "member tests", ntests)
    if not keep:
        return
    out = basket(G, keep)
    st = basket(G, keep, 1.5)
    print(f"survivor basket Sharpe pre {sharpe(out[pre]):.2f} post {sharpe(out[~pre]):.2f}  1.5x {sharpe(st):.2f}"
          f"  1.5x pre/post {sharpe(st[pre]):.2f}/{sharpe(st[~pre]):.2f}")
    folder = ROOT / "marketdata" / "candidates"
    days = G.days.strftime("%Y-%m-%d")
    for suf, s in (("", out), ("_stress", st)):
        pd.DataFrame({"day": days, "r": s.values}).to_csv(folder / f"near_miss_basket{suf}.csv", index=False)
    # markets file: survivors' rules applied to each test market (swap the symbol, keep rules and parameters)
    cols = {"day": days}
    for m in FX_TEST + IDX_TEST:
        sp = [(m, k, p) for s, k, p in keep if m in tests_for(s) or m == s]
        # only rules whose own test list contains the market, keeps asset classes apart
        if not sp:
            continue
        b = basket(G, sp)
        cols[m] = b.values
        print(f"market {m:7s} rules {len(sp)} Sharpe {sharpe(b):5.2f} pre {sharpe(b[pre]):5.2f} post {sharpe(b[~pre]):5.2f}")
    pd.DataFrame(cols).to_csv(folder / "near_miss_basket_markets.csv", index=False)
    print("written near_miss_basket(.csv/_stress.csv/_markets.csv)")


if __name__ == "__main__":
    main()
