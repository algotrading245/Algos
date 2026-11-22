"""PPO sets per-leg weight multipliers (0..1.5, max change 0.25/day) over the book's legs.
Train 2012-2019, validate 2020-21 (pick nothing: report), test 2022 to 2025-10-10 (holdout dropped by B.clip).
Reward: daily return - 2*downside dev (daily min(r,0)^2 sqrt proxy) - 0.5*drawdown increment. 5 seeds.
Controls: equal risk (m=1), book vol-target multiplier (20d vol), random smoothed policy."""
import sys
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
sys.path.insert(0, "tools")
import book_sim as B

OUT = "marketdata/candidates/"


def build():
    L = B.legs()
    W = B.weights(L)
    P = (W * L.fillna(0.0))  # weighted pnl per leg
    P = P[W.sum(axis=1) > 0]
    P = P.loc[:, (P != 0).any()]
    sd = P.std().replace(0, 1)
    P = P / sd * sd.mean()  # keep as is in scale of book; features use z-scores
    return P


def features(P):
    s5 = P.rolling(5).sum()
    s20 = P.rolling(20).sum()
    z5 = s5 / (P.rolling(60).std() * np.sqrt(5))
    z20 = s20 / (P.rolling(120).std() * np.sqrt(20))
    b = P.sum(axis=1)
    v20 = b.rolling(20).std()
    vl = v20 / v20.expanding(60).mean()
    eq = (1 + b * 0.0 + b).cumprod()
    dd = 1 - eq / eq.cummax()
    mtd = b.groupby(b.index.to_period("M")).cumsum()
    F = pd.concat([z5.clip(-4, 4), z20.clip(-4, 4), vl.rename("vol").to_frame(), dd.rename("dd").to_frame() * 10,
                   (mtd * 10).rename("mtd").to_frame()], axis=1)
    F.columns = [f"f{i}" for i in range(F.shape[1])]
    return F.shift(1)  # past only (state at the close of the day before)


class Env(gym.Env):
    def __init__(self, P, F, train=True, ep=250, seed=0):
        self.P = P.to_numpy(); self.F = F.to_numpy().astype(np.float32); self.n, self.k = self.P.shape
        self.train = train; self.ep = ep; self.rng = np.random.default_rng(seed)
        self.observation_space = spaces.Box(-10, 10, (self.F.shape[1] + self.k,), np.float32)
        self.action_space = spaces.Box(0.0, 1.5, (self.k,), np.float32)

    def _obs(self):
        o = np.concatenate([np.nan_to_num(self.F[self.t]), self.m]).astype(np.float32)
        return np.clip(o, -10, 10)

    def reset(self, seed=None, options=None):
        self.t0 = int(self.rng.integers(0, max(1, self.n - self.ep))) if self.train else 0
        self.t = self.t0; self.end = min(self.n, self.t0 + self.ep) if self.train else self.n
        self.m = np.ones(self.k); self.eq = 1.0; self.peak = 1.0
        return self._obs(), {}

    def step(self, a):
        tgt = np.clip(a, 0, 1.5)
        self.m = self.m + np.clip(tgt - self.m, -0.25, 0.25)
        r = float((self.P[self.t] * self.m).sum())
        dd0 = 1 - self.eq / self.peak
        self.eq *= 1 + r; self.peak = max(self.peak, self.eq)
        dd1 = 1 - self.eq / self.peak
        rew = r - 2 * abs(min(r, 0)) - 0.5 * max(dd1 - dd0, 0)
        self.t += 1
        done = self.t >= self.end
        return (self._obs() if not done else np.zeros(self.observation_space.shape, np.float32)), rew * 100, done, False, {}


def roll(pol, P, F):
    env = Env(P, F, train=False)
    o, _ = env.reset(); M = []
    done = False
    while not done:
        a = pol(o)
        M.append(np.clip(a, 0, 1.5))
        o, _, done, _, _ = env.step(a)
        M[-1] = env.m.copy()
    return pd.DataFrame(M, index=P.index[:len(M)], columns=P.columns)


def score(P, M, tag):
    b = (P * M).sum(axis=1)
    x = B.risk_layer(b)
    t = x[x.index >= pd.Timestamp("2022-01-01")]
    mo = B.months(t)
    return B.sharpe(b[b.index >= "2022-01-01"]), B.sharpe(t), (mo < 0).sum(), len(mo), mo.min()


def main():
    P = build(); F = features(P)
    ok = F.dropna().index
    P = P.loc[ok]; F = F.loc[ok]
    tr = P.index < "2020-01-01"; va = (P.index >= "2020-01-01") & (P.index < "2022-01-01"); te = P.index >= "2022-01-01"
    print("legs", P.shape[1], "days", len(P), "train/val/test", tr.sum(), va.sum(), te.sum())
    base = pd.DataFrame(1.0, index=P.index, columns=P.columns)
    print("equal risk  raw/risklayer test Sharpe, losing months, worst: %.3f %.3f %d/%d %.4f" % score(P[te], base[te], "eq"))
    b = P.sum(axis=1); v = b.rolling(20).std().shift(1); vt = (v.expanding(60).median() / v).clip(0, 1.5).fillna(1.0)
    Mv = base.mul(vt, axis=0)
    print("vol-target  : %.3f %.3f %d/%d %.4f" % score(P[te], Mv[te], "vt"))
    res = []; keep = None
    for seed in range(5):
        env = Env(P[tr], F[tr], seed=seed)
        model = PPO("MlpPolicy", env, seed=seed, verbose=0, policy_kwargs=dict(net_arch=[32, 32]), n_steps=1000, batch_size=250, learning_rate=1e-4)
        model.learn(total_timesteps=60000)
        pol = lambda o: model.predict(o, deterministic=True)[0]
        Mv_ = roll(pol, P[va], F[va]); sv = score(P[va], Mv_, "va")
        Mt = roll(pol, P[te], F[te]); st = score(P[te], Mt, "te")
        bv = score(P[va], base[va], "x")
        print("seed %d val rl %.3f/%.3f (eq %.3f/%.3f) test rl raw %.3f rl+layer %.3f losing %d/%d worst %.4f mean m %.2f" % (
            seed, sv[0], sv[1], bv[0], bv[1], st[0], st[1], st[2], st[3], st[4], Mt.values.mean()))
        res.append(st[1])
        if keep is None:
            keep = (Mt, seed)
    print("test book Sharpe (with risk layer) across seeds:", np.round(res, 3), "min %.3f max %.3f" % (min(res), max(res)))
    # candidate series: seed 0 book return, test period
    Mt, _ = keep
    r = (P[te] * Mt).sum(axis=1)
    r.rename("r").rename_axis("day").to_csv(OUT + "drl_leg_sizing_ppo.csv")
    (r - 0.00005).rename("r").rename_axis("day").to_csv(OUT + "drl_leg_sizing_ppo_stress.csv")


if __name__ == "__main__":
    main()
