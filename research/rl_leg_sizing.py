"""RL position sizing (PPO) on the Hydra leg mix. Daily action = size per leg in [0,2] (action 0..1 times 2, so a fixed
size of 1 is action 0.5), state = past-only: last 5 daily returns of each leg, 20d drawdown of the book, 20d and 60d
vol of the book, leg 20d means. Reward = net book return (x100) minus a drawdown penalty, minus a turnover cost on
size changes (1 bp per unit of |size change| per leg). Walk-forward by year (train = all earlier days, 1-day purge),
test years 2014 on, judged 2018 on, holdout dropped. 3 seeds, 1 config, 3 x folds trials counted.
Baselines: fixed size 1, vol-targeted size (60d vol of the book), and the "always on" book.

    python research/rl_leg_sizing.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

SPLIT = pd.Timestamp("2018-01-01")
TURN = 1e-4        # cost per unit of size change per leg
DD_PEN = 2.0
SEEDS = (0, 1, 2)
STEPS = 30000


def sharpe(x):
    x = np.asarray(x)
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


def maxdd(x):
    c = np.cumsum(x)
    return float((c - np.maximum.accumulate(c)).min())


def state_frame(L):
    book = L.sum(axis=1)
    cols = []
    for k in range(1, 6):
        cols.append((L.shift(k) * 100).add_suffix(f"_l{k}"))
    eq = book.cumsum()
    dd = (eq - eq.rolling(20).max()).shift(1) * 100
    v20 = book.rolling(20).std().shift(1) * 100
    v60 = book.rolling(60).std().shift(1) * 100
    m20 = (L.rolling(20).mean().shift(1) * 1000).add_suffix("_m20")
    S = pd.concat(cols + [m20, dd.rename("dd"), v20.rename("v20"), v60.rename("v60")], axis=1)
    return S


class Env(gym.Env):
    def __init__(self, L, S, ep=250, rng=0):
        self.L, self.S = L.values, S.values.astype(np.float32)
        self.n, self.k = len(L), L.shape[1]
        self.ep = ep
        self.rng = np.random.default_rng(rng)
        self.action_space = spaces.Box(0.0, 1.0, (self.k,), np.float32)
        self.observation_space = spaces.Box(-50, 50, (S.shape[1],), np.float32)

    def reset(self, seed=None, options=None):
        self.t = int(self.rng.integers(0, max(1, self.n - self.ep)))
        self.end = min(self.n, self.t + self.ep)
        self.prev = np.full(self.k, 1.0)
        self.eq = 0.0
        self.peak = 0.0
        return np.clip(self.S[self.t], -50, 50), {}

    def step(self, a):
        size = 2 * np.asarray(a, dtype=float)
        r = float((size * self.L[self.t]).sum() - TURN * np.abs(size - self.prev).sum())
        self.prev = size
        self.eq += r
        d0 = self.peak - self.eq
        self.peak = max(self.peak, self.eq)
        d1 = self.peak - self.eq
        rew = 100 * r - DD_PEN * 100 * max(0.0, d1 - d0)
        self.t += 1
        done = self.t >= self.end
        obs = np.clip(self.S[min(self.t, self.n - 1)], -50, 50)
        return obs, rew, done, False, {}


def main():
    L = pd.read_csv(ROOT / "marketdata" / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True)
    L = holdout.drop(L).drop(columns=["quartet"], errors="ignore")
    S = state_frame(L)
    ok = S.notna().all(axis=1)
    L, S = L[ok], S[ok]
    idx = L.index
    years = list(range(2014, idx.year.max() + 1))
    sizes = {s: pd.DataFrame(1.0, index=idx, columns=L.columns) for s in SEEDS}
    trials = 0
    for y in years:
        tr = idx < pd.Timestamp(f"{y}-01-01") - pd.Timedelta(days=2)
        te = idx.year == y
        for s in SEEDS:
            trials += 1
            env = Env(L[tr], S[tr], rng=s)
            m = PPO("MlpPolicy", env, seed=s, verbose=0, n_steps=1000, batch_size=250, learning_rate=3e-4,
                    policy_kwargs=dict(net_arch=[32, 32]))
            m.learn(STEPS)
            a, _ = m.predict(S[te].values.astype(np.float32).clip(-50, 50), deterministic=True)
            sizes[s].loc[te, :] = 2 * a
        print("fold", y, flush=True)

    start = pd.Timestamp("2014-01-01")
    sel = idx >= start
    Lw = L[sel]
    book = Lw.sum(axis=1)
    vt = (0.5 * book.std() / book.rolling(60).std().shift(1)).clip(0, 3).fillna(1.0)   # same average vol as fixed
    vol_t = book * vt

    def stream(sz):
        sz = sz[sel]
        turn = sz.diff().abs().sum(axis=1).fillna(0) * TURN
        return (sz * Lw).sum(axis=1) - turn, sz

    res = {}
    for s in SEEDS:
        res[s], _ = stream(sizes[s])
    avg = sum(sizes[s] for s in SEEDS) / len(SEEDS)
    ens, szavg = stream(avg)
    print("variant        period   Sharpe  maxDD   mean size")
    for name, x in [("fixed 1", book), ("vol-target", vol_t), ("RL ensemble", ens)] + [(f"RL seed{s}", res[s]) for s in SEEDS]:
        for lbl, m in (("2014-17", x.index < SPLIT), ("2018+", x.index >= SPLIT)):
            ms = szavg[m].mean().mean() if name == "RL ensemble" else (sizes[int(name[-1])][sel][m].mean().mean() if name.startswith("RL seed") else 1.0)
            print(f"{name:13s} {lbl:8s} {sharpe(x[m]):6.2f} {maxdd(x[m].values):7.3f} {ms:6.2f}")
    late = ens.index >= SPLIT
    print("worst seed 2018+ Sharpe", min(sharpe(res[s][late]) for s in SEEDS))
    print("mean size by leg 2018+", szavg[late].mean().round(2).to_dict())
    print("trials", trials)
    out = ROOT / "marketdata" / "candidates"
    ens.rename("r").rename_axis("day").to_csv(out / "rl_leg_sizing.csv")
    # stress: the leg costs are inside the leg returns and not separable, so charge 3x the turnover cost and 0.5 bp
    # extra per unit of size per day on legs that traded (non-zero return day)
    traded = (Lw != 0).astype(float)
    extra = 0.5e-4 * (szavg[sel.nonzero()[0].size and slice(None)] * traded).sum(axis=1) if False else 0.5e-4 * (szavg * traded).sum(axis=1)
    stress = ens - 2 * szavg.diff().abs().sum(axis=1).fillna(0) * TURN - extra
    stress.rename("r").rename_axis("day").to_csv(out / "rl_leg_sizing_stress.csv")
    print("fixed-1 stream stress-equivalent Sharpe 2018+", sharpe((book - 0.5e-4 * traded.sum(axis=1))[late]))
    print("RL stress Sharpe 2018+", sharpe(stress[late]))


if __name__ == "__main__":
    main()
