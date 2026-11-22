"""Deep Momentum Networks (Lim, Zohren, Roberts, "Enhancing Time Series Momentum Strategies Using Deep Neural
Networks", arXiv 1904.04912 / Journal of Financial Data Science 2019, read in full) on the 20 daily futures in
marketdata/commod.

Paper: position X_t = tanh(LSTM(u_t)) in the volatility-scaled time-series momentum frame
r_TSMOM = mean_i X_t sigma_tgt / sigma_t r_t+1 (eq. 1, sigma_tgt 15%, sigma = 60-day EWM std); inputs = returns over
1, 21, 63, 126, 252 days normalised by sigma sqrt(h), and the three MACD trend signals of Baz et al. (8/24, 16/48,
32/96); trained to maximise the annualised Sharpe ratio of the captured returns (eq. 16) on 63-day trajectories, with
dropout, Adam, 90/10 train/validation split by time, early stopping after 25 epochs without improvement (max 100),
50 random hyperparameter draws picked on validation Sharpe (dropout 0.1-0.5, hidden 5-80, batch 256-2048, lr 1e-5 to
1, max gradient norm 1e-4 to 10); retrained from scratch every 5 years on all data so far; the turnover regulariser
(eq. 35) puts the cost c |X_t/sigma_t - X_t-1/sigma_t-1| sigma_tgt into the loss.  88 ratio-adjusted futures,
1995-2015, no costs: Sharpe LSTM 2.80, MLP 1.38, linear 1.09, Sgn(returns) 1.19, MACD 0.98, long only 0.74; the
LSTM beats the benchmarks up to 2-3 bp of cost.

Here: the same 20 Yahoo front-month futures as research/drl_futures.py (returns clipped at +-20%, winsorised features
as in the paper's appendix), folds trained on all data up to 2011, 2016, 2021 and tested on the next five years
(2011 to 2026-10); 12 random draws per fold instead of 50 (narrowed grid), training cost c = 0 or 2 bp, test costs
2 and 10 bp.  At test time each day's position is the last output of the LSTM run over the previous 63 days.

    python research/deep_momentum.py [--draws 12]

Result (2026-10-15): rejected.  Out of sample 2011-2026, test cost 2 bp: LSTM trained without cost Sharpe -0.16,
trained with 2 bp cost +0.14 (2011-15 -0.44, 2016-20 -0.84, 2021-26 +0.80); long only +0.55, Sgn(12-month return)
+0.37, MACD -0.11; at 10 bp the LSTM is -0.82 / -0.05.  The validation Sharpe picked the models well in the first
fold (2.5-2.6 on 2009-2010) and then did not carry over to the test years, nor to the later folds (0.1-0.7).  On
these 20 markets after 2010 the trend premium the network has to learn is too weak (the benchmarks themselves earn
0.4-0.6), the paper's 2.80 rests on 88 markets in 1995-2015.  Correlation with the Hydra legs 0.03-0.07.
"""
import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drl_futures import ROOT, TGT, baselines, load, pnl, sharpe  # noqa: E402

SEQ = 63


def features(p):
    r = p.pct_change().clip(-0.2, 0.2)
    sig = r.ewm(span=60, min_periods=30).std()
    f = pd.DataFrame(index=p.index)
    for h in (1, 21, 63, 126, 252):
        f[f"r{h}"] = (p / p.shift(h) - 1) / (sig * np.sqrt(h))
    for s, l in ((8, 24), (16, 48), (32, 96)):
        q = (p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / s)).mean() - p.ewm(halflife=np.log(0.5) / np.log(1 - 1 / l)).mean())
        q = q / p.rolling(63).std()
        f[f"macd{s}"] = q / q.rolling(252).std()
    return f.clip(-5, 5), r, sig


def chunks(F, Y, S, idx):
    """Non-overlapping SEQ-day trajectories over the days idx (consecutive)."""
    out = []
    for a in range(0, len(idx) - SEQ + 1, SEQ):
        j = idx[a:a + SEQ]
        out.append((F[j], Y[j], S[j]))
    return out


def make_net(torch, hidden, dropout, nf):
    nn = torch.nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(nf, hidden, batch_first=True)
            self.drop = nn.Dropout(dropout)
            self.out = nn.Linear(hidden, 1)

        def forward(self, x):
            h, _ = self.lstm(self.drop(x))
            return torch.tanh(self.out(self.drop(h))).squeeze(-1)

    return Net()


def loss_fn(torch, X, Y, S, c):
    """Negative annualised Sharpe of X * sigma_tgt / sigma * r, less c times the change of X / sigma."""
    w = X * TGT / S
    R = w * Y
    if c > 0:
        R = R[:, 1:] - c * (w[:, 1:] - w[:, :-1]).abs()
    return -R.mean() / (R.std() + 1e-9) * np.sqrt(252)


def fit(torch, tr, va, hp, c, seed):
    torch.manual_seed(seed)
    net = make_net(torch, hp["hidden"], hp["dropout"], tr[0][0].shape[1])
    opt = torch.optim.Adam(net.parameters(), lr=hp["lr"])
    T = [torch.tensor(np.stack([x[k] for x in tr]), dtype=torch.float32) for k in range(3)]
    V = [torch.tensor(np.stack([x[k] for x in va]), dtype=torch.float32) for k in range(3)]
    best, state, wait = -1e9, None, 0
    for ep in range(100):
        net.train()
        perm = torch.randperm(len(T[0]))
        for b in range(0, len(perm), hp["batch"]):
            j = perm[b:b + hp["batch"]]
            loss = loss_fn(torch, net(T[0][j]), T[1][j], T[2][j], c)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), hp["clip"])
            opt.step()
        net.eval()
        with torch.no_grad():
            v = -loss_fn(torch, net(V[0]), V[1], V[2], c).item()
        if v > best:
            best, state, wait = v, {k: t.clone() for k, t in net.state_dict().items()}, 0
        else:
            wait += 1
            if wait >= 25:
                break
    net.load_state_dict(state)
    net.eval()
    return net, best


def predict(torch, net, F, idx):
    W = np.stack([F[i - SEQ + 1:i + 1] for i in idx])
    out = []
    with torch.no_grad():
        for b in range(0, len(W), 4096):
            out.append(net(torch.tensor(W[b:b + 4096], dtype=torch.float32))[:, -1].numpy())
    return np.concatenate(out)


if __name__ == "__main__":
    import torch
    torch.set_num_threads(2)
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=12)
    a = ap.parse_args()
    P = load()
    names, data, rets, sigs, base = list(P), [], {}, {}, {}
    for c in names:
        p = P[c].dropna()
        f, r, s = features(p)
        y = r.shift(-1)
        data.append((f.fillna(0).to_numpy(np.float32), y.fillna(0).to_numpy(np.float32),
                     s.bfill().to_numpy(np.float32), p.index.to_numpy()))
        rets[c], sigs[c], base[c] = r, s, baselines(p, r, s)
    hydra = pd.read_csv(ROOT / "hydra_legs_daily.csv.gz", index_col=0, parse_dates=True).sum(axis=1)
    rng = random.Random(0)
    grid = dict(dropout=(0.1, 0.2, 0.3, 0.4, 0.5), hidden=(5, 10, 20, 40, 80), batch=(64, 128, 256),
                lr=(1e-4, 1e-3, 1e-2), clip=(1e-2, 1e-1, 1.0, 10.0))
    draws = [{k: rng.choice(v) for k, v in grid.items()} for _ in range(a.draws)]
    pos = {tc: {c: [] for c in names} for tc in (0.0, 0.0002)}
    for t1, t2 in (("2011", "2016"), ("2016", "2021"), ("2021", "2027")):
        tr, va = [], []
        for F, Y, S, D in data:
            idx = np.flatnonzero(D < np.datetime64(t1))
            idx = idx[idx >= 252 + 63]
            idx = idx[:-1]                                      # the last day's target lies in the test block
            if len(idx) < 3 * SEQ:
                continue
            cut = int(len(idx) * 0.9)
            tr += chunks(F, Y, S, idx[:cut])
            va += chunks(F, Y, S, idx[cut:])
        for tc in pos:
            fits = sorted((fit(torch, tr, va, hp, tc, k) + (hp,) for k, hp in enumerate(draws)), key=lambda z: -z[1])
            net, v, hp = fits[0]
            print(f"fold {t1}-{t2} cost {tc * 1e4:.0f} bp: best validation Sharpe {v:.2f} with {hp}; "
                  f"next {[round(z[1], 2) for z in fits[1:4]]}", flush=True)
            for k, (F, Y, S, D) in enumerate(data):
                idx = np.flatnonzero((D >= np.datetime64(t1)) & (D < np.datetime64(t2)))
                idx = idx[idx >= SEQ + 252]
                if len(idx):
                    pos[tc][names[k]].append(pd.Series(predict(torch, net, F, idx), index=pd.DatetimeIndex(D[idx])))
    for cost in (0.0, 0.0002, 0.0010):
        lines = {n: pd.concat([pnl(base[c][n], rets[c], sigs[c], cost) for c in names], axis=1, sort=True)
                 .mean(axis=1)["2011":] for n in ("long", "sign", "macd")}
        for tc in pos:
            cols = [pnl(pd.concat(v).sort_index().reindex(rets[c].index), rets[c], sigs[c], cost)
                    for c, v in pos[tc].items() if v]
            lines[f"lstm c={tc * 1e4:.0f}bp"] = pd.concat(cols, axis=1, sort=True).mean(axis=1)["2011":]
        print(f"test cost {cost * 1e4:.0f} bp")
        for n, x in lines.items():
            corr = pd.concat([x, hydra], axis=1, sort=True).dropna().corr().iloc[0, 1]
            print(f"  {n:12s} Sharpe 2011-26 {sharpe(x):+.2f}  (2011-15 {sharpe(x[:'2015']):+.2f}, 2016-20 "
                  f"{sharpe(x['2016':'2020']):+.2f}, 2021-26 {sharpe(x['2021':]):+.2f})  corr Hydra {corr:+.2f}")
