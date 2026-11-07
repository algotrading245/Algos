"""Thompson-sampling bandit over leg multipliers (0.5/1/1.5), monthly, walk-forward. Book sim 2018+ vs equal weight
and a random-arm control. Past-only: the arm for month m uses rewards of months < m."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import book_sim as B  # noqa: E402

ARMS = np.array([0.5, 1.0, 1.5])
DECAY, SEEDS, START = 0.97, 5, "2012-01"
SPLIT = "2018-01-01"

L = B.legs()
W = B.weights(L)
Lf = L.fillna(0.0)
mper = L.index.to_period("M")
mret = (1 + Lf).groupby(mper).prod() - 1
months = list(mret.index)


def mults(seed, random=False):
    rng = np.random.default_rng(seed)
    out = pd.DataFrame(1.0, index=months, columns=L.columns)
    for k in L.columns:
        prec = np.ones(3)      # prior N(0,1): precision 1, mean 0
        num = np.zeros(3)
        hist = []
        for i, m in enumerate(months):
            if m >= pd.Period(START, "M") and L[k].first_valid_index() is not None:
                if random:
                    a = rng.integers(3)
                else:
                    a = int(np.argmax(rng.normal(num / prec, 1 / np.sqrt(prec))))
                out.loc[m, k] = ARMS[a]
            # observe month m (all arms' rewards: full information, reward = std. return * mult)
            r = mret.loc[m, k]
            if L[k].first_valid_index() is not None and m >= L[k].first_valid_index().to_period("M"):
                sd = np.std(hist[-36:]) if len(hist) >= 6 else None
                hist.append(r)
                if sd and sd > 0:
                    z = r / sd
                    prec *= DECAY
                    num *= DECAY
                    prec += 1.0
                    num += ARMS * z
    return out


def book(mu):
    mm = mu.reindex(mper).set_axis(L.index)
    b = (W * mm * Lf).sum(axis=1)
    live = W.sum(axis=1) > 0
    return b[live]


base = B.risk_layer(B.combine(L)[0])
print("equal weight  2018+ %.3f  to2017 %.3f" % (B.sharpe(base[base.index >= SPLIT]), B.sharpe(base[base.index < SPLIT])))
for name, rnd in (("bandit", False), ("random", True)):
    res = []
    for s in range(SEEDS):
        b = B.risk_layer(book(mults(s, rnd)))
        res.append((B.sharpe(b[b.index >= SPLIT]), B.sharpe(b[(b.index < SPLIT) & (b.index >= "2012-01-01")])))
    a = np.array(res)
    print(name, "2018+ per seed", np.round(a[:, 0], 3), "mean %.3f" % a[:, 0].mean(), "| 2012-17 mean %.3f" % a[:, 1].mean())
b0 = base[(base.index >= "2012-01-01") & (base.index < SPLIT)]
print("equal weight 2012-17 %.3f" % B.sharpe(b0))
