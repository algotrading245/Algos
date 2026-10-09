"""Channel breakout, follow or fade, with levels from coarse bars and fills walked along a finer price path.
scan5 was biased for the fade (it ignored the move beyond the level inside the entry bar); this walks every path point.
Path: 4 points per fine bar (O,L,H,C for an up bar, O,H,L,C for a down bar). Levels crossed inside a bar fill at the level,
at a bar open they fill at the open. Cost 0.16 per oz per round trip. One position at a time, flat before a session break."""
import sys
import numpy as np
import pandas as pd
import realdata as rd

COST = 0.16

def path(df, seconds):
    up = (df.close >= df.open).to_numpy()
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    px = np.stack([o, np.where(up, l, h), np.where(up, h, l), c], 1).ravel()
    t0 = df.time.to_numpy(np.int64)
    t = np.stack([t0, t0 + seconds // 3, t0 + 2 * seconds // 3, t0 + seconds - 1], 1).ravel()
    return t, px

def levels(coarse, N, sec):
    h, l, c = coarse.high.to_numpy(float), coarse.low.to_numpy(float), coarse.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    atr = pd.Series(tr).rolling(14).mean().shift().to_numpy()
    hh = pd.Series(h).rolling(N).max().shift().to_numpy()
    ll = pd.Series(l).rolling(N).min().shift().to_numpy()
    return coarse.time.to_numpy(np.int64), hh, ll, atr

def run(T, P, ct, hh, ll, atr, csec, tp_k, sl_k, hold, fade, hours=None):
    ci = np.searchsorted(ct, T, "right") - 1
    fresh = (T - ct[np.maximum(ci, 0)]) < csec           # path point lies inside a coarse bar that exists
    out = []
    side = 0
    last_bar = -1
    n = len(P)
    for q in range(1, n):
        p = P[q]
        gap = q % 4 == 0
        if side == 0:
            k = ci[q]
            if k < 0 or not fresh[q] or k == last_bar or np.isnan(hh[k]) or np.isnan(atr[k]):
                continue
            if hours is not None and not hours[(T[q] % 86400) // 3600]:
                continue
            if q + 1 < n and T[q + 1] - T[q] > 1800:
                continue
            brk = 1 if p > hh[k] else (-1 if p < ll[k] else 0)
            if brk == 0:
                continue
            # a level is only a fill price if the path crossed it on this leg; if price was already beyond it, fill at that price
            lvl = p if gap else (max(hh[k], P[q - 1]) if brk > 0 else min(ll[k], P[q - 1]))
            side = -brk if fade else brk
            entry, t_in, last_bar = lvl, T[q], k
            tp, sl = entry + side * tp_k * atr[k], entry - side * sl_k * atr[k]
        if side != 0:
            x = None
            if side * (p - sl) <= 0 and not (T[q] == t_in and side * (p - entry) > 0):
                x = p if (gap and T[q] != t_in) else sl
            elif side * (p - tp) >= 0:
                x = tp
            elif T[q] - t_in >= hold or q + 1 == n or T[q + 1] - T[q] > 1800:
                x = p
            if x is not None:
                out.append((t_in, side * (x - entry) - COST, T[q] - t_in))
                side = 0
    return np.array(out)

def show(name, res, t_split):
    if len(res) < 60:
        print(f"{name:44s} too few trades ({len(res)})"); return
    parts, ok = [], True
    for mk in (res[:, 0] < t_split, res[:, 0] >= t_split):
        p = res[mk, 1]
        if len(p) < 20:
            parts.append("n<20"); ok = False; continue
        tt = p.mean() / p.std() * np.sqrt(len(p))
        ok &= p.mean() > 0 and tt > 2
        parts.append(f"n={len(p):5d} net {p.mean():+.3f} t {tt:+.1f} win {100 * (p > 0).mean():.0f}% hold {np.median(res[mk, 2]) / 60:.0f}m")
    print(f"{name:44s} train {parts[0]} | test {parts[1]}{'  <==' if ok else ''}")

m1, m5, m15 = rd.bars("M1"), rd.bars("M5"), rd.bars("M15")
setups = [("M15 levels, M5 path (17 months)", m15, 900, m5, 300),
          ("M5 levels, M1 path (3.5 months)", m5[m5.time >= m1.time.iloc[0] - 86400 * 3], 300, m1, 60),
          ("M15 levels, M1 path (3.5 months)", m15[m15.time >= m1.time.iloc[0] - 86400 * 10], 900, m1, 60)]
for title, coarse, csec, fine, fsec in setups:
    coarse = coarse.reset_index(drop=True)
    T, P = path(fine, fsec)
    t_split = T[int(len(T) * 0.6)]
    print(f"\n=== {title}; net of {COST}")
    for N in (12, 48, 96):
        ct, hh, ll, atr = levels(coarse, N, csec)
        for tp_k, sl_k in ((1, 1), (2, 1), (1, 2), (0.5, 1)):
            for fade in (False, True):
                res = run(T, P, ct, hh, ll, atr, csec, tp_k, sl_k, 48 * csec, fade)
                show(f"N={N} tp={tp_k} sl={sl_k} {'fade' if fade else 'follow'}", res, t_split)
