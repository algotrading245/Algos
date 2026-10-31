"""What the book lacks: the gap list the finder aims at and the portfolio manager reviews (owner 2026-10-22).

    python tools/gaps.py            # prints the gaps and writes docs/gaps.json
    python tools/gaps.py --quiet    # writes docs/gaps.json only

For each leg in the book (tools/book_sim.py) it gives the market, style and holding period (LEG_TAGS below), the
Sharpe from 2018, the leg's current weight, its correlation with the rest of the book and what the book loses without
it.  Then the gaps: FTMO markets with no leg, styles with no leg, holding periods with too few legs, and the book's
losing months from 2018 (a new leg that made money in those months helps most).  Nothing on or after the holdout.

A new leg needs a tag here before it shows up as covering a gap; an untagged leg is listed as such.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import book_sim  # noqa: E402

OUT = ROOT / "docs" / "gaps.json"

# market groups as traded on FTMO (docs/memory/mission.md), styles and holding periods we want covered
MARKETS = ["gold", "usdjpy", "eurusd", "dollar pairs", "yen crosses", "aud/cad", "us indices"]
STYLES = ["trend", "mean reversion", "breakout", "calendar / flow", "carry", "volatility premium", "cross-asset reaction",
          "intraday momentum", "seasonal session"]
HORIZONS = ["intraday", "days", "weeks+"]

LEG_TAGS = {
    "quartet": {"markets": ["gold"], "style": "seasonal session", "horizon": "intraday"},
    "grid": {"markets": ["aud/cad"], "style": "mean reversion", "horizon": "days"},
    "hold": {"markets": ["gold"], "style": "trend", "horizon": "weeks+"},
    "fix": {"markets": ["dollar pairs"], "style": "calendar / flow", "horizon": "intraday"},
    "cross": {"markets": ["yen crosses", "dollar pairs"], "style": "calendar / flow", "horizon": "intraday"},
    "fall": {"markets": ["dollar pairs"], "style": "cross-asset reaction", "horizon": "intraday"},
    "morning": {"markets": ["yen crosses"], "style": "cross-asset reaction", "horizon": "intraday"},
    "after": {"markets": ["dollar pairs"], "style": "calendar / flow", "horizon": "intraday"},
    "breakout": {"markets": ["usdjpy"], "style": "breakout", "horizon": "intraday"},
    "noise": {"markets": ["us indices"], "style": "intraday momentum", "horizon": "intraday"},
    "drift": {"markets": ["us indices"], "style": "calendar / flow", "horizon": "days"},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    L = book_sim.legs()
    book, W = book_sim.combine(L)
    managed = book_sim.risk_layer(book)
    since = L.index >= book_sim.SPLIT
    full = book_sim.sharpe(managed[managed.index >= book_sim.SPLIT])

    rows = []
    for k in L:
        rest, _ = book_sim.combine(L.drop(columns=[k]))
        rest_m = book_sim.risk_layer(rest)
        x = L[k][since].dropna()
        corr = float(x.corr(rest.reindex(x.index))) if len(x) > 20 else float("nan")
        tag = LEG_TAGS.get(k, {"markets": [], "style": "untagged", "horizon": "untagged"})
        rows.append({"leg": k, **tag, "sharpe_2018": round(book_sim.sharpe(x), 2),
                     "weight_now": round(float(W[k].iloc[-1]), 3), "corr_rest": round(corr, 2),
                     "book_without": round(book_sim.sharpe(rest_m[rest_m.index >= book_sim.SPLIT]), 2)})

    covered_m = {m for r in rows for m in r["markets"]}
    covered_s = {r["style"] for r in rows}
    per_h = {h: sum(r["horizon"] == h for r in rows) for h in HORIZONS}
    risk_m = {m: round(sum(r["weight_now"] / max(len(r["markets"]), 1) for r in rows if m in r["markets"]), 3)
              for m in MARKETS}
    month = managed[managed.index >= book_sim.SPLIT].groupby(managed.index[managed.index >= book_sim.SPLIT]
                                                              .to_period("M")).sum()
    losing = [{"month": str(p), "book_pct": round(float(v) * 100, 2)} for p, v in month.items() if v < 0]

    gaps = {
        "markets_without_leg": [m for m in MARKETS if m not in covered_m],
        "styles_without_leg": [s for s in STYLES if s not in covered_s],
        "thin_horizons": [h for h, n in per_h.items() if n <= 1],
        "crowded_markets": [m for m, w in risk_m.items() if w > 0.35],
        "untagged_legs": [r["leg"] for r in rows if r["style"] == "untagged"],
    }
    out = {"when": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%S"), "ends": str(L.index[-1].date()),
           "book_sharpe_2018": round(full, 2), "legs": rows, "risk_by_market": risk_m, "legs_by_horizon": per_h,
           "gaps": gaps, "losing_months_2018": losing,
           "aim": "Queue ideas that fill a gap (a market, style or horizon with no leg), made money in the losing "
                  "months, and are likely to have corr <= 0.30 with the book. A leg that only repeats a crowded "
                  "market or style rarely lifts the book by the 0.03 the gate needs."}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    if a.quiet:
        return
    print(f"book Sharpe from 2018 (risk layer on): {full:.2f}, data to {out['ends']}")
    print(f"{'leg':10} {'style':22} {'horizon':9} {'S2018':>6} {'w':>6} {'corr':>5} {'book w/o':>8}")
    for r in rows:
        print(f"{r['leg']:10} {r['style'][:22]:22} {r['horizon']:9} {r['sharpe_2018']:6.2f} {r['weight_now']:6.3f} "
              f"{r['corr_rest']:5.2f} {r['book_without']:8.2f}")
    for k, v in gaps.items():
        print(f"{k}: {', '.join(v) if v else '-'}")
    print("risk by market now: " + ", ".join(f"{m} {w:.0%}" for m, w in risk_m.items()))
    print(f"losing months from 2018: {len(losing)} of {len(month)}: "
          + ", ".join(f"{m['month']} {m['book_pct']}%" for m in losing))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
