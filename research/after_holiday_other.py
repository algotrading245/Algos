"""Does the after-holiday leg of Hydra carry over to other currencies' holidays?

Hydra's `after` leg (tools/backtest_hydra.py) is long the dollar through the London morning of the first weekday
after a US federal holiday, read as settlement demand for dollars that could not settle on the holiday.  The same
reading predicts demand for yen after a Japanese holiday and for sterling after an English bank holiday.  Tested
here on the half-hour bid closes of research/atlas_scan.py (server clock = New York + 7): the trigger is the first
weekday after a holiday that is not itself a holiday of that country nor a US holiday; windows fixed in advance -
London morning, server 9:00-15:00 (the after leg's), and the Tokyo morning, server 2:30-8:30.  Mean return per
trade in bp of the currency bought, before costs (about 1 bp a round trip), with t-statistics, to 2017 and from
2018.

    python research/after_holiday_other.py

Result (2026-10-15): rejected, the effect is the dollar's.  USD after US holidays (the leg, this window): +7.6 bp
(t 3.4; +7.0 to 2017, +8.2 from 2018), other days +0.5 bp.  JPY after Japanese holidays: London morning +2.9 bp
(t 1.3; +3.1 / +2.7), Tokyo morning +0.4 bp - about 2 bp after cost on 11 days a year, not worth a leg.  GBP after
English bank holidays: London morning -2.5 bp, Tokyo hours +1.7 bp (t 1.8) - nothing.
One-off checks on the US leg itself: every dollar pair and gold move the same way after US holidays (per pair +3.9
to +7.3 bp, gold +6.6 bp t 2.1, silver +14.7 bp); the day before a US holiday has no consistent sign.  NZD/USD and
USD/JPY were already tried for the leg (tools/backtest_hydra.py AFTER); short gold with the leg's stop rule earns
t 1.2 and leaves Hydra at 3.37 from 2018 at half or full size, so the leg stays at its five pairs.
"""
import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atlas_scan import half  # noqa: E402

LONDON, TOKYO = (18, 30), (5, 17)
# test: (country calendar, {pair: +1 if the pair rises when the currency is bought}, windows)
TESTS = {
    "USD after US holiday": (None, {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "USDCAD": 1, "USDCHF": 1}, (LONDON,)),
    "JPY after Japanese holiday": ("JP", {"USDJPY": -1, "EURJPY": -1, "GBPJPY": -1, "AUDJPY": -1}, (TOKYO, LONDON)),
    "GBP after English bank holiday": ("UK", {"GBPUSD": 1, "EURGBP": -1, "GBPCHF": 1}, (LONDON, TOKYO)),
}


def stat(x):
    return f"{x.mean() * 1e4:+5.1f} bp (n {len(x):3d}, t {x.mean() / x.std() * np.sqrt(len(x)):+.1f})" if len(x) > 2 else "n/a"


if __name__ == "__main__":
    data, days = half()
    years = range(2009, 2028)
    us = pd.DatetimeIndex(USFederalHolidayCalendar().holidays(start="2009-01-01", end="2027-12-31"))
    for name, (cc, pairs, wins) in TESTS.items():
        if cc is None:
            hol = us
        else:
            cal = holidays.Japan(years=years) if cc == "JP" else holidays.UK(years=years, subdiv="ENG")
            hol = pd.DatetimeIndex(sorted(cal.keys()))
        hol = hol[hol.dayofweek < 5]
        wd = days[days.dayofweek < 5]
        nxt = wd[np.searchsorted(wd.to_numpy(), (hol + pd.Timedelta(days=1)).to_numpy()).clip(0, len(wd) - 1)]
        trig = pd.DatetimeIndex(sorted(set(nxt) - set(hol) - set(us)))
        if cc is None:
            trig = pd.DatetimeIndex(sorted(set(nxt) - set(hol)))
        row = days.get_indexer(trig)
        print(name, f"({len(trig)} days)")
        for a, b in wins:
            r = []
            for s, sign in pairs.items():
                M = pd.DataFrame(data[s]).ffill(axis=1).to_numpy(dtype=float)
                r.append(pd.Series(sign * (M[row, b] / M[row, a] - 1), index=trig))
            x = pd.concat(r, axis=1).mean(axis=1).dropna()
            x = x[x.abs() < 0.05]
            allx = pd.concat(r, axis=1)
            base = []
            for s, sign in pairs.items():            # the same window on all other weekdays, for comparison
                M = pd.DataFrame(data[s]).ffill(axis=1).to_numpy(dtype=float)
                base.append(pd.Series(sign * (M[:, b] / M[:, a] - 1), index=days))
            bx = pd.concat(base, axis=1).mean(axis=1)
            bx = bx[(bx.index.dayofweek < 5) & ~bx.index.isin(trig) & (bx.abs() < 0.05)].dropna()
            print(f"  server {a / 2:04.1f}-{b / 2:04.1f}h: all {stat(x)} | to 2017 {stat(x[:'2017'])} | 2018+ "
                  f"{stat(x['2018':])} | other days {bx.mean() * 1e4:+.2f} bp")
