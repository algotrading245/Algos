"""volmanaged_mm with FTMO swaps (docs/ftmo_specs.json) in place of the flat 0.5 bp/day swap.

Same rule as research/volmanaged_mm.py (Moreira & Muir 2017, daily): w = min(CAP, c / RV22^2), RV to yesterday's close,
c fixed on data to 2017 so managed std = hold std. Long only. Swap per night = swap_long * point / price_t (the current
FTMO swap in points, applied at each day's price), tripled on the rollover3days weekday (Wed=3, Fri=5), on w.
Spread: half round trip each side (SPX 1.0 bp, XAU 1.0, USDJPY 0.7, EURUSD 0.6) on |dw|, x1/1.5/2 (swap also scaled).
Holdout dropped. Trials: 4 markets x caps {1,2} = 8 (same as the original run; the swap is a data fix, not a new trial).
    python research/volmanaged_mm_ftmo.py
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

SPECS = json.load(open(ROOT / "docs" / "ftmo_specs.json"))["symbols"]
MAP = {"SPXUSD": "US500.cash", "XAUUSD": "XAUUSD", "USDJPY": "USDJPY", "EURUSD": "EURUSD"}
RT = {"SPXUSD": 1.0e-4, "XAUUSD": 1.0e-4, "USDJPY": 0.7e-4, "EURUSD": 0.6e-4}
SPLIT = pd.Timestamp("2018-01-01")


def daily(sym):
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    cl = d.close.resample("1D").last().dropna()
    cl = cl[cl.index.dayofweek < 5]
    return np.log(cl).diff().dropna(), cl


def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan


def swap_rate(sym, cl, idx):
    s = SPECS[MAP[sym]]
    # swap is a financing rate, so it scales with price: the points at today's price, as bp of notional, held fixed
    # (points at old, lower prices would overstate the cost 5x for the index)
    per_night = s["swap_long"] * s["point"] / cl.iloc[-1]  # >0 credit, <0 cost (fraction of notional)
    tri = pd.Series([3.0 if (d + 1) % 7 == s["swap_rollover3days"] else 1.0 for d in idx.dayofweek], index=idx)
    return per_night * tri


def run(r, cl, sym, cap, mult):
    rv2 = (r ** 2).rolling(22).sum().shift(1)
    w0 = 1.0 / rv2
    tr = r[r.index < SPLIT]
    ok = w0.loc[tr.index].notna()
    target = tr[ok].std()
    base = (w0.loc[tr.index][ok] * tr[ok]).std()
    c0 = target / base
    cs = np.linspace(c0 * 0.2, c0 * 20, 4000)
    best = min(cs, key=lambda cc: abs((np.minimum(cap, cc * w0.loc[tr.index][ok]) * tr[ok]).std() - target))
    w = np.minimum(cap, best * w0).dropna()
    rr = r.loc[w.index]
    sw = swap_rate(sym, cl, w.index)  # signed: negative = cost
    cost_spread = w.diff().abs().fillna(0) * RT[sym] / 2 * mult
    swap_pnl = w * sw * np.where(sw < 0, mult, 1.0)  # stress only the costs
    net = w * rr - cost_spread + swap_pnl
    hold_sw = sw * np.where(sw < 0, mult, 1.0)
    hold = rr + hold_sw
    return net, hold, best, w


for sym in RT:
    r, cl = daily(sym)
    s = SPECS[MAP[sym]]
    print(f"== {sym}: {r.index[0].date()} .. {r.index[-1].date()}  {len(r)} days  swap_long {s['swap_long']} pts "
          f"-> {s['swap_long']*s['point']/cl.iloc[-1]*1e4:.2f} bp/night at last price")
    for cap in (1, 2):
        for mult in (1.0, 1.5, 2.0):
            net, hold, c, w = run(r, cl, sym, cap, mult)
            a, b = net[net.index < SPLIT], net[net.index >= SPLIT]
            ha, hb = hold.loc[a.index], hold.loc[b.index]
            print(f"cap {cap} x{mult}: managed Sh {sh(a):.2f}/{sh(b):.2f}  hold {sh(ha):.2f}/{sh(hb):.2f}  "
                  f"delta {sh(a)-sh(ha):+.2f}/{sh(b)-sh(hb):+.2f}  mean w {w.mean():.2f}")
        if sym == "SPXUSD" and cap == 2:
            n1 = run(r, cl, sym, cap, 1.0)[0]
            n15 = run(r, cl, sym, cap, 1.5)[0]
            out = ROOT / "marketdata" / "candidates"
            n1.rename("r").rename_axis("day").to_csv(out / "volmanaged_mm.csv")
            n15.rename("r").rename_axis("day").to_csv(out / "volmanaged_mm_stress.csv")
