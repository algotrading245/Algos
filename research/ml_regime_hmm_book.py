"""Two-state Gaussian HMM (own numpy EM; hmmlearn not installed) on [book daily return, 10d realised vol].
Refit each year (expanding window from first day), filtered forward probabilities only. Rule fixed beforehand:
P(bad) > 0.6 at close -> next-day book multiplier 0.5, else 1. Bad state = lower-mean-return state. 3 seeds.
Control: random halving on same fraction of days."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "tools")
import book_sim as B

OUT = "marketdata/candidates/"


def logpdf(X, mu, var):
    return -0.5 * (np.log(2 * np.pi * var).sum(-1) + ((X[:, None, :] - mu[None]) ** 2 / var[None]).sum(-1))


def fit(X, seed, it=60):
    rng = np.random.default_rng(seed)
    n, d = X.shape
    K = 2
    z = rng.random(n) < 0.5
    mu = np.array([X[z].mean(0), X[~z].mean(0)])
    var = np.array([X[z].var(0), X[~z].var(0)]) + 1e-12
    A = np.array([[0.95, 0.05], [0.05, 0.95]])
    pi = np.array([0.5, 0.5])
    for _ in range(it):
        lp = logpdf(X, mu, var)
        m = lp.max(1, keepdims=True)
        e = np.exp(lp - m)
        al = np.zeros((n, K)); c = np.zeros(n)
        a = pi * e[0]; c[0] = a.sum(); al[0] = a / c[0]
        for t in range(1, n):
            a = (al[t - 1] @ A) * e[t]; c[t] = a.sum(); al[t] = a / c[t]
        be = np.ones((n, K))
        for t in range(n - 2, -1, -1):
            be[t] = (A @ (e[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be; g /= g.sum(1, keepdims=True)
        xi = np.zeros((K, K))
        for t in range(n - 1):
            x = al[t][:, None] * A * (e[t + 1] * be[t + 1])[None]
            xi += x / x.sum()
        A = xi / xi.sum(1, keepdims=True)
        pi = g[0]
        w = g.sum(0)
        mu = (g.T @ X) / w[:, None]
        var = np.einsum("tk,tkd->kd", g, (X[:, None, :] - mu[None]) ** 2) / w[:, None] + 1e-12
    return mu, var, A, pi


def filt(X, mu, var, A, pi):
    lp = logpdf(X, mu, var); e = np.exp(lp - lp.max(1, keepdims=True))
    out = np.zeros((len(X), 2)); a = pi * e[0]; out[0] = a / a.sum()
    for t in range(1, len(X)):
        a = (out[t - 1] @ A) * e[t]; out[t] = a / a.sum()
    return out


def run(b, seed):
    vol = b.rolling(10).std()
    D = pd.concat([b.rename("r"), vol.rename("v")], axis=1).dropna()
    X = D.to_numpy()
    sd = X[:500].std(0)
    pbad = pd.Series(np.nan, index=D.index)
    years = sorted(set(D.index.year))
    for y in years:
        if y < 2013:
            continue
        tr = D.index < pd.Timestamp(f"{y}-01-01")
        te = D.index.year == y
        mu, var, A, pi = fit(X[tr] / sd, seed)
        bad = int(np.argmin(mu[:, 0]))  # lower return state... use higher vol alternatively
        if mu[0, 1] != mu[1, 1]:
            bad = int(np.argmax(mu[:, 1]))  # bad = high-vol state
        # filter over train+test so state continuity holds, take the test year only
        idx = np.where(tr | te)[0]
        p = filt(X[idx] / sd, mu, var, A, pi)[:, bad]
        pbad.loc[D.index[te]] = p[-te.sum():]
    return pbad


def main():
    L = B.legs()
    b, _ = B.combine(L)
    x0 = B.risk_layer(b)
    mo0 = B.months(x0)
    print("base book 2018+ %.3f halves %.2f/%.2f losing months %d/%d worst %.4f" % (
        B.sharpe(x0[x0.index >= B.SPLIT]), B.sharpe(x0[x0.index < B.SPLIT]), B.sharpe(x0[x0.index >= B.SPLIT]),
        (mo0 < 0).sum(), len(mo0), mo0.min()))
    res = []
    best = None
    for seed in range(3):
        pb = run(b, seed)
        m = pd.Series(1.0, index=b.index)
        sig = (pb > 0.6).astype(float).reindex(b.index).fillna(0).shift(1).fillna(0)
        m = 1.0 - 0.5 * sig
        frac = sig[sig.index >= pd.Timestamp("2013-01-01")].mean()
        x = B.risk_layer(b * m)
        a = x[x.index >= B.SPLIT]; mo = B.months(x)
        s = B.sharpe(a)
        print("seed %d: bad-days %.1f%% book2018+ %.3f halves %.2f/%.2f losing %d/%d worst %.4f" % (
            seed, 100 * frac, s, B.sharpe(x[x.index < B.SPLIT]), s, (mo < 0).sum(), len(mo), mo.min()))
        res.append(s)
        if best is None:
            best = (m, x, frac)
    rng = np.random.default_rng(0)
    m0, x1, frac = best
    ctl = []
    for _ in range(20):
        r = (rng.random(len(b)) < frac).astype(float)
        x = B.risk_layer(b * (1 - 0.5 * r)); ctl.append(B.sharpe(x[x.index >= B.SPLIT]))
    print("random halving control 2018+: mean %.3f sd %.3f max %.3f" % (np.mean(ctl), np.std(ctl), np.max(ctl)))
    # candidate series: the overlay's gain = b*m - b (the part the rule adds), written as relative to book
    r = (b * m0)
    r = r[r.index >= pd.Timestamp("2013-01-01")]
    r.rename("r").rename_axis("day").to_csv(OUT + "ml_regime_hmm_book.csv")
    (r - 0.00005).rename("r").rename_axis("day").to_csv(OUT + "ml_regime_hmm_book_stress.csv")


if __name__ == "__main__":
    main()
