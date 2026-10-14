"""Currencies fall in their own trading hours (Breedon, Ranaldo, SNB Working Paper 2011-4 / JMCB 2013).

EBS firm quotes 1997-2007, hourly.  Trading hours (Table 1): United States 8:00-16:00 New York, Europe 7:00-15:00
London, Japan 8:00-15:00 Tokyo, Australia 10:00-16:00 Sydney.  Table 2, annualised log returns at mid: EUR/USD
-8.4% in the European session (to the US open, as the two overlap) and +10.0% in the US session; GBP/USD -7.1% and
+9.2%; USD/CHF +9.5% and -8.8%; USD/JPY and AUD/USD 0-3%.  After the spread only EUR/USD pays: 6% and 7% a year,
Sharpe 1.3 for the morning short and 0.9 for the afternoon long.  Figure 2: the gap between the two EUR/USD
sessions has the same sign in every year but 2004.  The pattern is in order flow too (Table 3).

Here: the same windows on bid minute bars.  The Tokyo and Sydney sessions start an hour late (9:00 and 11:00) to
stay clear of the 17:00 New York rollover, where bid-only prices jump.

    python research/fx_local_hours.py

Result on histdata minute bars (2009 to 2026-10), not added to any EA:
  The sign is still there for the European pairs, at a quarter of the paper's size.  EUR/USD falls 2.1 bp
           (t 4.7) from 7:00 to 13:00 London - 2.6 bp to 2017, 1.6 bp from 2018, 5% a year against 8.4% - and
           rises 1.0 bp (t 1.8) in the US session, 0.3 bp from 2018.  The two sessions together are positive in
           16 of 18 years.  GBP/USD 1.4 bp and 1.4 bp, USD/CHF 0.75 bp and 1.6 bp, each near zero from 2018.
  USD/JPY, EUR/JPY and AUD/USD go against the paper in the Asian session (yen -1.3 bp, t -3.0); USD/CAD and
           NZD/USD show nothing in the US session.
  After the spread only the EUR/USD morning short is left: Sharpe 0.65 (0.79 to 2017, 0.48 from 2018).  All
           other sessions are negative from 2018; the dollar basket is -0.19, the European basket 0.22.
  As a Hydra leg the EUR/USD morning short has correlation 0.17 with the rest and lowers the combined Sharpe at
           every size (3.01 to 2.98 at 1x, 2.74 at 3x).  Not added.
"""
import numpy as np
import pandas as pd

from intraday_momentum import SPLIT, at, minutes
from overnight_intraday_reversal import NY, matrix, stats

LONDON, TOKYO, SYDNEY = "Europe/London", "Asia/Tokyo", "Australia/Sydney"
US = (NY, "08:00", "16:00")
EUROPE = (LONDON, "07:00", "13:00")      # to the US open; the paper's open-to-open
EUROPE_FULL = (LONDON, "07:00", "15:00")
JAPAN = (TOKYO, "09:00", "15:00")
AUSTRALIA = (SYDNEY, "11:00", "16:00")
# pair: (round trip bp, {session: (window, sign of the paper's prediction for the pair)})
PAIRS = {
    "EURUSD": (0.85, {"EUR": (EUROPE, -1), "EUR full": (EUROPE_FULL, -1), "USD": (US, 1)}),
    "GBPUSD": (1.0, {"GBP": (EUROPE, -1), "GBP full": (EUROPE_FULL, -1), "USD": (US, 1)}),
    "USDCHF": (1.1, {"CHF": (EUROPE, 1), "CHF full": (EUROPE_FULL, 1), "USD": (US, -1)}),
    "USDJPY": (0.85, {"JPY": (JAPAN, 1), "USD": (US, -1)}),
    "EURJPY": (1.5, {"JPY": (JAPAN, 1), "EUR": (EUROPE_FULL, -1)}),
    "AUDUSD": (1.05, {"AUD": (AUSTRALIA, -1), "USD": (US, 1)}),
    "USDCAD": (1.1, {"USD": (US, -1)}),
    "NZDUSD": (1.5, {"USD": (US, 1)}),
}


def frame(symbol, sessions):
    """Per weekday (date of the session's own clock): the log return of the pair over each session."""
    out = {}
    for name, ((zone, a, b), _) in sessions.items():
        days, p = matrix(symbol, zone)
        lp = np.log(p.astype(float))
        x = pd.Series(at(lp, minutes(b)) - at(lp, minutes(a)), index=days)
        out[name] = x[days.dayofweek < 5]
    return pd.DataFrame(out)


def cell(x):
    x = x.dropna()
    return f"{x.mean() * 1e4:6.2f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):5.2f})"


def row(name, x):
    x = x.dropna()
    print(f"    {name:30s} all {stats(x)}   to 2017 {stats(x[:SPLIT])}   2018+ {stats(x[SPLIT:])}")


if __name__ == "__main__":
    legs = {}
    for s, (cost, sessions) in PAIRS.items():
        r = frame(s, sessions)
        print(f"\n=== {s}  {r.index[0].date()} to {r.index[-1].date()}  {len(r)} days, {cost} bp round trip")
        print("  mean in the predicted direction, before costs:  all | to 2017 | 2018+   (% a year)")
        for name, (_, sign) in sessions.items():
            x = sign * r[name]
            print(f"    {name:10s} {cell(x)}   {cell(x[:SPLIT])}   {cell(x[SPLIT:])}"
                  f"   {x.mean() * 252 * 100:5.1f}%")
        print("  traded every day in the predicted direction")
        for name, (_, sign) in sessions.items():
            row(f"{name}, before costs", sign * r[name])
            legs[s, name] = sign * r[name] - cost * 1e-4
            row(f"{name}, after {cost} bp", legs[s, name])
        if s in ("EURUSD", "GBPUSD", "USDCHF"):
            a, b = list(sessions)[0], "USD"
            gap = (sessions[b][1] * r[b] + sessions[a][1] * r[a]).dropna()
            print("  both sessions by year, bp a day before costs:  " + "  ".join(
                f"{y} {x.mean() * 1e4:4.1f}" for y, x in gap.groupby(gap.index.year)))
    print("\n=== dollar basket, US session 8:00-16:00 New York: short the dollar on every pair, equal weight")
    usd = pd.DataFrame({s: legs[s, "USD"] for s in PAIRS if (s, "USD") in legs})
    row("after costs", usd.mean(axis=1))
    print("=== European basket, 7:00-13:00 London: short EUR, GBP and CHF against the dollar")
    eur = pd.DataFrame({s: legs[s, n] for s, n in (("EURUSD", "EUR"), ("GBPUSD", "GBP"), ("USDCHF", "CHF"))})
    row("after costs", eur.mean(axis=1))
