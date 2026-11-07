"""Deep reinforcement learning for trading futures (Zhang, Zohren, Roberts, "Deep Reinforcement Learning for
Trading", arXiv 1911.10107 / Journal of Financial Data Science 2020, read in full), replicated on the 20 daily
futures in marketdata/commod.

Paper (sections 3-4): state = the last 60 days of 8 features per contract - normalised price, returns over 1, 2, 3
and 12 months scaled by ex-ante volatility (60-day EWM) x sqrt(horizon), three MACD signals (8/24, 16/48, 32/96:
(EWM_S - EWM_L) / 63-day price std, then / its 252-day std) and RSI(30); a two-layer LSTM (64, 32 units, leaky ReLU);
DQN with fixed Q-targets, double and dueling heads, actions {-1, 0, 1}; reward (eq. 4) = position x sigma_tgt /
sigma_{t-1} x return minus bp x the change of the volatility-scaled position, bp = 20 bp in training, gamma 0.3,
Adam 1e-4, batch 64, replay 5,000, target update every 1,000 steps; retrained every 5 years on all data so far,
tested 2011-2019, equal-weight portfolio.  Table 3 (no portfolio vol scaling), all contracts: Long Sharpe -0.04,
Sign(12m return) 0.29, MACD -0.08, DQN 1.26, PG 0.60, A2C 0.97; DQN holds up to 25 bp of cost (Figure 2).

Here: Yahoo continuous front-month closes (not ratio-adjusted: the roll gaps stay in the returns, daily returns
clipped at +-20%), 2005-10 on; the current position is added to the state (the reward depends on it through the
cost, the paper does not say how it handles that); walk-forward folds trained to 2010, 2015, 2020 and tested on the
next 5 years (2021 to 2026-10); three seeds; costs in the test 2 and 10 bp.  Baselines as in section 4.2.

    python research/drl_futures.py [--steps 30000] [--seeds 3]

Result (2026-10-15, 30,000 training steps a fold, three seeds): rejected.  Out of sample 2011-2026 at 2 bp the three
seeds earn Sharpe +0.54, -0.06, -0.17 (2011-15 +0.61 / -0.34 / -0.88) - the seed decides, not the model; at 10 bp
+0.01, -0.48, -0.65 (paper 1.26 and robust to 25 bp).  Benchmarks at 2 bp: long +0.55, Sgn(12m) +0.37, MACD -0.11.
Correlation with the Hydra legs 0.00-0.05.  PG and A2C, which the paper ranks below the DQN, were not run.  With
the Deep Momentum Network (research/deep_momentum.py) and the EUR/USD agent (research/dl_rl_replication.py) this
makes three deep-learning / RL replications that do not beat simple rules out of sample on this data.
"""
import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / "marketdata"
WIN, NF = 60, 9
TGT = 0.15 / np.sqrt(252)


def load():
    P = pd.DataFrame({f.stem: pd.read_csv(f, index_col=0, parse_dates=True).close
                      for f in sorted((ROOT / "commod").glob("*.csv"))}).sort_index()
    P = P[P.index.dayofweek < 5].ffill(limit=3)
    return P["2005":]


def features(p):
    """Per contract: (T x NF) feature matrix, daily return, ex-ante daily volatility."""
    r = p.pct_change().clip(-0.2, 0.2)
    sig = r.ewm(span=60, min_periods=30).std()
    f = pd.DataFrame(index=p.index)
    f["px"] = (p - p.rolling(WIN).mean()) / p.rolling(WIN).std()
    for h in (21, 42, 63, 252):
        f[f"r{h}"] = (p / p.shift(h) - 1) / (sig * np.sqrt(h))
    for s, l in ((8, 24), (16, 48), (32, 96)):
        q = (p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / s)).mean() - p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / l)).mean())
        q = q / p.rolling(63).std()
        f[f"macd{s}"] = q / q.rolling(252).std()
    d = p.diff()
    up, dn = d.clip(lower=0).rolling(30).mean(), (-d.clip(upper=0)).rolling(30).mean()
    f["rsi"] = (100 - 100 / (1 + up / dn)) / 100 - 0.5
    return f.clip(-5, 5), r, sig


def baselines(p, r, sig):
    sign = np.sign(p / p.shift(252) - 1)
    m = 0.0
    for s, l in ((8, 24), (16, 48), (32, 96)):
        q = (p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / s)).mean() - p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / l)).mean())
        q = q / p.rolling(63).std()
        y = q / q.rolling(252).std()
        m = m + y * np.exp(-y ** 2 / 4) / 0.89
    return {"long": pd.Series(1.0, index=p.index), "sign": sign, "macd": m / 3}


def pnl(pos, r, sig, cost):
    """Next-day volatility-scaled return of position `pos` decided at each close, net of cost (fraction)."""
    w = (pos * TGT / sig).clip(-5, 5)
    return (w.shift(1) * r - cost * w.diff().abs().shift(1)).fillna(0)


def build_net(torch):
    nn = torch.nn

    class QNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.l1 = nn.LSTM(NF, 64, batch_first=True)
            self.l2 = nn.LSTM(64, 32, batch_first=True)
            self.act = nn.LeakyReLU()
            self.v = nn.Linear(32 + 1, 1)
            self.a = nn.Linear(32 + 1, 3)

        def forward(self, x, prev):
            h, _ = self.l1(x)
            h, _ = self.l2(self.act(h))
            z = torch.cat([self.act(h[:, -1]), prev.unsqueeze(1)], 1)
            a = self.a(z)
            return self.v(z) + a - a.mean(1, keepdim=True)          # dueling head

    return QNet


def train(data, t0, t1, steps, seed, torch):
    """DQN on the days in [t0, t1) of every contract.  data: list of (feat array, ret array, sig array, dates)."""
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    QNet = build_net(torch)
    q, tgt = QNet(), QNet()
    tgt.load_state_dict(q.state_dict())
    opt = torch.optim.Adam(q.parameters(), lr=1e-4)
    mem, cap = [], 5000
    acts = np.array([-1.0, 0.0, 1.0])
    pools = []
    for k, (F, R, S, D) in enumerate(data):
        idx = np.flatnonzero((D >= t0) & (D < t1))
        idx = idx[(idx >= WIN + 252) & (idx < len(D) - 1)]
        if len(idx) > 300:
            pools.append((k, idx))
    eps, step = 1.0, 0
    while step < steps:
        k, idx = random.choice(pools)
        F, R, S, D = data[k]
        start = random.randint(0, len(idx) - 253)
        prev = 0.0
        for i in idx[start:start + 252]:
            s = torch.tensor(F[i - WIN + 1:i + 1][None], dtype=torch.float32)
            if random.random() < eps:
                a = random.randrange(3)
            else:
                with torch.no_grad():
                    a = int(q(s, torch.tensor([prev], dtype=torch.float32)).argmax())
            w_prev, w = prev * TGT / S[i - 1], acts[a] * TGT / S[i]
            rew = w * R[i + 1] - 0.0020 * abs(w - w_prev)
            mem.append((i, k, prev, a, rew * 100))
            if len(mem) > cap:
                mem.pop(0)
            prev = acts[a]
            step += 1
            eps = max(0.05, 1.0 - step / (0.5 * steps))
            if len(mem) >= 640:
                b = random.sample(mem, 64)
                X = torch.tensor(np.stack([data[kk][0][ii - WIN + 1:ii + 1] for ii, kk, _, _, _ in b]), dtype=torch.float32)
                X2 = torch.tensor(np.stack([data[kk][0][ii - WIN + 2:ii + 2] for ii, kk, _, _, _ in b]), dtype=torch.float32)
                pv = torch.tensor([x[2] for x in b], dtype=torch.float32)
                av = torch.tensor([x[3] for x in b])
                rv = torch.tensor([x[4] for x in b], dtype=torch.float32)
                nv = torch.tensor(acts[[x[3] for x in b]], dtype=torch.float32)
                with torch.no_grad():
                    best = q(X2, nv).argmax(1)                                   # double DQN
                    y = rv + 0.3 * tgt(X2, nv).gather(1, best[:, None]).squeeze(1)
                qa = q(X, pv).gather(1, av[:, None]).squeeze(1)
                loss = torch.nn.functional.smooth_l1_loss(qa, y)
                opt.zero_grad()
                loss.backward()
                opt.step()
            if step % 1000 == 0:
                tgt.load_state_dict(q.state_dict())
            if step >= steps:
                break
    return q


def act(q, F, idx, torch):
    """Greedy positions on the days idx, run in order (the position feeds the next state)."""
    acts = np.array([-1.0, 0.0, 1.0])
    out, prev = [], 0.0
    with torch.no_grad():
        for i in idx:
            s = torch.tensor(F[i - WIN + 1:i + 1][None], dtype=torch.float32)
            prev = acts[int(q(s, torch.tensor([prev], dtype=torch.float32)).argmax())]
            out.append(prev)
    return np.array(out)


def sharpe(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0.0


if __name__ == "__main__":
    import torch
    torch.set_num_threads(4)
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    P = load()
    data, rets, sigs, base = [], {}, {}, {}
    for c in P:
        p = P[c].dropna()
        f, r, s = features(p)
        f = f.fillna(0)
        data.append((f.to_numpy(np.float32), r.fillna(0).to_numpy(), s.bfill().to_numpy(), p.index.to_numpy()))
        rets[c], sigs[c], base[c] = r, s, baselines(p, r, s)
    folds = (("2005", "2011", "2016"), ("2005", "2016", "2021"), ("2005", "2021", "2027"))
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    results = {f"dqn{sd}": {} for sd in range(a.seeds)}
    for t0, t1, t2 in folds:
        for sd in range(a.seeds):
            q = train(data, np.datetime64(t0), np.datetime64(t1), a.steps, sd, torch)
            for k, c in enumerate(P):
                F, R, S, D = data[k]
                idx = np.flatnonzero((D >= np.datetime64(t1)) & (D < np.datetime64(t2)))
                idx = idx[idx >= WIN + 252]
                if len(idx) == 0:
                    continue
                pos = pd.Series(act(q, F, idx, torch), index=pd.DatetimeIndex(D[idx]))
                results[f"dqn{sd}"].setdefault(c, []).append(pos)
            print(f"fold {t1}-{t2} seed {sd} trained", flush=True)
    for cost in (0.0002, 0.0010):
        lines = {}
        for name in ("long", "sign", "macd"):
            lines[name] = pd.concat([pnl(base[c][name], rets[c], sigs[c], cost) for c in P], axis=1, sort=True).mean(axis=1)["2011":]
        for sd in range(a.seeds):
            cols = []
            for c, parts in results[f"dqn{sd}"].items():
                pos = pd.concat(parts).sort_index()
                cols.append(pnl(pos.reindex(rets[c].index), rets[c], sigs[c], cost))
            lines[f"dqn seed {sd}"] = pd.concat(cols, axis=1, sort=True).mean(axis=1)["2011":]
        print(f"cost {cost * 1e4:.0f} bp")
        for name, x in lines.items():
            corr = pd.concat([x, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
            print(f"  {name:12s} Sharpe 2011-26 {sharpe(x):+.2f}  (2011-15 {sharpe(x[:'2015']):+.2f}, 2016-20 "
                  f"{sharpe(x['2016':'2020']):+.2f}, 2021-26 {sharpe(x['2021':]):+.2f})  corr Hydra {corr:+.2f}")
