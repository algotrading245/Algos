"""Backtest of AurumTrend on real XAUUSD.pc D1 bars.

Rule: at each daily open, be long if the previous close is above its --ma day average, otherwise flat. Size targets a
fixed annual volatility: leverage = min(--cap, --target / vol), vol = exponentially weighted (span --span) standard
deviation of daily returns, annualised. The held size is only changed when it is more than --band away from the
target. Trades fill at the daily open with --cost per round trip; long swap is charged per night (triple on
Wednesday) as a fixed fraction of the position value, set from today's broker swap. This is managed gold exposure,
so most of the return is the gold price itself: compare with "always long".

Usage: python tools/backtest_trend.py [--ma 50] [--target 0.10] [--cap 2] [--band 0.25] [--cost 0.25] [--grid]
"""
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
import realdata as rd

SWAP_LONG = 0.7744      # price units per oz per night, from the broker's symbol specification
SWAP_PRICE = 4200.0     # gold price when that swap was read; the charge is scaled with price (a financing rate)


def run(ma=50, target=0.10, cap=2.0, band=0.25, cost=0.25, span=30, always=False):
    d = rd.bars("D1").reset_index(drop=True)
    c, o = d.close.to_numpy(), d.open.to_numpy()
    r = pd.Series(c).pct_change()
    vol = (r.ewm(span=span).std() * np.sqrt(252)).to_numpy()
    sma = pd.Series(c).rolling(ma).mean().to_numpy()
    nights = np.where(d.dt.dt.dayofweek == 2, 3, 1)
    start = max(ma, 2 * span) + 1
    held, rows = 0.0, []
    for i in range(start, len(d) - 1):
        # decided on the close of day i-1, traded at the open of day i, held to the open of day i+1
        want = min(cap, target / vol[i - 1]) if (always or c[i - 1] > sma[i - 1]) else 0.0
        if want == 0.0 or held == 0.0 or abs(want - held) > band * held:
            turn, held = abs(want - held), want
        else:
            turn = 0.0
        pnl = held * (o[i + 1] / o[i] - 1) - turn * (cost / 2) / o[i] - held * SWAP_LONG / SWAP_PRICE * nights[i]
        rows.append((d.dt[i], held, turn, pnl))
    return pd.DataFrame(rows, columns=["dt", "lev", "turn", "ret"])


def report(t, label=""):
    eq = (1 + t.ret).cumprod()
    years = (t.dt.iloc[-1] - t.dt.iloc[0]).days / 365.25
    dd = (1 - eq / eq.cummax()).max()
    k = int(len(t) * 0.6)
    sh = lambda z: z.mean() / z.std() * np.sqrt(252)
    print(f"{label}CAGR {100 * (eq.iloc[-1] ** (1 / years) - 1):.1f}%, Sharpe {sh(t.ret):.2f} (first 60% {sh(t.ret.iloc[:k]):.2f}, "
          f"last 40% {sh(t.ret.iloc[k:]):.2f}), maxDD {100 * dd:.1f}%, in market {100 * (t.lev > 0).mean():.0f}%, "
          f"mean leverage {t.lev[t.lev > 0].mean():.2f}, size changes {int((t.turn > 0).sum() / years)}/yr")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ma", type=int, default=50, help="moving-average length, days")
    ap.add_argument("--target", type=float, default=0.10, help="annual volatility target")
    ap.add_argument("--cap", type=float, default=2.0, help="maximum leverage")
    ap.add_argument("--band", type=float, default=0.25, help="resize only when target differs by this fraction")
    ap.add_argument("--cost", type=float, default=0.25, help="round-trip cost, price units per oz")
    ap.add_argument("--grid", action="store_true", help="print variations instead of one run")
    a = ap.parse_args()
    if a.grid:
        report(run(always=True, cost=a.cost), "always long, vol target      | ")
        for ma in (20, 50, 100, 200):
            report(run(ma=ma, cost=a.cost), f"close > MA{ma:<3d}               | ")
        for band in (0.0, 0.1, 0.5):
            report(run(band=band, cost=a.cost), f"MA50, band {band:.2f}              | ")
        report(run(target=0.15, cap=3.0, cost=a.cost), "MA50, 15% target, cap 3x     | ")
        report(run(cost=1.0), "MA50, cost 1.00              | ")
    else:
        t = run(a.ma, a.target, a.cap, a.band, a.cost)
        report(t)
        y = t.groupby(t.dt.dt.year).ret.apply(lambda z: 100 * ((1 + z).prod() - 1))
        print("by year (%):", " ".join(f"{k}:{v:+.1f}" for k, v in y.items()))
