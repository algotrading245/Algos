"""Shu-Yu-Mulvey statistical jump model 0/1 regime filter, long US500/US100 (ES/NQ daily futures as proxy) in bull only.

Pre-registered: lambda 50, features EWM downside dev hl10, EWM Sortino hl20 and hl60, refit every 126 days on the last
3000 days, online state = Viterbi end state over the window, signal at close t, position held from t+2 (1-day delay).
Costs: 1 bp per side per switch (1x), plus 3%/yr financing while long. Variant B (window 1250d) is a second trial,
declared because 3000d burn-in on ES from 2005 leaves no pre-2018 test days.
    python research/ml_jump_model_regime_long_indices.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
from holdout import drop

LAM, REFIT = 50.0, 126
OUT = "marketdata/candidates/ml_jump_model_regime_long_indices"


def feats(r):
    neg = np.minimum(r, 0.0) ** 2
    cols = []
    for hl in (10, 20, 60):
        dd = np.sqrt(neg.ewm(halflife=hl).mean())
        if hl == 10:
            cols.append(dd)
        else:
            cols.append(r.ewm(halflife=hl).mean() / dd.replace(0, np.nan))
    # paper: dd hl10, sortino hl20, sortino hl60
    return pd.concat(cols, axis=1).replace([np.inf, -np.inf], np.nan)


def viterbi(X, mu, lam):
    T = len(X)
    cost = ((X[:, None, :] - mu[None]) ** 2).sum(2)
    V = np.zeros((T, 2))
    B = np.zeros((T, 2), int)
    V[0] = cost[0]
    for t in range(1, T):
        for k in range(2):
            s = V[t - 1] + lam * (np.arange(2) != k)
            B[t, k] = s.argmin()
            V[t, k] = s.min() + cost[t, k]
    st = np.zeros(T, int)
    st[-1] = V[-1].argmin()
    for t in range(T - 1, 0, -1):
        st[t - 1] = B[t, st[t]]
    return st


def fit(X, lam, iters=15):
    best = None
    rng = np.random.RandomState(0)
    for init in range(4):
        idx = rng.choice(len(X), 2, replace=False)
        mu = X[idx].copy()
        for _ in range(iters):
            st = viterbi(X, mu, lam)
            new = np.array([X[st == k].mean(0) if (st == k).any() else mu[k] for k in range(2)])
            if np.allclose(new, mu):
                break
            mu = new
        st = viterbi(X, mu, lam)
        obj = ((X - mu[st]) ** 2).sum() + lam * (np.diff(st) != 0).sum()
        if best is None or obj < best[0]:
            best = (obj, mu, st)
    return best[1], best[2]


def signal(ret, win):
    F = feats(ret)
    ok = F.dropna().index
    F = F.loc[ok]
    r = ret.loc[ok]
    n = len(F)
    sig = pd.Series(np.nan, index=F.index)
    for t0 in range(win, n, REFIT):
        tr = F.values[t0 - win:t0]
        m, s = tr.mean(0), tr.std(0)
        Z = (tr - m) / s
        mu, st = fit(Z, LAM)
        bull = int(np.argmax([r.values[t0 - win:t0][st == k].sum() if (st == k).any() else -9 for k in range(2)]))
        # online state: forward DP from the window start (window grows to win+REFIT); end state = argmin V[t]
        Zf = (F.values[t0 - win:min(t0 + REFIT, n)] - m) / s
        cost = ((Zf[:, None, :] - mu[None]) ** 2).sum(2)
        V = cost[0].copy()
        for i in range(1, len(Zf)):
            V = np.minimum(V, V[::-1] + LAM) + cost[i]
            if i >= win:
                sig.iloc[t0 - win + i] = float(V.argmin() == bull)
    return sig


def sharpe(x):
    x = x.dropna()
    return x.mean() / x.std() * np.sqrt(252) if len(x) > 20 and x.std() > 0 else float("nan")


def strat(ret, sig, cost):
    pos = sig.shift(2).reindex(ret.index)
    pos = pos.dropna()
    rr = ret.loc[pos.index]
    turn = pos.diff().abs().fillna(0)
    return pos * rr - turn * cost - pos * 0.03 / 252


def run(win, tag):
    outs = {}
    for nm in ("ES", "NQ"):
        d = pd.read_csv(f"marketdata/commod/{nm}.csv", parse_dates=["date"]).set_index("date")["close"]
        ret = np.log(d).diff().dropna()
        s = signal(ret, win)
        outs[nm] = (ret, s)
    res = {}
    for c, mult in (("1x", 1.0), ("1.5x", 1.5), ("2x", 2.0)):
        rs = []
        for nm, (ret, s) in outs.items():
            rs.append(strat(ret, s, 1e-4 * mult))
        res[c] = pd.concat(rs, axis=1).dropna().mean(axis=1)
    bh = pd.concat([o[0] for o in outs.values()], axis=1).mean(axis=1)
    for c, r in res.items():
        r = drop(r)
        print(tag, c, "first", r.index[0].date(), "n", len(r), "full", round(sharpe(r), 2),
              "to2017", round(sharpe(r[r.index < "2018-01-01"]), 2), "2018on", round(sharpe(r[r.index >= "2018-01-01"]), 2))
    b = drop(bh).loc[res["1x"].index.intersection(drop(bh).index)]
    print(tag, "buy&hold same days: to2017", round(sharpe(b[b.index < "2018-01-01"]), 2), "2018on", round(sharpe(b[b.index >= "2018-01-01"]), 2))
    for nm, (ret, s) in outs.items():
        p = s.shift(2).dropna()
        print(tag, nm, "share long", round(p.mean(), 2), "switches", int(p.diff().abs().sum()), "years", round(len(p) / 252, 1))
    if tag == sys.argv[1] if len(sys.argv) > 1 else tag == "A":
        for nm, c in (("", "1x"), ("_stress", "1.5x")):
            r = drop(res[c])
            pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(OUT + nm + ".csv", index=False)
        mk = pd.concat([drop(strat(outs[k][0], outs[k][1], 1e-4).dropna()).rename(k) for k in outs], axis=1)
        mk.index.name = "day"
        mk.to_csv(OUT + "_markets.csv")


if __name__ == "__main__":
    run(3000, "A")
    run(1250, "B")
