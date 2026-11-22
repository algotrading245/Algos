"""j15 step 16: research/hydra_t5b_months_model.py at the 4x target, on j15's 21 months (2024.01-2025.09).

Same model, same settings as j10b / j11b ("odds": target_odds' 21 weekdays, cap 20, history day vol; "preset":
AurumHydra_target4x_FTMO.set, 23 weekdays, cap 50, InpGoalDayVolPct 1.56), edge 1.0 and 0.7, each round from the
month's first weekday; only the goal (4x) and the tester run (backtests/2026-10-18_0755_AurumHydra_t4b_months) change.

The tester's month multiple is the final balance after the last fill, so a round that stopped at the goal can show
3.992x (2024.12: the log line says "ended, equity 40004.42 ... (4.00x, goal 4.0x)"); counts take 0.3% below a level
as reaching it, as in research/hydra_t3b_months_model.py.

    python research/hydra_t4b_months_model.py
"""
import numpy as np

import hydra_t5b_months_model as m

m.GOAL = 4.0
m.RUN = m.ROOT / "backtests" / "2026-10-18_0755_AurumHydra_t4b_months" / "months_result.json"
TOL = 0.997


def summary(x):
    x = np.asarray(x)
    return (np.mean(x >= 3 * TOL), np.mean(x >= 4 * TOL), np.mean(x >= 5 * TOL), np.mean(x <= m.RUIN + 1e-9),
            np.median(x))


m.summary = summary

if __name__ == "__main__":
    m.main()
    # m.main()'s base-rate line names P(3x) and P(5x); the 4x goal needs P(4x) and P(ruin) too
    r = m.daily()
    print("\nbase rate at the 4x goal, month-start rounds 2010 on (odds settings):")
    for edge in (1.0, 0.7):
        rr = r - (1.0 - edge) * r.mean()
        ends = [m.one_round(g.to_numpy(), 21, 20.0, rr.std()) for _, g in rr.groupby(rr.index.to_period("M"))
                if len(g) >= 15]
        s = summary(ends)
        print(f"  edge {edge}: {len(ends)} months, P(4x) {100 * s[1]:.1f}%, P(3x) {100 * s[0]:.1f}%, "
              f"P(ruin) {100 * s[3]:.1f}%, median {s[4]:.2f}x")
