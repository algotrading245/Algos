"""Small 1D CNN vs LightGBM vs baselines on XAUUSD M15: next-hour (4 bars) direction.

Features (past only): last 32 M15 log returns divided by trailing 96-bar std (CNN: sequence; LGBM: same 32 + 3 vol
terms). Target: sign of the next 4-bar return. Walk-forward: refit each January on all data before it, purge 4 bars,
embargo 1 day; test years 2012 to 2025-09 (holdout dropped through tools/holdout.py). Trading: decisions at every
hour boundary (every 4th bar), position = sign(p-0.5) for the next hour, cost per position change.
Costs: 2 bp round trip x1.0/1.5/2.0 (gold spread assumption used by earlier scans), charged on |dpos|/2... i.e. each
unit of position change costs half of the round trip. Baselines: buy and hold, plain momentum (sign of last 4 bars),
"tomorrow = today" (sign of the last hour kept, same as momentum on this horizon, reported once as persistence of
the previous day's sign), LGBM. Trials: CNN 1 config x 3 seeds + LGBM 1 config x 3 seeds = 6 extra trials.
Stream for tools/gates.py: candidate nn_gold_m15 = CNN 3-seed mean probability.
    python research/nn_gold_m15.py
"""
from pathlib import Path
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import lightgbm as lgb  # noqa: E402

torch.set_num_threads(4)
L = 32
H = 4
COST_RT = 2.0e-4
SEEDS = [0, 1, 2]
SPLIT = pd.Timestamp("2018-01-01")
FIRST_TEST = 2012


def load():
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / "XAUUSD_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    c = d.close.resample("15min").last().dropna()
    # drop the rollover hour (server 23-01) rows from decisions later; keep bars for returns
    return c


def build(c):
    lr = np.log(c).diff()
    vol = lr.rolling(96).std()
    n = len(c)
    arr = lr.values
    X = np.full((n, L), np.nan, dtype=np.float32)
    for k in range(L):
        X[:, k] = arr[np.maximum(np.arange(n) - (L - 1 - k), 0)] if False else np.roll(arr, L - 1 - k)
    X[:L] = np.nan
    X = (X / vol.values[:, None]).astype(np.float32)
    fwd = np.log(c).shift(-H) - np.log(c)
    idx = c.index
    # keep samples whose forward window is contiguous (<= 70 min) and not across weekend
    gap = (idx.to_series().shift(-H) - idx.to_series()).dt.total_seconds().values
    ok = (gap <= 3600 + 600) & np.isfinite(X).all(1) & np.isfinite(fwd.values) & np.isfinite(vol.values)
    hour = idx.hour
    ok &= ~((hour >= 22) | (hour < 1))  # rollover window excluded from decisions
    ok &= idx.dayofweek < 5
    return X, fwd.values, ok, vol.values


class CNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(1, 16, 5, padding=2), nn.ReLU(),
            nn.Conv1d(16, 16, 5, padding=2, stride=2), nn.ReLU(),
            nn.Conv1d(16, 16, 3, padding=1, stride=2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(16, 1))

    def forward(self, x):
        return self.net(x.unsqueeze(1)).squeeze(1)


def fit_cnn(X, y, seed):
    torch.manual_seed(seed)
    np.random.seed(seed)
    m = CNN()
    opt = torch.optim.AdamW(m.parameters(), 2e-3, weight_decay=1e-3)
    Xt = torch.tensor(np.clip(X, -6, 6))
    yt = torch.tensor(y, dtype=torch.float32)
    nv = int(len(Xt) * 0.9)
    best, bs, bad = 1e9, None, 0
    for ep in range(6):
        m.train()
        perm = torch.randperm(nv)
        for i in range(0, nv, 1024):
            b = perm[i:i + 1024]
            opt.zero_grad()
            nn.functional.binary_cross_entropy_with_logits(m(Xt[b]), yt[b]).backward()
            opt.step()
        m.eval()
        with torch.no_grad():
            v = nn.functional.binary_cross_entropy_with_logits(m(Xt[nv:]), yt[nv:]).item()
        if v < best - 1e-5:
            best, bs, bad = v, {k: t.clone() for k, t in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                break
    m.load_state_dict(bs)
    m.eval()
    return m


def pred_cnn(m, X):
    with torch.no_grad():
        return torch.sigmoid(m(torch.tensor(np.clip(X, -6, 6)))).numpy()


def fit_lgb(X, y, seed):
    return lgb.LGBMClassifier(n_estimators=150, learning_rate=0.03, num_leaves=15, min_child_samples=500,
                              subsample=0.7, subsample_freq=1, colsample_bytree=0.7, random_state=seed,
                              verbose=-1, n_jobs=4).fit(np.clip(X, -6, 6), y)


def stream(sig, fwd, idx, ok, cost_mult):
    """sig in {-1,0,1} per sample at hourly decision points; returns daily returns after costs."""
    df = pd.DataFrame({"sig": sig, "fwd": fwd}, index=idx)[ok]
    df = df[df.index.minute == 0]
    pos = df.sig
    prev = pos.shift(1).fillna(0)
    r = pos * df.fwd - (pos - prev).abs() * COST_RT / 2 * cost_mult
    return r.groupby(r.index.normalize()).sum()


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def main():
    c = load()
    X, fwd, ok, vol = build(c)
    idx = c.index
    y = (fwd > 0).astype(np.float32)
    years = sorted(set(idx.year))
    P = {"cnn": np.full(len(c), np.nan), "lgb": np.full(len(c), np.nan)}
    acc = {"cnn": [], "lgb": []}
    for yr in [t for t in years if t >= FIRST_TEST]:
        tr = ok & (idx < pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=1))
        te = ok & (idx.year == yr)
        if te.sum() == 0:
            continue
        # purge: training labels end before the test start by construction (1 day embargo above)
        Xtr, ytr = X[tr], y[tr]
        pc = np.mean([pred_cnn(fit_cnn(Xtr, ytr, s), X[te]) for s in SEEDS], axis=0)
        pl = np.mean([fit_lgb(Xtr, ytr, s).predict_proba(X[te])[:, 1] for s in SEEDS], axis=0)
        P["cnn"][te] = pc
        P["lgb"][te] = pl
        for k, p in (("cnn", pc), ("lgb", pl)):
            acc[k].append(((p > 0.5) == (y[te] > 0.5)).mean())
        print(yr, "acc cnn %.4f lgb %.4f" % (acc["cnn"][-1], acc["lgb"][-1]), flush=True)
    live = ok & np.isfinite(P["cnn"])
    sigs = {
        "cnn": np.sign(P["cnn"] - 0.5),
        "lgb": np.sign(P["lgb"] - 0.5),
        "momentum": np.sign(X[:, -H:].sum(1)),
        "buyhold": np.ones(len(c)),
    }
    out = {}
    for name, s in sigs.items():
        row = []
        for cm in (1.0, 1.5, 2.0):
            r = stream(s, fwd, idx, live, cm)
            row.append(r)
        out[name] = row
        a, b = row[0][row[0].index < SPLIT], row[0][row[0].index >= SPLIT]
        print("%-9s sharpe all %.2f  halves(<2018, 2018+) %.2f / %.2f  1.5x %.2f  2x %.2f  turnover/day %.1f" % (
            name, sharpe(row[0]), sharpe(a), sharpe(b), sharpe(row[1]), sharpe(row[2]),
            (pd.Series(s, index=idx)[live][lambda z: z.index.minute == 0].diff().abs().groupby(
                lambda t: t.normalize()).sum().mean())), flush=True)
    cand = ROOT / "marketdata" / "candidates"
    for suf, i in (("", 0), ("_stress", 1)):
        r = out["cnn"][i]
        pd.DataFrame({"day": r.index.strftime("%Y-%m-%d"), "r": r.values}).to_csv(cand / f"nn_gold_m15{suf}.csv", index=False)


if __name__ == "__main__":
    main()
