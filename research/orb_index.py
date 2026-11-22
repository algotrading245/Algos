"""5-minute opening range breakout on the Nasdaq 100 and S&P 500 CFDs (Zarattini, Aziz, "Can Day Trading Really Be
Profitable? Evidence of Sustainable Long-term Profits from Opening Range Breakout (ORB) Day Trading Strategy vs.
Benchmark in the US Stock Market", SSRN 4416622, April 2023, read in full).

Paper: QQQ, 2016-01 to 2023-02-17.  If the first 5-minute candle (9:30-9:35) is up, buy at the open of the second
candle, if down, sell; nothing on a doji.  Stop at the first candle's low (long) or high (short), R = entry - stop;
target 10 R or the close, whichever first.  Size: risk 1% of the account, notional capped at 4x the account,
$0.0005 a share, no slippage.  Result: +675%, 31% a year, Sharpe 1.12, win rate 24%, 0.13 R a trade, beta ~0; on
TQQQ (3x) 46% a year, Sharpe 1.18.  Sensitivity: a stop at 5% of the 14-day ATR and no target (exit at the close)
is best, 0.18 R per trade on TQQQ and +9,350% - with the caveat that a stop that tight will slip.

Here: histdata.com minute closes on the New York clock (research/overnight_intraday_reversal.py `matrix`), so the
first candle's range is that of the 9:30-9:35 minute closes and a stop fills at the first minute close beyond it
(pessimistic) or at the stop itself (optimistic).  Costs 0.75 and 1.5 bp of the notional per round trip, 2010-11 to
2026-10; the paper's sample is 2016 to 2023-02, so 2010-2015 and 2023-03 on are out of it.

    python research/orb_index.py          (minute closes, stop fill bracketed)
    python research/orb_index.py --hl     (minute highs and lows: the test that counts)

Result (2026-10-15): rejected, the noise-area leg already holds it.
  Minute closes only: the result is decided by the stop fill - filled at the stop the Nasdaq rule shows Sharpe
  1.5-2.1 (0.05 ATR stop 2.06), filled at the first minute close beyond it 0.4-0.6.  On minute highs and lows (a stop
  fills at the stop or the gapped open, less 0.5 bp slippage, stop first when a bar reaches both) at 0.75 bp:
  Nasdaq, paper's rule (first-candle stop, 10 R): 0.53 (2010-15 0.06, paper's years 0.87, after 0.35), 0.10 R a
  trade, win 23% (paper 0.13 R, 24%); 0.10 ATR stop to the close 0.72 (0.47, 0.88, 0.67); 0.05 ATR 0.53, the paper's
  best setting does not survive real highs and lows; S&P 500 0.02 to 0.34, the tight stops negative.  Correlation
  with the Hydra legs ~0, with the noise-area leg (research/noise_area_index.py) 0.3.  Hydra with the noise leg
  from 2018: 3.55, plus the ORB at the weight best to 2017 3.55-3.56, at 0.25 3.48-3.49; after the paper 3.44 ->
  3.41-3.43.  Nothing to add.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from overnight_intraday_reversal import NY, matrix  # noqa: E402

CACHE = Path(__file__).resolve().parent.parent / "marketdata" / "hydra_legs_daily.csv.gz"
DATA = Path(__file__).resolve().parent.parent / "marketdata" / "histdata"
OPEN, CLOSE = 570, 960


def bars(symbol):
    """Days x 390 one-minute bars 9:30-15:59 New York (bar open time): open, high, low, close."""
    f = DATA / f"ORB_{symbol}.npz"
    if f.exists():
        z = np.load(f)
        return pd.DatetimeIndex(z["days"]), z["o"], z["h"], z["l"], z["c"]
    m = pd.read_csv(DATA / f"{symbol}_M1.csv.gz")
    t = pd.to_datetime(m["time"] - 7 * 3600, unit="s").dt.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    t = t.dt.tz_localize(None)
    k = (t.dt.hour * 60 + t.dt.minute).to_numpy()
    ok = t.notna().to_numpy() & (k >= OPEN) & (k < CLOSE)
    t, k, m = t[ok], k[ok] - OPEN, m[ok]
    day = t.dt.normalize()
    days = pd.DatetimeIndex(np.unique(day))
    row = days.get_indexer(day)
    out = []
    for col in ("open", "high", "low", "close"):
        a = np.full((len(days), CLOSE - OPEN), np.nan, dtype=np.float32)
        a[row, k] = m[col].to_numpy()
        out.append(a)
    np.savez_compressed(f, days=days.values, o=out[0], h=out[1], l=out[2], c=out[3])
    return (days, *out)


def run_hl(symbol, stop_atr=None, target=10.0, cost_bp=0.75, slip_bp=0.0, risk=0.01, cap=4.0):
    """The rule on minute highs and lows: a stop fills at the stop (or the bar's open if it gaps through) less
    slip_bp; when a bar reaches both the stop and the target, the stop counts."""
    days, O, H, L, C = bars(symbol)
    keep = (days.dayofweek < 5) & (np.isnan(C).sum(axis=1) < 30) & ~np.isnan(O[:, :6]).any(axis=1)
    days, O, H, L, C = days[keep], O[keep], H[keep], L[keep], C[keep]
    C = pd.DataFrame(C).ffill(axis=1).to_numpy()
    hi, lo, c = np.nanmax(H, axis=1), np.nanmin(L, axis=1), C[:, -1]
    tr = np.maximum(hi, np.r_[np.nan, c[:-1]]) - np.minimum(lo, np.r_[np.nan, c[:-1]])
    atr = pd.Series(tr).rolling(14).mean().shift(1).to_numpy()
    out, rr = np.zeros(len(days)), np.full(len(days), np.nan)
    for i in range(len(days)):
        o, e = O[i, 0], O[i, 5]
        f = C[i, 4]
        if not atr[i] > 0 or abs(f - o) < 1e-9 * o:
            continue
        side = 1 if f > o else -1
        stop = (np.nanmin(L[i, :5]) if side > 0 else np.nanmax(H[i, :5])) if stop_atr is None else e - side * stop_atr * atr[i]
        R = side * (e - stop)
        if R <= 0:
            continue
        tgt = e + side * target * R if target else None
        x = C[i, -1]
        for j in range(5, CLOSE - OPEN):
            if np.isnan(H[i, j]):
                continue
            adverse = L[i, j] if side > 0 else H[i, j]
            if side * (adverse - stop) <= 0:
                x = (min(stop, O[i, j]) if side > 0 else max(stop, O[i, j])) * (1 - side * slip_bp * 1e-4)
                break
            fav = H[i, j] if side > 0 else L[i, j]
            if tgt is not None and side * (fav - tgt) >= 0:
                x = tgt
                break
        notional = min(cap, risk / (R / e))
        out[i] = notional * (side * (x / e - 1) - cost_bp * 1e-4)
        rr[i] = side * (x - e) / R
    return pd.Series(out, index=days), pd.Series(rr, index=days)


def run(symbol, stop_atr=None, target=10.0, cost_bp=0.75, risk=0.01, cap=4.0, fill="close"):
    days, p = matrix(symbol, NY)
    p = pd.DataFrame(p.astype(float)).ffill(axis=1).to_numpy()
    keep = (days.dayofweek < 5) & ~np.isnan(p[:, OPEN]) & ~np.isnan(p[:, CLOSE]) & ~np.isnan(p[:, OPEN + 5])
    days, p = days[keep], p[keep]
    s = p[:, OPEN:CLOSE + 1]
    hi, lo, c = s.max(axis=1), s.min(axis=1), s[:, -1]
    tr = np.maximum(hi, np.r_[np.nan, c[:-1]]) - np.minimum(lo, np.r_[np.nan, c[:-1]])
    atr = pd.Series(tr).rolling(14).mean().shift(1).to_numpy()
    out, rr = np.zeros(len(days)), np.full(len(days), np.nan)
    for i in range(len(days)):
        first = s[i, :6]
        o, e = first[0], first[5]
        if not atr[i] > 0 or abs(e - o) < 1e-9 * o:
            continue
        side = 1 if e > o else -1
        stop = (first.min() if side > 0 else first.max()) if stop_atr is None else e - side * stop_atr * atr[i]
        R = abs(e - stop)
        if R <= 0:
            continue
        tgt = e + side * target * R if target else None
        x = s[i, -1]
        for px in s[i, 6:]:
            if side * (px - stop) <= 0:
                x = px if fill == "close" else stop
                break
            if tgt is not None and side * (px - tgt) >= 0:
                x = tgt
                break
        notional = min(cap, risk / (R / e))
        out[i] = notional * (side * (x / e - 1) - cost_bp * 1e-4)
        rr[i] = side * (x - e) / R
    return pd.Series(out, index=days), pd.Series(rr, index=days)


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def report(x, r, hy, tag):
    x, r = x["2010-11":], r["2010-11":].dropna()
    a = pd.concat([hy, x], axis=1, sort=True).fillna(0)
    best, wb = -9, 0
    for w in (0.25, 0.5, 1.0, 2.0):
        v = sharpe((a.iloc[:, 0] + w * a.iloc[:, 1])[:"2017"])
        best, wb = (v, w) if v > best else (best, wb)
    add = a.iloc[:, 0] + wb * a.iloc[:, 1]
    print(f"  {tag:40s} Sharpe {sharpe(x):+.2f} (2010-15 {sharpe(x[:'2015']):+.2f}, 2016-23/02 "
          f"{sharpe(x['2016':'2023-02']):+.2f}, after {sharpe(x['2023-03':]):+.2f})  {r.mean():+.3f} R, win "
          f"{(r > 0).mean():.0%}, {252 * x.mean():+.0%}/yr  corr Hydra {a.corr().iloc[0, 1]:+.2f}  Hydra+{wb}: "
          f"2018+ {sharpe(add['2018':]):.2f} (alone {sharpe(a.iloc[:, 0]['2018':]):.2f})", flush=True)


if __name__ == "__main__" and "--hl" in sys.argv:
    hy = pd.read_csv(CACHE, index_col=0, parse_dates=True).sum(axis=1)
    hy = hy[hy.index.dayofweek < 5]
    for sym in ("NSXUSD", "SPXUSD"):
        print(sym, "on minute highs and lows")
        for stop_atr, target in ((None, 10.0), (None, None), (0.05, None), (0.10, None), (0.25, None)):
            for cost, slip in ((0.75, 0.0), (0.75, 0.5), (1.5, 0.5)):
                x, r = run_hl(sym, stop_atr, target, cost, slip)
                tag = f"stop {'candle' if stop_atr is None else f'{stop_atr:.2f} ATR'} tgt {target or 'EoD'} {cost}+{slip}bp"
                report(x, r, hy, tag)
    sys.exit()

if __name__ == "__main__":
    hy = pd.read_csv(CACHE, index_col=0, parse_dates=True).sum(axis=1)
    hy = hy[hy.index.dayofweek < 5]
    for sym in ("NSXUSD", "SPXUSD"):
        print(sym)
        for stop_atr, target in ((None, 10.0), (None, None), (0.05, None), (0.10, None), (0.25, None)):
            for cost in (0.75, 1.5):
                for fill in ("close", "stop"):
                    if fill == "stop" and cost == 1.5:
                        continue
                    x, r = run(sym, stop_atr, target, cost, fill=fill)
                    x = x["2010-11":]
                    r = r["2010-11":].dropna()
                    a = pd.concat([hy, x], axis=1, sort=True).fillna(0)
                    best, wb = -9, 0
                    for w in (0.25, 0.5, 1.0, 2.0):
                        v = sharpe((a.iloc[:, 0] + w * a.iloc[:, 1])[:"2017"])
                        best, wb = (v, w) if v > best else (best, wb)
                    add = a.iloc[:, 0] + wb * a.iloc[:, 1]
                    tag = f"stop {'candle' if stop_atr is None else f'{stop_atr:.2f} ATR'} tgt {target or 'EoD'}"
                    print(f"  {tag:22s} {cost:4.2f}bp fill {fill:5s}: Sharpe {sharpe(x):+.2f} (2010-15 "
                          f"{sharpe(x[:'2015']):+.2f}, 2016-23/02 {sharpe(x['2016':'2023-02']):+.2f}, after "
                          f"{sharpe(x['2023-03':]):+.2f})  {r.mean():+.3f} R/trade, win {(r > 0).mean():.0%}, "
                          f"{252 * x.mean():+.0%}/yr  corr Hydra {a.corr().iloc[0, 1]:+.2f}  Hydra+{wb}: 2018+ "
                          f"{sharpe(add['2018':]):.2f} (alone {sharpe(a.iloc[:, 0]['2018':]):.2f})", flush=True)
