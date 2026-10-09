"""M1 burst fade on real ticks (14 days): after an L-minute move with |z|>thr, trade against it.
market: enter at the touch (ask for a buy) at the signal, exit at the touch H minutes later.
limit : rest a limit at the near touch (bid for a buy) for 60 s; filled only when the far touch reaches it (ask <= limit);
        exit at market H minutes after the fill. No extra cost: real bid/ask are used."""
import sys
import numpy as np
import pandas as pd
import realdata as rd

days = rd.tick_days()
rows = []
for di, p in enumerate(days):
    t, b, a = rd.ticks(p)
    minute = t // 60000
    last = np.flatnonzero(np.diff(minute, append=minute[-1] + 1))     # last tick of each minute
    c, mt = b[last], minute[last]
    r1 = np.diff(c, prepend=c[0])
    vol = pd.Series(r1).rolling(200).std().to_numpy()
    for L, H, zt in ((3, 3, 2.0), (3, 3, 2.5), (3, 5, 2.5), (5, 5, 2.5), (2, 2, 3.0), (1, 2, 3.0), (1, 1, 3.0)):
        for i in range(max(200, L), len(c)):
            if mt[i] - mt[i - L] != L or np.isnan(vol[i]) or vol[i] == 0:
                continue
            z = (c[i] - c[i - L]) / (vol[i] * np.sqrt(L))
            if abs(z) <= zt:
                continue
            side = -1 if z > 0 else 1
            k0 = last[i] + 1
            if k0 >= len(t):
                continue
            t0 = t[k0]
            kx = np.searchsorted(t, t0 + H * 60000)
            if kx >= len(t):
                continue
            mkt = (b[kx] - a[k0]) if side > 0 else (b[k0] - a[kx])
            lim = b[k0] if side > 0 else a[k0]
            k1 = np.searchsorted(t, t0 + 60000)
            seg = a[k0 + 1:k1] <= lim if side > 0 else b[k0 + 1:k1] >= lim
            lp = np.nan
            if seg.any():
                kf = k0 + 1 + int(np.argmax(seg))
                ke = np.searchsorted(t, t[kf] + H * 60000)
                if ke < len(t):
                    lp = (b[ke] - lim) if side > 0 else (lim - a[ke])
            rows.append((di, f"L={L} H={H} z>{zt}", mkt, lp, a[k0] - b[k0]))

df = pd.DataFrame(rows, columns=["day", "rule", "mkt", "lim", "spr"])
def st(x):
    x = x.dropna()
    if len(x) < 10: return f"n={len(x):4d}"
    return f"n={len(x):4d} {x.mean():+.3f} t {x.mean() / x.std() * np.sqrt(len(x)):+.1f} win {100 * (x > 0).mean():.0f}%"
half = len(days) * 6 // 10
print(f"{len(days)} tick days; first {half} = train, rest = test; per oz, real bid/ask")
for rule, g in df.groupby("rule", sort=False):
    tr, te = g[g.day < half], g[g.day >= half]
    print(f"{rule:16s} market: train {st(tr.mkt)} | test {st(te.mkt)}")
    print(f"{'':16s} limit : train {st(tr.lim)} | test {st(te.lim)}   fill rate {100 * g.lim.notna().mean():.0f}%  spread at signal {g.spr.median():.2f}")
