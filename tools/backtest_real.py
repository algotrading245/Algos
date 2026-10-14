"""AurumLadder EA rules run on the real XAUUSD.pc history in marketdata/.

Signals come from real M15 bars. The price path inside each bar is rebuilt from the
finest bars held for that date (M15 before 2025-05, M5 until 2026-06-30, M1 after) as
open -> low -> high -> close for an up bar and open -> high -> low -> close for a down
bar. Spread is the bar's recorded spread, floored at the 0.11 measured on real ticks.

    python tools\\backtest_real.py --deposit 40000
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research"))
import backtest_sim as b
import ladder_model as m
import realdata as rd

SPREAD_FLOOR = 0.11


def steps_from(df, seconds):
    up = (df.close >= df.open).to_numpy()
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    px = np.stack([o, np.where(up, l, h), np.where(up, h, l), c], 1).ravel()
    t0 = df.time.to_numpy(np.int64)
    t = np.stack([t0, t0 + seconds // 3, t0 + 2 * seconds // 3, t0 + seconds - 1], 1).ravel()
    sp = np.repeat(np.maximum(df.spread.to_numpy(float), SPREAD_FLOOR), 4)
    return t, px, sp


def market():
    m15, m5, m1 = rd.bars("M15"), rd.bars("M5"), rd.bars("M1")
    cut5, cut1 = m5.time.iloc[0], m1.time.iloc[0]
    cut5 -= cut5 % 900
    cut1 -= cut1 % 900
    parts = [steps_from(m15[m15.time < cut5], 900),
             steps_from(m5[(m5.time >= cut5) & (m5.time < cut1)], 300),
             steps_from(m1[m1.time >= cut1], 60)]
    t, bid, sp = (np.concatenate(x) for x in zip(*parts))
    return m15, t, bid, bid + sp


def atr_of(df, period):
    h, l, c = df.high.to_numpy(float), df.low.to_numpy(float), df.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    out = np.full(len(tr), np.nan)
    cs = np.cumsum(tr)
    out[period - 1:] = (cs[period - 1:] - np.concatenate([[0], cs[:-period]])) / period
    return out


def is_friday(t):
    return (t // 86400 + 3) % 7 == 4


def run(m15, t, bid, ask, inp, deposit, start=None, end=None):
    close = m15.close.to_numpy(float)
    bt = m15.time.to_numpy(np.int64)
    atr = atr_of(m15, inp.atr_period)
    tstat, er = b.signals(close, inp.lookback)
    res = b.Result(balance=deposit)
    res.when = []
    peak = deposit
    cooldown_until = -1
    fails = {}
    s = inp.max_spread
    c = inp.commission_lot / b.V
    k = inp.lookback + 1
    at = None                                   # path point to start from, set right after a ladder closed
    while k < len(close):
        now, at = at, None
        if (start and bt[k] < start) or (end and bt[k] >= end):
            k += 1
            continue
        i = int(np.searchsorted(t, bt[k])) if now is None else now
        if i >= len(t) - 1:
            break
        day = t[i] // 86400
        if (t[i] < cooldown_until or (inp.max_fails_per_day > 0 and fails.get(day, 0) >= inp.max_fails_per_day)
                or (now is None and t[i] - bt[k] > 300) or ask[i] - bid[i] > s + 1e-9
                or (is_friday(t[i]) and 86400 - t[i] % 86400 < inp.no_new_minutes * 60)):
            k += 1
            continue
        tv, ev = tstat[k - 1], er[k - 1]
        side = (1 if tv > 0 else -1) if abs(tv) >= inp.t_min and ev >= inp.er_min else 0
        if side == 0 and inp.restart_now and not np.isnan(tv):
            side = 1 if tv >= 0 else -1
        if side == 0 or np.isnan(atr[k - 1]):
            k += 1
            continue
        d = inp.step_atr * atr[k - 1]
        tg = inp.target_atr * atr[k - 1]
        mpl = bid[i] * b.V / b.LEVERAGE
        size = (res.balance, inp.loss_cap_pct / 100, inp.max_steps, d, tg, s, c, b.V, b.LOT_STEP, b.VMIN, b.VMAX)
        if inp.profit_min > 0 and tg > c:
            l1, n, lots, tg = m.profit_ladder(*size, inp.profit_min, inp.profit_max, mpl, res.balance,
                                              inp.margin_pct / 100)
        else:
            l1, n, lots = m.first_lot(*size, mpl, res.balance, inp.margin_pct / 100)
        min_dist = b.STOPS_DIST + s
        if tg < inp.target_spreads * s or d <= min_dist or tg <= min_dist or tg <= c:
            k += 1
            continue
        if lots is None:
            res.skipped_cap += 1
            k += 1
            continue
        bal0 = res.balance
        j, pnl, filled, low_eq = ladder(t, bid, ask, i, side, lots, d, tg, s, inp)
        pnl -= inp.commission_lot * sum(lots[:filled])
        res.balance += pnl
        peak = max(peak, bal0)
        res.max_dd_pct = max(res.max_dd_pct, 100 * (peak - (bal0 + low_eq)) / peak)
        peak = max(peak, res.balance)
        res.ladders.append((filled, len(lots), pnl, 100 * pnl / bal0))
        res.when.append(int(t[i]))
        if pnl < 0:
            dj = t[j] // 86400
            fails[dj] = fails.get(dj, 0) + 1
            cooldown_until = t[j] + inp.cooldown_hours * 3600
        k = int(np.searchsorted(bt, t[j], side="right"))
        if inp.restart_now and j + 1 < len(t) - 1:
            k, at = int(np.searchsorted(bt, t[j + 1], side="right")) - 1, j + 1
    return res


def ladder(t, bid, ask, i, side1, lots, d, tg, s, inp, chunk=4000):
    """One ladder from step i. Returns (exit step, pnl USC, filled, worst open pnl)."""
    px0 = ask[i] if side1 > 0 else bid[i]
    pos = [(side1, lots[0], px0)]
    upper, lower = (px0, px0 - d) if side1 > 0 else (px0 + d, px0)
    n = len(lots)
    worst = 0.0
    j = i + 1
    end = len(bid)
    while j < end:
        e = min(end, j + chunk)
        bb, aa, tt = bid[j:e], ask[j:e], t[j:e]
        has_buy = any(p[0] > 0 for p in pos)
        has_sell = any(p[0] < 0 for p in pos)
        nxt = -pos[-1][0] if len(pos) < n else 0
        cond = np.zeros(e - j, bool)
        if has_buy:
            cond |= (bb >= upper + tg) | (bb <= lower - tg - s)
        if has_sell:
            cond |= (aa <= lower - tg) | (aa >= upper + tg + s)
        if nxt > 0:
            cond |= aa >= upper
        elif nxt < 0:
            cond |= bb <= lower
        fri = is_friday(tt) & (86400 - tt % 86400 <= inp.flatten_minutes * 60)
        cond |= fri
        hits = np.flatnonzero(cond)
        q_rel = hits[0] if len(hits) else e - j - 1
        worst = min(worst, b.open_pnl(pos, bb[:q_rel + 1], aa[:q_rel + 1]).min())
        if len(hits) == 0:
            j = e
            continue
        q = j + q_rel
        bq, aq = bid[q], ask[q]
        sp = aq - bq
        # Price moves continuously inside a bar, so a level crossed there fills at the
        # level. The first point of a bar can gap past it and then fills at the open.
        gap = q % 4 == 0
        if nxt > 0 and aq >= upper:
            pos.append((1, lots[len(pos)], aq if gap else upper))
        elif nxt < 0 and bq <= lower:
            pos.append((-1, lots[len(pos)], bq if gap else lower))
        has_buy = any(p[0] > 0 for p in pos)
        has_sell = any(p[0] < 0 for p in pos)
        out = None
        if has_buy and bq >= upper + tg:
            out = upper + tg
        elif has_sell and aq >= upper + tg + s:
            out = upper + tg + s - sp
        elif has_sell and aq <= lower - tg:
            out = lower - tg - sp
        elif has_buy and bq <= lower - tg - s:
            out = lower - tg - s
        elif fri[q_rel]:
            out = bq
        if out is not None:
            xb = np.array([bq if gap else out])
            pnl = float(b.open_pnl(pos, xb, xb + sp)[0])
            return q, pnl, len(pos), min(worst, pnl)
        j = q + 1
    pnl = float(b.open_pnl(pos, bid[-1:], ask[-1:])[0])
    return end - 1, pnl, len(pos), min(worst, pnl)


def by_year(res):
    years = {}
    for ts, (_, _, pnl, pct) in zip(res.when, res.ladders):
        y = 1970 + int(ts // (365.2425 * 86400))
        n, w, tot = years.get(y, (0, 0, 0.0))
        years[y] = (n + 1, w + (pnl >= 0), tot + pct)
    return "  ".join(f"{y}: {n} ladders {100 * w / n:.0f}% won, sum {tot:+.1f}%"
                     for y, (n, w, tot) in sorted(years.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deposit", type=float, default=40000)
    ap.add_argument("--profit", type=float, nargs=2, metavar=("MIN", "MAX"),
                    help="size the first lot so a won ladder pays MIN..MAX USC, restart at once, no cooldown")
    ap.add_argument("--commission", type=float, default=0.0, help="USC per lot, round trip")
    args = ap.parse_args()
    m15, t, bid, ask = market()
    print(f"{len(m15)} M15 bars, {len(t)} path points, "
          f"{m15.dt.iloc[0]:%Y-%m-%d} to {m15.dt.iloc[-1]:%Y-%m-%d}")
    for steps in (6, 3):
        for mult in (1.0, 1.5, 2.5):
            inp = b.Inputs(max_steps=steps, step_atr=mult, target_atr=mult, commission_lot=args.commission)
            if args.profit:
                inp.profit_min, inp.profit_max = args.profit
                inp.restart_now, inp.cooldown_hours = True, 0
            res = run(m15, t, bid, ask, inp, args.deposit)
            b.summarise(res, args.deposit, inp, f"N={steps} zone={mult}xATR")
            print("  " + by_year(res))


if __name__ == "__main__":
    main()
