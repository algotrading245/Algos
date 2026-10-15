"""The "London breakout" of retail EAs: trade the first break of the Asian-session range during the London day.

Fixed textbook rules, no fitting: range = high and low of server 01:00-09:00 (New York 18:00-02:00, the Asian
session); from server 10:00 to 18:00 (London 08:00-16:00) buy the first 5-minute bar whose high breaks the range
high (fill at the range high, or the bar's open if it gapped through) or sell the first that breaks the low; stop
at the other side of the range (or its midpoint), exit at server 18:00.  Exits on 5-minute highs and lows, stop
first when a bar touches both.  Ranges smaller than a quarter or larger than three times their 60-day average are
skipped.  Results in R (the stop distance), costs per round trip in bp of price.

    python research/london_breakout.py

Result (2026-10-15): USD/JPY is a candidate leg; the other six are not.
  Stop at the range's other side, net of the costs above: USD/JPY Sharpe 0.97 (0.96 to 2017, 0.98 from 2018; 4,139
  trades, +0.057 R, R ~36 bp, positive in 16 of 17 years), gold 0.48 (0.45 / 0.52, year signs alternate), EUR/JPY
  0.62 (0.89 / 0.34), GBP/USD, EUR/USD, GBP/JPY, AUD/USD at or below zero; the seven together 0.46 (0.83 / 0.13).
  Midpoint stop: USD/JPY 0.90 (0.82 / 0.99), gold 0.69.
  USD/JPY robustness (one-off checks): range 0-9, 2-9, 1-8, 1-10 and entry 9-18, 11-18, 10-20 give 0.93-1.17 with
  both halves 0.74-1.28; entry only to 16:00 0.73; no range filter 1.00; at 1.5 bp instead of 0.8 bp 0.59.  Upside
  breaks carry it: +0.093 R a trade (t 4.4, +0.109 / +0.079), downside +0.023 R (t 1.2); USD/JPY's drift over the
  same hours on all days is +0.5 bp (t 0.8), so it is the break, not a London drift.  On 1-minute bars instead of 5:
  0.93 (0.87 / 0.98, 2024 on 1.13).  Correlation with every Hydra
  leg |r| <= 0.03.
  Added at 0.5% risk a trade: Hydra 2.60 / 3.37 -> 2.80 / 3.48 (to 2017 / from 2018), with the noise-area leg 3.66;
  AurumFunded 2.66 / 3.24 -> 2.88 / 3.34, with the noise leg 3.53.  The weight best to 2017 alone (2x) gives Hydra
  3.36 from 2018, so the gain needs a modest size.  At AurumFunded's volatility, 0.25x (0.125% risk a trade) gives
  Sharpe 3.30 and a lower maximum drawdown (11.4% -> 10.8%); 1x gives 3.34 but 14.9%.
  Mechanism not confirmed: if it were the dollar rising into the ECB and London fixings (Krohn, Mueller, Whelan,
  J. Finance; research/fx_fixings_clock.py), dollar-up breaks would earn on every dollar pair.  They do not
  (one-off check, R a trade, dollar-up / dollar-down breaks): EUR/USD +0.027 / -0.045, GBP/USD +0.037 / -0.050,
  AUD/USD -0.020 / -0.017, USD/CAD -0.058 / -0.094, USD/CHF -0.062 / -0.025, USD/JPY +0.093 / +0.023.  The effect
  is the yen's alone - one pair of seven, without a known cause, so the tester run on real spreads matters more.
  Variant chosen on 2010-2017 (one-off check): trade each side on its own - a buy stop and a sell stop that each
  fire once a day, instead of the first break only.  Upside only 1.33 / 1.06, downside only 0.62 / 0.48, both
  1.40 / 1.08 (first break only, same series, 1.09 / 0.93); in AurumFunded at its volatility with 0.125% a trade
  3.32 from 2018 and a lower drawdown (11.4% -> 10.6%).  AurumBreakout 1.01 trades both sides by default.
  Nikkei 225 CFD with the same rules, both sides (one pre-set check of the yen link): before cost 1.37 (1.86 /
  0.99), correlation 0.25 with the USD/JPY breakout - the same effect shows in the yen's stock market; at its 2 bp
  spread 0.73 (1.20 / 0.37), at 3 bp 0.41 (0.87 / 0.06): too costly as a leg.
  Gold with the both-sides rule (one check): 0.58 before cost, 0.21 at 1 bp (0.19 / 0.22), year signs alternate;
  adds nothing to AurumFunded with the USD/JPY leg (3.32 either way).
  On real bid/ask ticks 2024-01 to 2026-09 (research/breakout_ticks.py) the fills cost ~1.2 bp all in; at 1.2 bp the
  both-sides leg is 1.18 / 0.83 and still lifts AurumFunded 3.24 -> 3.30 at 0.125% a trade.
  Yen crosses, both sides (one check of the yen link): before cost EUR/JPY 1.50 (1.75 / 1.24), GBP/JPY 1.23 (1.24 /
  1.22), CAD/JPY 1.21 (1.01 / 1.41), AUD/JPY 0.63 (0.57 / 0.68), correlation 0.21-0.42 with the USD/JPY leg; at
  their spreads (1.4-2 bp) 0.72, 0.19, 0.21, -0.13.  With the Nikkei, every yen market shows the same break-and-run
  in both halves, so the USD/JPY result is not a lone fluke - but only USD/JPY is cheap enough to trade.
  Yen-cross agreement filter (rule fixed in advance: take the USD/JPY break only if at least two of EUR/JPY,
  GBP/JPY, AUD/JPY, CAD/JPY broke their own range the same way by then), at 1.2 bp: kept 3,128 of 4,965 trades,
  Sharpe 1.34 (1.63 / 1.07) against 1.01 (1.15 / 0.88); the dropped trades earn 0.30.  In the portfolios it changes
  nothing that matters (AurumFunded 3.29 vs 3.30 from 2018, drawdown 10.5% vs 10.8%; Hydra with both legs 3.64 vs
  3.63) because a third fewer trades offset the better ones - not worth a multi-symbol EA for now.
  US index CFDs, same rules, both sides (one check whether it is a risk-asset effect): S&P 500 0.03 and Nasdaq -0.01
  before cost, negative after - it is not.  DAX: 0.87 at 1 bp, but histdata has its Asian hours only from 2019 with
  2021-2022 missing and the years alternate (2023 -1.2, 2026 -1.6) - too thin to judge, not a candidate.
  After the exit (one check): fading USD/JPY from the London fix (18:00) to 22:00 on days it closed outside its range
  earns -0.4 bp (above) and +1.1 bp (below), t <= 1.4, signs differ by half - no post-fix reversal to add.
  Range width (Crabel's narrow-range idea, terciles of range / 60-day average set on 2010-2017, at 1.2 bp): below
  0.66 +0.163 R a trade to 2017 and +0.101 R from 2018, middle -0.002 / +0.005, widest +0.022 / +0.049.  Real, but
  trading the narrow third only gives the same daily Sharpe (0.98; 1.29 / 0.72) on a third of the trades, and the
  portfolios do not change (AurumFunded 3.29 vs 3.30, Hydra with both legs 3.64 vs 3.63) - the EA keeps all days.
  Sizing the narrow third up instead (x1.5 / 2 / 3): 1.27-1.32 to 2017 but 0.82-0.85 from 2018 against 0.83 - no.
  Next: an MQL5 version for the Strategy Tester on USDJPY, then a size of about 0.125-0.25% risk a trade.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
PAIRS = {"GBPUSD": 1.0, "EURUSD": 0.8, "XAUUSD": 1.0, "USDJPY": 0.8, "GBPJPY": 2.0, "EURJPY": 1.4, "AUDUSD": 1.0}


def run(s, stop_at="side", both=False):
    """Trades as (day, r in R, R / entry).  both=True: a buy and a sell stop that each trade once a day on their own
    (two rows on a day both sides break); else only the first break."""
    m = pd.read_csv(DATA / f"{s}_M1.csv.gz")
    t = pd.to_datetime(m.time, unit="s")
    m = m[t.dt.dayofweek < 5]
    g = m.assign(time=m.time // 300 * 300).groupby("time").agg(open=("open", "first"), high=("high", "max"),
                                                               low=("low", "min"), close=("close", "last"))
    g["day"] = pd.to_datetime(g.index, unit="s").normalize()
    g["h"] = (g.index % 86400) / 3600
    out = []
    rng_hist = []
    for day, d in g.groupby("day"):
        a = d[(d.h >= 1) & (d.h < 9)]
        b = d[(d.h >= 10) & (d.h < 18)]
        if len(a) < 60 or len(b) < 60:
            continue
        hi, lo = a.high.max(), a.low.min()
        width = hi - lo
        avg = np.mean(rng_hist[-60:]) if len(rng_hist) >= 30 else np.nan
        rng_hist.append(width / a.close.iloc[-1])
        if np.isnan(avg) or not 0.25 * avg <= width / a.close.iloc[-1] <= 3 * avg:
            continue
        O, H, L, C = (b[c].to_numpy() for c in ("open", "high", "low", "close"))
        for want in ((1, -1) if both else (0,)):
            side, e, stop, x = 0, 0.0, 0.0, None
            for k in range(len(b)):
                if side == 0:
                    if want >= 0 and H[k] > hi:
                        side, e = 1, max(hi, O[k])
                    elif want <= 0 and L[k] < lo:
                        side, e = -1, min(lo, O[k])
                    else:
                        continue
                    stop = (lo if side > 0 else hi) if stop_at == "side" else (hi + lo) / 2
                    if side * (C[k] - stop) <= 0:            # stopped inside the entry bar
                        x = stop
                        break
                    continue
                if side * ((L[k] if side > 0 else H[k]) - stop) <= 0:
                    x = stop
                    break
            if side == 0:
                continue
            if x is None:
                x = C[-1]
            R = abs(e - stop)
            out.append((day, side * (x - e) / R, R / e))
    return pd.DataFrame(out, columns=["day", "r", "rel"])


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    hy = pd.read_csv(CACHE, index_col=0, parse_dates=True).sum(axis=1)
    hy = hy[hy.index.dayofweek < 5]
    for stop_at in ("side", "mid"):
        print(f"stop at the range {stop_at}")
        port = []
        for s, c in PAIRS.items():
            T = run(s, stop_at)
            r = T.r - c * 1e-4 / T.rel
            d = pd.Series(r.to_numpy(), index=T.day)
            port.append(d.rename(s))
            print(f"  {s}: {len(T)} trades, R {T.rel.median() * 1e4:.0f} bp, gross {T.r.mean():+.3f}R, net {r.mean():+.3f}R "
                  f"win {(r > 0).mean():.0%}  Sharpe {sharpe(d):+.2f} (to2017 {sharpe(d[:'2017']):+.2f}, 2018+ "
                  f"{sharpe(d['2018':]):+.2f})", flush=True)
        p = pd.concat(port, axis=1, sort=True).fillna(0).mean(axis=1).reindex(hy.index).fillna(0) * 0.003
        best = max(((sharpe((hy + w * p)[:"2017"]), w) for w in (0.25, 0.5, 1.0, 2.0)))
        print(f"  all: Sharpe {sharpe(p):+.2f} (to2017 {sharpe(p[:'2017']):+.2f}, 2018+ {sharpe(p['2018':]):+.2f})  "
              f"corr Hydra {p.corr(hy):+.2f}  Hydra + {best[1]}x 2018+ {sharpe((hy + best[1] * p)['2018':]):.3f} (3.371)")
