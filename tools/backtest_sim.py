"""Python port of the AurumLadder EA, run on synthetic gold.

Stand-in for the MT5 Strategy Tester where MT5 and real tick data are unavailable.
The EA rules are the same as mql5/ (signal, ATR zone, ladder sizing, SL/TP, spread
filter, weekend, cooldown, daily stop). The price path is a fat-tailed random walk
with volatility clustering and an intraday session pattern, calibrated to Terminal 14
(XAUUSD.pc ~4142, median M15 ATR(14) 7.70, spread 0.10, V = 100 USC per lot per 1.00).

A random walk has no trend for the signal to find, so this measures the ladder's risk
mechanics and cost, not the signal's edge. Only real-tick MT5 runs can measure that.

    python3 tools/backtest_sim.py --years 3 --seeds 5 --deposit 40000
"""
import argparse
import math
from dataclasses import dataclass, field

import numpy as np

import ladder_model as m

STEP_SEC = 15
STEPS_PER_BAR = 60                # M15
BARS_PER_DAY = 92                 # 01:00-24:00 server time
V = 100.0                         # USC per lot per 1.00 move
LOT_STEP, VMIN, VMAX = 0.01, 0.01, 500.0
STOPS_DIST = 0.20                 # 20 points
LEVERAGE = 500.0


@dataclass
class Inputs:
    lookback: int = 64
    t_min: float = 3.0
    er_min: float = 0.25
    atr_period: int = 14
    step_atr: float = 1.5
    target_atr: float = 1.5
    target_spreads: float = 5.0
    max_steps: int = 6
    loss_cap_pct: float = 5.0
    margin_pct: float = 50.0
    max_spread: float = 0.40
    cooldown_hours: int = 4
    max_fails_per_day: int = 2
    no_new_minutes: int = 180
    flatten_minutes: int = 15


# ---------------------------------------------------------------- market
def make_market(years, seed, target_atr=7.70, price0=4142.0):
    rng = np.random.default_rng(seed)
    days = int(years * 52) * 5
    n_bars = days * BARS_PER_DAY
    hours = 1 + (np.arange(n_bars) % BARS_PER_DAY) / 4.0
    session = np.select([hours < 9, hours < 15, hours < 19], [0.6, 1.0, 1.4], 0.8)
    h = np.zeros(n_bars)                              # log-vol, AR(1) per bar
    eta = rng.normal(0, 0.045, n_bars)
    for k in range(1, n_bars):
        h[k] = 0.985 * h[k - 1] + eta[k]
    bar_sigma = session * np.exp(h)
    steps = n_bars * STEPS_PER_BAR
    z = rng.standard_t(4, steps) / math.sqrt(2.0)     # unit-variance fat tails
    inc = np.repeat(bar_sigma, STEPS_PER_BAR) * z
    # Daily break and weekend gaps, applied at each day's first step.
    day_start = np.arange(days) * BARS_PER_DAY * STEPS_PER_BAR
    gap_sd = np.where(np.arange(days) % 5 == 0, 3.0, 1.0)
    inc[day_start] += rng.normal(0, 1, days) * gap_sd
    bid = price0 + np.cumsum(inc)

    # Scale so the median M15 ATR matches Terminal 14.
    atr = bar_atr(bid, 14)
    scale = target_atr / np.nanmedian(atr)
    bid = price0 + (bid - price0) * scale

    spread = np.full(steps, 0.10)
    open_steps = 5 * 60 // STEP_SEC                    # wide spread for 5 min after open
    for s0 in day_start:
        spread[s0:s0 + open_steps] = 0.60
    ask = bid + spread
    t = np.arange(steps)
    day = t // (BARS_PER_DAY * STEPS_PER_BAR)
    sec_in_day = 3600 + (t % (BARS_PER_DAY * STEPS_PER_BAR)) * STEP_SEC
    return bid, ask, day, sec_in_day


def bars_from(bid):
    b = bid.reshape(-1, STEPS_PER_BAR)
    return b[:, 0], b.max(1), b.min(1), b[:, -1]


def bar_atr(bid, period):
    o, hi, lo, c = bars_from(bid)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(hi - lo, np.maximum(abs(hi - prev), abs(lo - prev)))
    out = np.full(len(tr), np.nan)
    cs = np.cumsum(tr)
    out[period - 1:] = (cs[period - 1:] - np.concatenate([[0], cs[:-period]])) / period
    return out


def signals(close, n):
    """t-stat and efficiency ratio for the window ending at each bar (inclusive)."""
    tstat = np.full(len(close), 0.0)
    er = np.full(len(close), 0.0)
    w = np.lib.stride_tricks.sliding_window_view(np.log(close), n)
    x = np.arange(n) - (n - 1) / 2
    sxx = (x * x).sum()
    ym = w.mean(1, keepdims=True)
    b = ((w - ym) * x).sum(1) / sxx
    sse = ((w - ym - b[:, None] * x) ** 2).sum(1)
    se = np.sqrt(np.maximum(sse, 1e-30) / (n - 2) / sxx)
    tstat[n - 1:] = b / se
    cw = np.lib.stride_tricks.sliding_window_view(close, n)
    path = np.abs(np.diff(cw, axis=1)).sum(1)
    er[n - 1:] = np.abs(cw[:, -1] - cw[:, 0]) / np.where(path > 0, path, np.inf)
    return tstat, er


# ---------------------------------------------------------------- EA
@dataclass
class Result:
    balance: float
    ladders: list = field(default_factory=list)   # (filled, n, pnl, pct)
    max_dd_pct: float = 0.0
    skipped_cap: int = 0


def run(bid, ask, day, sec, inp: Inputs, deposit):
    o, hi, lo, close = bars_from(bid)
    atr = bar_atr(bid, inp.atr_period)
    tstat, er = signals(close, inp.lookback)
    n_steps = len(bid)
    res = Result(balance=deposit)
    peak = deposit
    cooldown_until = -1
    fails = {}
    s = inp.max_spread
    k = inp.lookback + 1
    n_bars = len(close)
    while k < n_bars:
        i = k * STEPS_PER_BAR                          # first step of bar k
        d_ = day[i]
        friday = d_ % 5 == 4
        secs_to_close = 86400 - sec[i]
        if (i < cooldown_until or fails.get(d_, 0) >= inp.max_fails_per_day
                or ask[i] - bid[i] > s + 1e-9
                or (friday and secs_to_close < inp.no_new_minutes * 60)):
            k += 1
            continue
        tv, ev = tstat[k - 1], er[k - 1]
        side = (1 if tv > 0 else -1) if abs(tv) >= inp.t_min and ev >= inp.er_min else 0
        if side == 0 or np.isnan(atr[k - 1]):
            k += 1
            continue
        d = inp.step_atr * atr[k - 1]
        t = inp.target_atr * atr[k - 1]
        min_dist = STOPS_DIST + s
        if t < inp.target_spreads * s or d <= min_dist or t <= min_dist:
            k += 1
            continue
        mpl = bid[i] * V / LEVERAGE
        l1, n, lots = m.first_lot(res.balance, inp.loss_cap_pct / 100, inp.max_steps, d, t, s, 0,
                                  V, LOT_STEP, VMIN, VMAX, mpl, res.balance, inp.margin_pct / 100)
        if lots is None:
            res.skipped_cap += 1
            k += 1
            continue

        bal0 = res.balance
        j, pnl, filled, low_eq = ladder(bid, ask, day, sec, i, side, lots, d, t, s, inp)
        res.balance += pnl
        peak = max(peak, bal0)
        res.max_dd_pct = max(res.max_dd_pct, 100 * (peak - (bal0 + low_eq)) / peak)
        peak = max(peak, res.balance)
        res.ladders.append((filled, len(lots), pnl, 100 * pnl / bal0))
        if pnl < 0:
            fails[day[j]] = fails.get(day[j], 0) + 1
            cooldown_until = j + inp.cooldown_hours * 3600 // STEP_SEC
        k = j // STEPS_PER_BAR + 1
    return res


def ladder(bid, ask, day, sec, i, side1, lots, d, t, s, inp, chunk=4000):
    """Runs one ladder from step i. Returns (exit step, pnl USC, filled, worst open pnl)."""
    pos = [(side1, lots[0], ask[i] if side1 > 0 else bid[i])]
    upper, lower = (pos[0][2], pos[0][2] - d) if side1 > 0 else (pos[0][2] + d, pos[0][2])
    n = len(lots)
    worst = 0.0
    j = i + 1
    end = len(bid)
    while j < end:
        e = min(end, j + chunk)
        b, a = bid[j:e], ask[j:e]
        has_buy = any(p[0] > 0 for p in pos)
        has_sell = any(p[0] < 0 for p in pos)
        nxt = -pos[-1][0] if len(pos) < n else 0
        cond = np.zeros(e - j, bool)
        if has_buy:
            cond |= (b >= upper + t) | (b <= lower - t - s)
        if has_sell:
            cond |= (a <= lower - t) | (a >= upper + t + s)
        if nxt > 0:
            cond |= a >= upper
        elif nxt < 0:
            cond |= b <= lower
        # Weekend flatten 15 min before Friday close.
        fri = (day[j:e] % 5 == 4) & (86400 - sec[j:e] <= inp.flatten_minutes * 60)
        cond |= fri
        # Track worst open P&L at bar resolution for drawdown.
        worst = min(worst, open_pnl(pos, b[::STEPS_PER_BAR], a[::STEPS_PER_BAR]).min())
        hits = np.flatnonzero(cond)
        if len(hits) == 0:
            j = e
            continue
        q = j + hits[0]
        bq, aq = bid[q], ask[q]
        # Every order fills at the price of the sample that triggers it, as the MT5
        # real-tick tester does. Filling stops at their level instead would hand the
        # strategy the overshoot of every jump for free.
        if nxt > 0 and aq >= upper:
            pos.append((1, lots[len(pos)], aq))
        elif nxt < 0 and bq <= lower:
            pos.append((-1, lots[len(pos)], bq))
        exit_now = fri[hits[0]] or any(
            (p[0] > 0 and (bq >= upper + t or bq <= lower - t - s)) or
            (p[0] < 0 and (aq <= lower - t or aq >= upper + t + s)) for p in pos)
        if exit_now:
            pnl = float(open_pnl(pos, bid[q:q + 1], ask[q:q + 1])[0])
            return q, pnl, len(pos), min(worst, pnl)
        j = q + 1
    pnl = float(open_pnl(pos, bid[-1:], ask[-1:])[0])
    return end - 1, pnl, len(pos), min(worst, pnl)


def open_pnl(pos, b, a):
    tot = np.zeros(len(b))
    for sd, lot, px in pos:
        tot += V * lot * ((b - px) if sd > 0 else (px - a))
    return tot


# ---------------------------------------------------------------- report
def summarise(res, deposit, inp, label):
    L = res.ladders
    n = len(L)
    wins = sum(1 for f, _, p, _ in L if p >= 0)
    first = sum(1 for f, _, p, _ in L if p >= 0 and f == 1)
    caps = sum(1 for f, nn, p, _ in L if p < 0 and f >= nn)
    worst = max([-pct for *_, pct in L if pct < 0], default=0.0)
    hist = {}
    for f, *_ in L:
        hist[f] = hist.get(f, 0) + 1
    be = inp.step_atr / (inp.step_atr + inp.target_atr)
    net = res.balance - deposit
    wr = first / n if n else 0
    ok = net > 0 and wr > be and worst <= 6 and res.max_dd_pct <= 30
    print(f"{label}: {n} ladders, {wins} won ({first} at trade 1), {n - wins} lost "
          f"({caps} at step cap); fills by step {dict(sorted(hist.items()))}")
    print(f"  net {net:+.0f} USC ({100 * net / deposit:+.1f}%)  "
          f"first-trade win {100 * wr:.1f}% vs break-even {100 * be:.1f}%  "
          f"worst ladder -{worst:.2f}%  max DD {res.max_dd_pct:.1f}%  "
          f"skipped (cap) {res.skipped_cap}  -> {'PASS' if ok else 'FAIL'}")
    return net, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--deposit", type=float, default=40000)
    ap.add_argument("--max-steps", type=int, default=6)
    ap.add_argument("--atr-mult", type=float, default=1.5)
    args = ap.parse_args()
    inp = Inputs(max_steps=args.max_steps, step_atr=args.atr_mult, target_atr=args.atr_mult)
    nets = []
    for seed in range(args.seeds):
        bid, ask, day, sec = make_market(args.years, seed)
        atr = bar_atr(bid, 14)
        res = run(bid, ask, day, sec, inp, args.deposit)
        print(f"seed {seed}: price {bid.min():.0f}-{bid.max():.0f}, M15 ATR median "
              f"{np.nanmedian(atr):.2f} p10 {np.nanpercentile(atr, 10):.2f} "
              f"p90 {np.nanpercentile(atr, 90):.2f}")
        net, _ = summarise(res, args.deposit, inp, f"  {args.years:g}y")
        nets.append(net)
    print(f"\nall seeds: mean net {np.mean(nets):+.0f} USC, "
          f"{sum(x > 0 for x in nets)}/{len(nets)} profitable")


if __name__ == "__main__":
    main()
