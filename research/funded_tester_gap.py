"""Why the j3 base run (AurumFunded 1.03, legs off, 2024-01 to 2026-10) made +168% where the 2026-10-15 run made +110%.

The 2026-10-15 run was AurumFunded 1.00: cushion sizing capped at 1.0 (sizes only shrink near the final stop).
1.01 raised the cap to 1.4 (`InpPropCap`, room 8.5 = the final stop), so after +3.5% the legs trade 1.4 times their
size.  The day stop stayed at 3% of the initial balance, which shrinks as a share of equity while the account grows.

Daily leg results (marketdata/hydra_legs_daily.csv.gz, no grid, no gold hold) at size 0.5, sized on equity so the
result compounds like the EA.  Daily data cannot see an intraday dip, so the day-stop count is a lower bound.

    python research/funded_tester_gap.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
FLOOR, ROOM, LEAST, SIZE, DAYSTOP = 0.915, 0.085, 0.3, 0.5, 0.03


def walk(r, cap, daystop):
    eq, peak, dd, hits, worst, path = 1.0, 1.0, 0.0, [], 0.0, []
    for day, x in r.items():
        f = min(cap, max(LEAST, (eq - FLOOR) / ROOM)) if cap else 1.0
        pnl = eq * SIZE * f * x
        if daystop and pnl <= -DAYSTOP:
            pnl = -DAYSTOP
            hits.append(day.date())
        worst = min(worst, pnl / eq)
        eq += pnl
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        path.append(eq)
    return eq, dd, worst, hits, pd.Series(path, r.index)


def main():
    legs = pd.read_csv(CACHE, index_col=0, parse_dates=True).drop(columns=["grid", "hold"])
    r = legs.loc["2024-01-01":"2026-10-14"].sum(axis=1)
    print(f"{len(r)} days {r.index[0].date()} to {r.index[-1].date()}")
    print(f"{'case':<34}{'return':>9}{'max DD':>8}{'worst day':>11}{'day stops':>11}")
    for name, cap, ds in [("no cushion (size 0.5 flat)", None, False), ("cap 1.0 (v1.00), no day stop", 1.0, False),
                          ("cap 1.0 (v1.00), day stop 3%", 1.0, True), ("cap 1.4 (v1.01+), no day stop", 1.4, False),
                          ("cap 1.4 (v1.01+), day stop 3%", 1.4, True)]:
        eq, dd, worst, hits, path = walk(r, cap, ds)
        print(f"{name:<34}{(eq - 1) * 100:>8.1f}%{dd * 100:>7.1f}%{worst * 100:>10.2f}%{len(hits):>11}")
        if ds:
            print("   hits:", ", ".join(str(h) for h in hits) or "none")
            yearly = path.groupby(path.index.year).last()
            print("   year-end equity:", ", ".join(f"{y} {v:.2f}" for y, v in yearly.items()))
    # Legs on (job j3's compare run): breakout at 0.125% risk a trade, noise 0.275 per index, the weights of
    # tools/prop_candidates.py; the EA multiplies both by SizeMult(), so they get size 0.5 and the cushion too.
    c = pd.read_csv(CACHE.with_name("candidate_legs_daily.csv.gz"), index_col=0, parse_dates=True)
    c = c.reindex(r.index).fillna(0.0)
    on = r + c.breakout + 0.55 * c.noise
    print("legs on (breakout 0.125%, noise 0.275 per index):")
    for name, cap, ds in [("cap 1.0, no day stop", 1.0, False), ("cap 1.4, no day stop", 1.4, False),
                          ("cap 1.4, day stop 3%", 1.4, True)]:
        eq, dd, worst, hits, _ = walk(on, cap, ds)
        print(f"  {name:<32}{(eq - 1) * 100:>8.1f}%{dd * 100:>7.1f}%{worst * 100:>10.2f}%{len(hits):>11}")
    # Day stop as a share of equity once the account has grown.
    for e in (1.0, 1.5, 2.0, 2.7):
        print(f"equity {e:.1f}x: the 3% day stop is {DAYSTOP / e * 100:.2f}% of equity; at size 0.5 x 1.4 a leg day "
              f"of {DAYSTOP / e / (SIZE * 1.4) * 100:.2f}% (full size) reaches it")


if __name__ == "__main__":
    main()
