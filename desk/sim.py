"""The desk's trade simulator (owner 2026-11-02): 10,000 bootstrapped paths, read-only, no tokens.

  ticket   view sim SYM ENTRY STOP TARGET HOURS [atr=X] [tf=H1] [n=10000]
           The odds that a trade reaches its target before its stop, its stop first, or neither by the deadline, on
           paths resampled from the market's own bars before the holdout (blocks of 24 bars keep volatility clusters),
           in ATR units and scaled to today's ATR. Two answers: "neutral" removes the history's drift (what a trade
           with no edge gets), "history" keeps it. A pod's forecast above the neutral odds must say where the gap
           comes from; a target the paths rarely reach in the time allowed is too far for that clock.
  edge     view sim edge NAME MARKET [n=20] [live=R] [key=value ...]
           Resamples the edge's sandbox trades: the spread of total R over the next n trades, the drawdown and the
           losing streak. With live=R (the leg's live total over its last n trades) it gives that total's percentile:
           above the 5th is an ordinary losing run, below it the edge is likely broken.

A simulator built from past returns cannot see direction: on neutral paths a 1.5R target before a 1R stop comes out
near 1 / (1 + 1.5) = 40%, a losing bet after costs. It checks the clock, the distances and the calibration of a
ticket; it is not a forecast.
"""
import math

import numpy as np

from desk import paths
from desk.edges import base

SECS = {"M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
N_PATHS = 10_000
BLOCK = 24
MAX_BARS = 1500
CLIP = 20.0  # bars beyond 20 ATR are data gaps, not moves


def auto_tf(hours):
    return "M15" if hours <= 12 else "H1" if hours <= 240 else "H4"


def unit_bars(df):
    """Each bar's high, low and close against the prior close, in units of the prior bar's ATR(14): (n, 3)."""
    a = base.atr(df, 14).shift(1).values
    pc = df["close"].shift(1).values
    rel = np.column_stack([(df[k].values - pc) / a for k in ("high", "low", "close")])
    rel = rel[np.isfinite(rel).all(axis=1) & (a > 0)]
    return np.clip(rel, -CLIP, CLIP)


def _paths(rel, k, n, rng):
    """n paths of k bars, drawn as blocks of BLOCK consecutive bars: (n, k, 3)."""
    b = min(BLOCK, k)
    nb = math.ceil(k / b)
    starts = rng.integers(0, len(rel) - b + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(b)).reshape(n, nb * b)[:, :k]
    return rel[idx]


def odds(rel, entry, stop, target, bars, atr_now, n=N_PATHS, seed=7, drift=False):
    """{target, stop, neither, r_at_deadline (median, paths that hit neither), ev_r (before costs)}."""
    d = 1 if target > entry else -1
    risk, reward = (entry - stop) * d, (target - entry) * d
    if risk <= 0 or reward <= 0:
        raise ValueError("the stop and the target must sit on opposite sides of the entry")
    rel = rel if drift else rel - rel[:, 2].mean()  # a shift of the whole bar keeps its shape
    rng = np.random.default_rng(seed)
    hits = {"target": 0, "stop": 0, "neither": 0}
    left, end_r = n, []
    while left:
        m = min(left, max(1, 3_000_000 // max(bars, 1)))
        p = _paths(rel, bars, m, rng) * atr_now
        pc = entry + np.concatenate([np.zeros((m, 1)), np.cumsum(p[:, :-1, 2], axis=1)], axis=1)
        hi, lo, cl = pc + p[:, :, 0], pc + p[:, :, 1], pc + p[:, :, 2]
        s_hit = (lo <= stop) if d > 0 else (hi >= stop)
        t_hit = (hi >= target) if d > 0 else (lo <= target)
        big = bars + 1
        s_at = np.where(s_hit.any(1), s_hit.argmax(1), big)
        t_at = np.where(t_hit.any(1), t_hit.argmax(1), big)
        stop_first = (s_at <= t_at) & (s_at < big)  # the same bar counts as the stop, as in the sandbox
        tgt_first = (t_at < s_at)
        hits["stop"] += int(stop_first.sum())
        hits["target"] += int(tgt_first.sum())
        none = ~(stop_first | tgt_first)
        hits["neither"] += int(none.sum())
        end_r.append((cl[none, -1] - entry) * d / risk)
        left -= m
    end_r = np.concatenate(end_r)
    pr = {k: round(v / n, 3) for k, v in hits.items()}
    mean_end = float(end_r.mean()) if len(end_r) else 0.0
    return pr | {"r_at_deadline": round(float(np.median(end_r)), 2) if len(end_r) else None,
                 "ev_r": round(pr["target"] * reward / risk - pr["stop"] + pr["neither"] * mean_end, 3)}


def ticket(sym, entry, stop, target, hours, atr_now=None, tf=None, n=N_PATHS, cfg=None, atr_from=None):
    cfg = cfg or paths.config()
    entry, stop, target, hours = float(entry), float(stop), float(target), float(hours)
    tf = (tf or auto_tf(hours)).upper()
    if tf not in SECS:
        raise ValueError(f"tf {tf}: one of {', '.join(SECS)}")
    df = base.hist_bars(sym, tf, cfg)
    rel = unit_bars(df)
    if len(rel) < 500:
        raise ValueError(f"only {len(rel)} usable {tf} bars of {sym} history")
    if atr_now is None:
        atr_now, atr_from = float(base.atr(df, 14).iloc[-1]), "history's last bar (before 2025-10-13), not live"
    bars = min(MAX_BARS, max(1, math.ceil(hours * 3600 / SECS[tf])))
    d = 1 if target > entry else -1
    risk, reward = (entry - stop) * d, (target - entry) * d
    spec = cfg["instruments"].get(sym, {})
    cost_r = round(float(spec.get("cost") or 0) / risk, 3) if risk > 0 else None
    neutral = odds(rel, entry, stop, target, bars, atr_now, n)
    hist = odds(rel, entry, stop, target, bars, atr_now, n, drift=True)
    rr = reward / risk
    return {"symbol": sym, "side": "buy" if d > 0 else "sell", "rr": round(rr, 2), "tf": tf, "bars": bars,
            "atr": round(atr_now, 6), "atr_from": atr_from or "given",
            "stop_atr": round(risk / atr_now, 2), "target_atr": round(reward / atr_now, 2),
            "neutral": neutral, "history": hist, "random_walk_no_deadline": round(1 / (1 + rr), 3),
            "cost_r": cost_r, "paths": n, "history_bars": len(rel),
            "read": _read(neutral, rr, cost_r)}


def _read(nt, rr, cost_r):
    out = [f"a trade with no edge reaches the target first {nt['target']:.0%} of the time; your forecast above that "
           "needs a reason"]
    if nt["neither"] >= 0.3:
        out.append(f"{nt['neither']:.0%} of paths hit neither by the deadline: the target is far for this clock")
    if cost_r and cost_r >= 0.1:
        out.append(f"costs are {cost_r:.2f}R a round trip: the stop is tight against the spread")
    return "; ".join(out)


def edge(name, market, n_next=20, live=None, params=None, n=N_PATHS, cfg=None, seed=7):
    from desk import sandbox
    trades = sandbox.edge_trades(name, market, params, cfg=cfg)
    r = np.array([x["r"] for x in trades], dtype=float)
    if len(r) < 10:
        raise ValueError(f"{name} on {market}: {len(r)} sandbox trades, too few to resample")
    rng = np.random.default_rng(seed)
    draw = r[rng.integers(0, len(r), size=(n, int(n_next)))]
    tot = draw.sum(1)
    eq = np.cumsum(draw, axis=1)
    dd = (np.maximum.accumulate(np.maximum(eq, 0), axis=1) - eq).max(1)
    streak = np.zeros(n, dtype=int)
    cur = np.zeros(n, dtype=int)
    for j in range(draw.shape[1]):
        cur = np.where(draw[:, j] < 0, cur + 1, 0)
        streak = np.maximum(streak, cur)
    pct = {f"p{q}": round(float(np.percentile(tot, q)), 2) for q in (5, 25, 50, 75, 95)}
    out = {"edge": name, "market": market, "history_trades": len(r), "avg_r": round(float(r.mean()), 3),
           "next": int(n_next), "total_r": pct, "p_loss": round(float((tot < 0).mean()), 3),
           "max_dd_r": {"p50": round(float(np.median(dd)), 2), "p95": round(float(np.percentile(dd, 95)), 2)},
           "losing_streak": {"p50": int(np.median(streak)), "p95": int(np.percentile(streak, 95))}}
    if live is not None:
        q = float((tot <= float(live)).mean())
        out["live"] = {"total_r": float(live), "percentile": round(q, 3),
                       "read": "below the 5th percentile: unlikely to be bad luck, the edge may be broken" if q < 0.05
                       else "inside the history's range: an ordinary run"}
    return out
