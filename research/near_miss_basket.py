"""Near-miss basket: six specs from docs/ideas/near_miss.jsonl (both halves Sharpe > 0.3, failed a gate).
Rebuild each best variant's daily net stream with the idea engine's own rule code (real costs, 0.5 bp swap),
scale each to a 10% annual target vol using a past-only 60-day realised vol (shifted one day), equal-weight them.
Pre-registered: primary = vol-scaled equal weight (candidate near_miss_basket). Secondary = raw equal weight,
reported only (2 weightings = 2 trials, plus the 21 member variants already counted by the engine).
Members were chosen by the engine's rule (both halves fair), not by the late half.
Run: python research/near_miss_basket.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import idea_engine as ie  # noqa: E402

MEMBERS = [
    ("USDJPY", "tsmom", {"lookback": 60}),
    ("USDJPY", "donchian", {"lookback": 55}),
    ("NZDCAD", "meanrev", {"lookback": 10, "z": 1.5}),
    ("AUDCAD", "rsi", {"level": 30, "period": 14}),
    ("SPXUSD", "rsi", {"level": 10, "period": 2}),
    ("USDCAD", "rsi", {"level": 30, "period": 2}),
]
TARGET = 0.10 / np.sqrt(252)


def stream(G, sym, kind, p):
    c = ie.daily_close(G, sym)
    r = np.nan_to_num(np.diff(c, prepend=np.nan))
    w = ie.rule_signal(kind, c, p)
    gross = w * r
    cost = np.abs(np.diff(w, prepend=0.0)) * ie.cost_of(sym) / 2 + np.abs(w) * ie.SWAP_BP * 1e-4
    return pd.Series(gross, index=G.days), pd.Series(cost, index=G.days)


def sharpe(x):
    x = np.asarray(x)
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def main():
    G = ie.Grid()
    pre = np.asarray(G.pre)
    out = {"": 0.0, "_stress": 0.0}
    raw = {"": 0.0, "_stress": 0.0}
    for sym, kind, p in MEMBERS:
        g, c = stream(G, sym, kind, p)
        net = g - c
        # past-only vol: std of the member's own net stream over 60 days, known the day before
        vol = net.rolling(60, min_periods=30).std().shift(1)
        k = (TARGET / vol).clip(upper=5.0).fillna(0.0)
        for suf, m in (("", 1.0), ("_stress", 1.5)):
            n = g - m * c
            out[suf] = out[suf] + k * n / len(MEMBERS)
            raw[suf] = raw[suf] + n / len(MEMBERS)
        print(f"{sym:7s}{kind:9s} Sharpe pre {sharpe((g - c)[pre]):5.2f} post {sharpe((g - c)[~pre]):5.2f}")
    for name, d in (("vol-scaled", out), ("raw", raw)):
        s = d[""]
        print(f"{name:11s} basket Sharpe pre {sharpe(s[pre]):.2f} post {sharpe(s[~pre]):.2f}  1.5x {sharpe(d['_stress']):.2f}"
              f"  1.5x pre/post {sharpe(d['_stress'][pre]):.2f}/{sharpe(d['_stress'][~pre]):.2f}")
    folder = ROOT / "marketdata" / "candidates"
    for suf in ("", "_stress"):
        pd.DataFrame({"day": G.days.strftime("%Y-%m-%d"), "r": out[suf].values}).to_csv(
            folder / f"near_miss_basket{suf}.csv", index=False)
    print("written near_miss_basket(.csv/_stress.csv)")


if __name__ == "__main__":
    main()
