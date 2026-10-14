"""Check of Aweda, Woods & Ojo (2025), "Development of Hybrid Deep Learning and Reinforcement Learning for
Intelligent Trading in Forex Markets" (doi 10.9734/jamcs/2025/v40i72028) on daily EUR/USD from histdata.com.

The paper: daily EUR/USD 2014-2024, five indicators (RSI, MACD, ROC, EMA, stochastic), min-max scaling, EMA
smoothing of the price, a CNN-LSTM that forecasts the close (RMSE 0.0025) and a deep Q-learning agent on top
(Sharpe 2.87, +49.2%, against +24.5% for buy-and-hold).

Three parts:
  1  the paper's benchmarks against the data: buy-and-hold, and the error of "tomorrow = today"
  2  what forecasting an EMA-smoothed close does to the error
  3  the model itself without leaks: CNN-LSTM forecast of the next day's return, then a deep Q-learning agent
     (replay memory, target network, decaying epsilon) that picks short / flat / long from the same window plus
     the forecast. Train 2014-2020, validation 2021-2022, test 2023-2024, several seeds, cost per position change.

Usage: python research/dl_rl_replication.py [--seeds 5] [--cost 0.85] [--window 30]
"""
import argparse
import os
import random

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "marketdata", "histdata")
TRAIN_TO, VAL_TO, FIRST, LAST = "2021-01-01", "2023-01-01", "2014-01-01", "2025-01-01"


def daily(pair="EURUSD"):
    """Daily bars; a day runs from 17:00 to 17:00 New York, the file's clock is that plus 7 hours."""
    m = pd.read_csv(os.path.join(ROOT, f"{pair}_M1.csv.gz"))
    t = pd.to_datetime(m.time, unit="s")
    m = m[t.dt.dayofweek < 5]
    d = m.groupby(t[t.dt.dayofweek < 5].dt.normalize()).agg(open=("open", "first"), high=("high", "max"),
                                                              low=("low", "min"), close=("close", "last"))
    return d


def features(d):
    """The paper's five indicators in a stationary form, plus the day's return and range."""
    c = d.close
    r = np.log(c).diff()
    up, dn = r.clip(lower=0).ewm(alpha=1 / 14).mean(), (-r.clip(upper=0)).ewm(alpha=1 / 14).mean()
    macd = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    lo, hi = d.low.rolling(14).min(), d.high.rolling(14).max()
    f = pd.DataFrame({"ret": r, "range": np.log(d.high / d.low), "rsi": up / (up + dn) - 0.5,
                      "macd": (macd - macd.ewm(span=9).mean()) / c, "roc": c / c.shift(10) - 1,
                      "ema": c / c.ewm(span=20).mean() - 1, "stoch": (c - lo) / (hi - lo) - 0.5})
    return f, r.shift(-1).rename("next")


class Net(nn.Module):
    """Conv1d over the window, LSTM over the result, 'out' numbers from the last step."""

    def __init__(self, n, out, extra=0):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(n, 16, 3, padding=1), nn.ReLU())
        self.lstm = nn.LSTM(16, 16, batch_first=True)
        self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(16 + extra, out))

    def forward(self, x, e=None):
        h = self.lstm(self.conv(x.transpose(1, 2)).transpose(1, 2))[0][:, -1]
        return self.head(h if e is None else torch.cat([h, e], 1))


def forecast(X, y, tr, va, seed):
    """Fits the forecaster with early stopping on the validation years; returns the forecast for every day."""
    torch.manual_seed(seed)
    net = Net(X.shape[2], 1)
    opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
    best, state, wait = np.inf, None, 0
    for _ in range(200):
        net.train()
        for b in torch.randperm(len(tr)).split(64):
            opt.zero_grad()
            nn.functional.mse_loss(net(X[tr[b]]).squeeze(1), y[tr[b]]).backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            v = nn.functional.mse_loss(net(X[va]).squeeze(1), y[va]).item()
        if v < best - 1e-6:
            best, state, wait = v, {k: w.clone() for k, w in net.state_dict().items()}, 0
        else:
            wait += 1
            if wait >= 15:
                break
    net.load_state_dict(state)
    net.eval()
    with torch.no_grad():
        return net(X).squeeze(1)


def agent(X, pred, ret, tr, va, cost, seed, episodes=40):
    """Deep Q-learning over actions short / flat / long. State: the window, the forecast and the position held.
    Reward: position times the next day's return, less the cost of the change. Returns the position per day."""
    torch.manual_seed(seed)
    random.seed(seed)
    q, target = Net(X.shape[2], 3, 2), Net(X.shape[2], 3, 2)
    target.load_state_dict(q.state_dict())
    opt = torch.optim.Adam(q.parameters(), 5e-4)
    memory, eps, gamma, steps = [], 1.0, 0.9, 0
    extra = lambda i, pos: torch.stack([pred[i], torch.full_like(pred[i], 0.0) + pos], -1)

    def play(idx, greedy):
        q.eval()
        pos, out = 0.0, []
        with torch.no_grad():
            for i in idx:
                a = int(q(X[i:i + 1], extra(torch.tensor([i]), pos)).argmax()) - 1 if greedy else None
                out.append(a)
                pos = float(a)
        return np.array(out, dtype=float)

    def value(idx, p):
        r = p * ret[idx].numpy() - cost * np.abs(np.diff(np.r_[0.0, p]))
        return r.mean() / (r.std() + 1e-12)

    best, state = -np.inf, None
    for _ in range(episodes):
        pos = 0.0
        q.train()
        for n, i in enumerate(tr[:-1].tolist()):
            if random.random() < eps:
                a = random.randrange(3)
            else:
                with torch.no_grad():
                    a = int(q(X[i:i + 1], extra(torch.tensor([i]), pos)).argmax())
            reward = (a - 1) * float(ret[i]) - cost * abs(a - 1 - pos)
            memory.append((i, pos, a, 100.0 * reward, float(a - 1)))
            memory = memory[-5000:]
            pos = float(a - 1)
            if len(memory) >= 256 and n % 4 == 0:
                b = random.sample(memory, 64)
                i0 = torch.tensor([m[0] for m in b])
                p0 = torch.tensor([m[1] for m in b])
                act = torch.tensor([m[2] for m in b])
                rew = torch.tensor([m[3] for m in b], dtype=torch.float32)
                p1 = torch.tensor([m[4] for m in b])
                with torch.no_grad():
                    nxt = target(X[i0 + 1], torch.stack([pred[i0 + 1], p1], -1).float()).max(1)[0]
                now = q(X[i0], torch.stack([pred[i0], p0], -1).float()).gather(1, act[:, None]).squeeze(1)
                opt.zero_grad()
                nn.functional.smooth_l1_loss(now, rew + gamma * nxt).backward()
                opt.step()
                steps += 1
                if steps % 100 == 0:
                    target.load_state_dict(q.state_dict())
        eps = max(0.1, eps * 0.9)
        v = value(va, play(va.tolist(), True))        # the policy kept is the one best on the validation years
        if v > best:
            best, state = v, {k: w.clone() for k, w in q.state_dict().items()}
    q.load_state_dict(state)
    return play


def stats(r):
    eq = np.cumprod(1 + r)
    return r.mean() / (r.std() + 1e-12) * np.sqrt(252), 100 * (eq[-1] - 1), 100 * (1 - eq / np.maximum.accumulate(eq)).max()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--cost", type=float, default=0.85, help="cost of one unit of position change, basis points")
    ap.add_argument("--window", type=int, default=30)
    a = ap.parse_args()
    torch.set_num_threads(2)
    d = daily().loc[FIRST:LAST]
    c = d.close
    test = c.loc[VAL_TO:]

    print("1  the paper's benchmarks")
    for share in (0.10, 0.15, 0.20, 0.30):
        s = c.iloc[int(len(c) * (1 - share)):]
        print(f"   buy-and-hold over the last {100 * share:.0f}% of 2014-2024 ({s.index[0].date()} on): {100 * (s.iloc[-1] / s.iloc[0] - 1):+.1f}%"
              f", Sharpe {s.pct_change().mean() / s.pct_change().std() * np.sqrt(252):+.2f}")
    print(f"   best buy-and-hold over any {len(test)} days of 2014-2024: {100 * (c / c.shift(len(test)) - 1).max():+.1f}%")
    naive = np.sqrt((test.diff() ** 2).mean())
    print(f"   RMSE of 'tomorrow = today' on 2023-2024: {naive:.4f}, MAE {test.diff().abs().mean():.4f} "
          f"(paper: ARIMA 0.0048, moving average 0.0051, CNN-LSTM 0.0025)")
    print(f"   share of the day-to-day variance a forecast must explain for RMSE 0.0025: {100 * (1 - (0.0025 / naive) ** 2):.0f}%")

    print("2  forecasting an EMA-smoothed close instead of the close")
    for span in (2, 3, 5, 10):
        s = c.ewm(span=span).mean().loc[VAL_TO:]
        print(f"   span {span:2d}: RMSE of 'tomorrow = today' {np.sqrt((s.diff() ** 2).mean()):.4f}, of 'tomorrow = today + today's change' "
              f"{np.sqrt(((s.diff() - s.diff().shift(1)) ** 2).mean()):.4f}")

    print(f"3  the model without leaks (window {a.window}, cost {a.cost} bp per unit of position change)")
    f, nxt = features(d)
    ok = f.notna().all(axis=1) & nxt.notna()
    f, nxt = f[ok], nxt[ok]
    past = f.index < TRAIN_TO
    z = ((f - f[past].mean()) / f[past].std()).to_numpy(dtype=np.float32)       # scaled with the training years only
    X = torch.tensor(np.stack([z[i - a.window + 1:i + 1] for i in range(a.window - 1, len(z))]))
    days = f.index[a.window - 1:]
    ret = torch.tensor(nxt.to_numpy(dtype=np.float32)[a.window - 1:])
    y = ret / ret[days < TRAIN_TO].std()
    tr = torch.tensor(np.flatnonzero(days < TRAIN_TO))
    va = torch.tensor(np.flatnonzero((days >= TRAIN_TO) & (days < VAL_TO)))
    te = torch.tensor(np.flatnonzero(days >= VAL_TO))
    cost, rt = a.cost / 1e4, ret[te].numpy()
    rows = []
    for seed in range(a.seeds):
        p = forecast(X, y, tr, va, seed)
        e = p[te].numpy() * float(ret[days < TRAIN_TO].std())
        r2 = 1 - ((rt - e) ** 2).sum() / (rt ** 2).sum()
        hit = (np.sign(e) == np.sign(rt)).mean()
        pos = np.sign(e)
        sf = stats(pos * rt - cost * np.abs(np.diff(np.r_[0.0, pos])))
        pa = agent(X, p, ret, tr, va, cost, seed)(te.tolist(), True)
        sa = stats(pa * rt - cost * np.abs(np.diff(np.r_[0.0, pa])))
        rows.append((r2, hit, *sf, *sa, np.abs(pa).mean()))
        print(f"   seed {seed}: forecast R2 {100 * r2:+.2f}%, direction right {100 * hit:.1f}% | sign of forecast: Sharpe {sf[0]:+.2f}, "
              f"{sf[1]:+.1f}%, maxDD {sf[2]:.1f}% | Q-agent: Sharpe {sa[0]:+.2f}, {sa[1]:+.1f}%, maxDD {sa[2]:.1f}%, in the market "
              f"{100 * rows[-1][-1]:.0f}% of days", flush=True)
    m = np.mean(rows, axis=0)
    print(f"   mean of {a.seeds} seeds: forecast R2 {100 * m[0]:+.2f}%, direction {100 * m[1]:.1f}% | sign of forecast Sharpe {m[2]:+.2f}, "
          f"{m[3]:+.1f}% | Q-agent Sharpe {m[5]:+.2f}, {m[6]:+.1f}%")
    bh = stats(rt)
    print(f"   buy-and-hold on the same days: Sharpe {bh[0]:+.2f}, {bh[1]:+.1f}%, maxDD {bh[2]:.1f}%")
