"""j11b step 16: research/hydra_t5b_months_model.py at the 3x target, on j11b's 21 months (2024.01-2025.09).

Same model, same settings ("odds": target_odds' 21 weekdays, cap 20, history day vol; "preset":
AurumHydra_target3x_FTMO.set, 23 weekdays, cap 50, InpGoalDayVolPct 1.56), edge 1.0 and 0.7, each round from the
month's first weekday; only the goal (3x) and the tester run (backtests/2026-10-18_0601_AurumHydra_t3b_months) change.

The tester's month multiple is the final balance, so a round that stopped at the goal shows 2.999x after the last
fill; counts here take 0.3% below a level as reaching it (the model is capped at the goal exactly, so it is unaffected).

    python research/hydra_t3b_months_model.py
"""
import numpy as np

import hydra_t5b_months_model as m

m.GOAL = 3.0
m.RUN = m.ROOT / "backtests" / "2026-10-18_0601_AurumHydra_t3b_months" / "months_result.json"
TOL = 0.997


def summary(x):
    x = np.asarray(x)
    return (np.mean(x >= 3 * TOL), np.mean(x >= 4 * TOL), np.mean(x >= m.GOAL * TOL), np.mean(x <= m.RUIN + 1e-9),
            np.median(x))


m.summary = summary

if __name__ == "__main__":
    m.main()
