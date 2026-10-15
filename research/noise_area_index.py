"""Noise-area intraday momentum on stock-index CFDs (Zarattini, Aziz, Barbon, "Beat the Market: An Effective
Intraday Momentum Strategy for S&P500 ETF (SPY)", Swiss Finance Institute RP 24-97, version of 2025-02-03, read in
full; earlier tested here only on gold, research/noise_trend_scan.py).

The paper's rule (section 3): sigma(t, HH:MM) = mean over the 14 previous days of |close(HH:MM)/open(9:30) - 1|;
upper band = max(open 9:30, previous close 16:00) x (1 + VM sigma), lower band = min(...) x (1 - VM sigma).  Checked
only at HH:00 and HH:30 from 10:00: long above the upper band, short below the lower band; a long is closed when the
price is below max(upper band, VWAP) (a short above min(lower band, VWAP)), and may reverse at once if the price is
beyond the other band; everything closes at 16:00.  Size: equity x min(4, 2% / daily volatility of the last 14
days).  Paper (SPY, 2007-2024-04, $0.0035 a share commission and $0.001 slippage): Sharpe 1.33, 19.6% a year,
volatility 14.3%, 12 bp a day, 1.8 trades a day; VM 1 (1.5 has the best Sharpe); Table 5-6 day patterns.

Here: bid minute bars from histdata.com on the New York clock (SPXUSD = S&P 500, NSXUSD = Nasdaq 100).  histdata
has no volume, so a time-weighted average of the minute closes since 9:30 stands in for the VWAP (also run with no
VWAP stop).  Cost in bp per round trip of the traded notional (an index CFD at FTMO: about 0.5-1 point of spread,
no commission).

    python research/noise_area_index.py

Result (2010-11 to 2026-10), a candidate leg, not yet in an EA:
  Before costs the rule replicates: S&P 500 Sharpe 1.00 (0.64 to 2017, 1.29 from 2018), Nasdaq 1.07 (0.76, 1.32),
  about 10 bp a traded day and one trade a day (paper 1.33, 12 bp, 1.8 trades).  Costs decide it:
    S&P 500  VM 1.0: 0.65 at 0.75 bp, 0.30 at 1.5 bp, -0.39 at 3 bp;  VM 1.5: 0.80 at 0.75 bp (0.70 | 0.88; 0.43
             since 2022), 0.54 at 1.5 bp
    Nasdaq   VM 1.0: 0.78 at 0.75 bp (0.43 | 1.08; 1.04 since 2022), 0.49 at 1.5 bp, -0.08 at 3 bp
  The band-only stop (no TWAP) is worse; VM 2 trades too little.  Correlation with the Hydra legs -0.02; between the
  two indices 0.62.  Half S&P 500 (VM 1.5) and half Nasdaq (VM 1.0): Sharpe 0.88 at 0.75 bp (0.61 | 1.08), 0.77 at
  1 bp, 0.57 at 1.5 bp.  Added to Hydra with the weight that was best to 2017 (0.55 at 0.75 bp, 0.45 at 1 bp, 0.25
  at 1.5 bp), the Sharpe from 2018 goes from 3.38 to 3.56, 3.53 and 3.46; AurumFunded's legs from 3.25 to 3.44 at
  0.75 bp.  The same rule on currency pairs fails (one-off check, London 8-16 for EUR/USD and GBP/USD, Tokyo 9-15
  for USD/JPY and AUD/USD, New York 8-16 for USD/CAD): before cost -0.56 to 0.50, after 0.8 bp all negative, as
  expected if the effect comes from option dealers' and leveraged ETFs' hedging in stock indices.
  Next: FTMO's spread on US500.cash and US100.cash, then an MQL5 version and the Strategy Tester.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overnight_intraday_reversal import NY, matrix

SPLIT = pd.Timestamp("2018-01-01")
# exchange clock and cash session (open, close in minutes of the day) of each index
SESSIONS = {"SPXUSD": (NY, 570, 960), "NSXUSD": (NY, 570, 960), "GRXEUR": ("Europe/Berlin", 540, 1050),
            "UKXGBP": ("Europe/London", 480, 990), "JPXJPY": ("Asia/Tokyo", 540, 900)}


def run(symbol, vm=1.0, cost_bp=1.5, use_vwap=True, look=14, target=0.02, cap=4.0):
    zone, OPEN, CLOSE = SESSIONS[symbol]
    CHECKS = list(range(OPEN + 30, CLOSE, 30))
    days, p = matrix(symbol, zone)
    p = pd.DataFrame(p.astype(float)).ffill(axis=1).to_numpy()
    keep = days.dayofweek < 5
    days, p = days[keep], p[keep]
    o, c = p[:, OPEN], p[:, CLOSE]
    ok = ~np.isnan(o) & ~np.isnan(c) & ~np.isnan(p[:, CHECKS]).any(axis=1)
    days, p, o, c = days[ok], p[ok], o[ok], c[ok]
    move = np.abs(p[:, OPEN:CLOSE + 1] / o[:, None] - 1)
    sig = pd.DataFrame(move).rolling(look).mean().shift(1).to_numpy()
    twap = np.cumsum(p[:, OPEN:CLOSE + 1], axis=1) / np.arange(1, CLOSE - OPEN + 2)
    dret = pd.Series(c / np.r_[np.nan, c[:-1]] - 1)
    dvol = dret.rolling(look).std().shift(1).to_numpy()
    out, trades = np.zeros(len(days)), np.zeros(len(days))
    for i in range(1, len(days)):
        if np.isnan(sig[i, 0]) or not dvol[i] > 0:
            continue
        hi, lo = max(o[i], c[i - 1]), min(o[i], c[i - 1])
        pos, entry, r, n = 0, 0.0, 0.0, 0
        for m in CHECKS + [CLOSE]:
            j = m - OPEN
            px = p[i, m]
            ub, lb = hi * (1 + vm * sig[i, j]), lo * (1 - vm * sig[i, j])
            if pos:
                stop = (max(ub, twap[i, j]) if pos > 0 else min(lb, twap[i, j])) if use_vwap else (lb if pos > 0 else ub)
                if m == CLOSE or (pos > 0 and px < stop) or (pos < 0 and px > stop):
                    r += pos * (px / entry - 1) - cost_bp * 1e-4
                    pos = 0
            if m == CLOSE:
                break
            if pos == 0:
                if px > ub:
                    pos, entry, n = 1, px, n + 1
                elif px < lb:
                    pos, entry, n = -1, px, n + 1
        out[i] = r * min(cap, target / dvol[i])
        trades[i] = n
    return pd.Series(out, index=days), pd.Series(trades, index=days)


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def line(label, x, n, hydra):
    x = x["2010":]
    corr = pd.concat([x, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
    act = x[x != 0]
    print(f"  {label:34s} Sharpe {sharpe(x):+.2f} (to 2017 {sharpe(x[:SPLIT]):+.2f}, from 2018 {sharpe(x[SPLIT:]):+.2f}, "
          f"2022+ {sharpe(x['2022':]):+.2f})  {1e4 * act.mean():+5.1f} bp a traded day, {252 * x.mean():+.1%}/yr, "
          f"vol {np.sqrt(252) * x.std():.1%}, {n['2010':].mean():.2f} trades/day, corr Hydra {corr:+.2f}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "marketdata"
    hydra = pd.read_csv(root / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    for s in SESSIONS:
        if not (root / "histdata" / f"{s}_M1.csv.gz").exists():
            continue
        print(s)
        for vm, cost, vw in ((1.0, 0.0, True), (1.0, 0.75, True), (1.0, 1.5, True), (1.0, 3.0, True), (1.5, 0.75, True), (1.5, 1.5, True), (2.0, 0.75, True), (1.0, 1.5, False)):
            x, n = run(s, vm, cost, vw)
            line(f"VM {vm} cost {cost} bp {'TWAP stop' if vw else 'band stop'}", x, n, hydra)
