"""The holdout: the last 12 months of data, which the agents never see while they improve the EAs.

    START = first day of the holdout.  Research tools call drop(series) on their daily data; in an agent run
    (AURUM_AGENT=1, set by tools/autopilot/run-agent.ps1) tools/run-tester.ps1 refuses a -To on or after START and
    tools/run-months.ps1 a -ToMonth after END_MONTH (both read the two values from this file).

Only the owner opens it, once, for a final judgment (python tools/holdout_check.py), and a result seen there is not
tuned on.  Moving START forward later re-hides nothing that was already seen: only move it at a planned review.
"""
import pandas as pd

START = pd.Timestamp("2025-10-13")
END_MONTH = "2025.09"   # last month the tester jobs of the agents may run


def drop(x):
    """`x` (indexed by date) without the holdout."""
    return x[x.index < START]


def month_ok(month):
    """True when a tester month 'YYYY.MM' lies before the holdout."""
    return month <= END_MONTH
