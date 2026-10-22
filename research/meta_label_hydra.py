"""Meta-label filter on AurumHydra tester trades (worker queue item, 2026-10-22).

Trades: deals of the j6 tester run (size 1, legs on, FTMO data, 2024-01 to 2026-10; the holdout from 2025-10-13 is
dropped). In and out deals are paired FIFO per symbol and direction, volume-proportional. Label: net trade pnl > 0.
Features at entry, past only: leg (comment), symbol, direction, hour, weekday, month-end flag, the symbol's prior-day
ATR14 / price, 5-day return and 20-day slope in ATR units (daily bars up to the day BEFORE entry; the histdata clock
differs from the server clock by hours, so only completed days before the entry day are used).
Walk-forward: quarterly test folds from 2024-10, train on earlier trades whose exit is before the fold start minus
5 days (purge + embargo). LightGBM, 3 seeds, probabilities averaged; keep a trade when p > thr.
Configs tried (all counted as trials): 2 parameter sets x 3 thresholds x 3 seeds = 18.
Pre-registered candidate: params A, thr 0.50. Baselines: all trades; leg-mean rule (keep a leg when its train hit
rate > 50%); random keep at the same rate (200 draws).
Daily stream = sum of kept trades' pnl / balance at entry, by exit day.
"""
from pathlib import Path
import re
import sys
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

HTM = ROOT / "backtests/2026-10-17_1116_AurumHydra_size1b_on/AurumHydra_size1b_on.htm"
CUT = pd.Timestamp("2025-10-13")


def parse():
    t = open(HTM, encoding="utf-16", errors="ignore").read()
    k = t.rfind("<b>Deals</b>")
    rows = []
    for tr in t[k:].split("<tr")[1:]:
        c = [re.sub("<[^>]+>", "", x).replace("\xa0", " ").strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        for j in (5, 6, 8, 9, 10, 11):
            if len(c) == 13:
                c[j] = c[j].replace(" ", "")
        if len(c) == 13 and re.match(r"\d{4}\.", c[0]) and c[3] in ("buy", "sell"):
            rows.append(c)
    return rows


def f(x):
    return float(x) if x not in ("", "-") else 0.0


def pair(rows):
    q = {}
    out = []
    for c in rows:
        ts = pd.Timestamp(c[0].replace(".", "-"))
        sym, side, io, vol = c[2], c[3], c[4], f(c[5])
        comm, swap, prof, bal = f(c[8]), f(c[9]), f(c[10]), f(c[11])
        if io == "in":
            q.setdefault((sym, side), []).append([ts, c[12], vol, comm, vol, bal])
        elif io == "out":
            key = (sym, "sell" if side == "buy" else "buy")
            qq = q.get(key, [])
            left = vol
            while left > 1e-9 and qq:
                p = qq[0]
                take = min(left, p[4])
                share = take / vol
                share_in = take / p[2]
                net = prof * share + swap * share + comm * share + p[3] * share_in
                out.append(dict(sym=sym, dir=1 if key[1] == "buy" else -1, leg=p[1], t_in=p[0], t_out=ts,
                                net=net, cost=-(comm * share + p[3] * share_in), bal=p[5]))
                p[4] -= take
                left -= take
                if p[4] <= 1e-9:
                    qq.pop(0)
    return pd.DataFrame(out)


def daily_feats(sym):
    d = pd.read_csv(ROOT / "marketdata/histdata" / f"{sym}_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    d = holdout.drop(d)
    dd = d.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = dd.close.shift(1)
    tr = pd.concat([dd.high - dd.low, (dd.high - pc).abs(), (dd.low - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out = pd.DataFrame({
        "atr_rel": atr / dd.close,
        "ret5": (dd.close / dd.close.shift(5) - 1) / (atr / dd.close),
        "slope20": (dd.close / dd.close.shift(20) - 1) / (atr / dd.close),
    })
    return out.shift(1)  # values known at the start of the day (prior completed day)


def main():
    tr = pair(parse())
    tr = tr[tr.t_out < CUT].copy()
    tr["leg"] = tr.leg.replace("", "none")
    tr["leg"] = tr.leg.str.replace(r"^sl .*", "sl", regex=True).str.replace("AurumHydra ", "", regex=False)
    tr["r"] = tr.net / tr.bal
    tr["day"] = tr.t_out.dt.normalize()
    print("trades", len(tr), "legs", tr.leg.value_counts().to_dict())
    feats = {}
    for s in tr.sym.unique():
        fn = ROOT / "marketdata/histdata" / f"{s}_M1.csv.gz"
        if fn.exists():
            feats[s] = daily_feats(s)
    X = pd.DataFrame(index=tr.index)
    for col in ["atr_rel", "ret5", "slope20"]:
        v = []
        for i, r in tr.iterrows():
            ft = feats.get(r.sym)
            v.append(np.nan if ft is None or r.t_in.normalize() not in ft.index else ft.at[r.t_in.normalize(), col])
        X[col] = v
    X["leg"] = tr.leg.astype("category").cat.codes
    X["sym"] = tr.sym.astype("category").cat.codes
    X["dir"] = tr.dir
    X["hour"] = tr.t_in.dt.hour
    X["dow"] = tr.t_in.dt.dayofweek
    X["me"] = (tr.t_in.dt.day >= 27).astype(int)
    y = (tr.net > 0).astype(int)

    folds = pd.date_range("2024-10-01", "2025-10-01", freq="QS")
    folds = list(folds) + [CUT]
    # first test fold start 2024-10-01 ... last ends at CUT
    PARAMS = {"A": dict(n_estimators=150, learning_rate=0.03, num_leaves=7, min_child_samples=40, subsample=0.8,
                        subsample_freq=1, colsample_bytree=0.8),
              "B": dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20, subsample=0.8,
                        subsample_freq=1, colsample_bytree=0.8)}
    P = {k: {s: pd.Series(np.nan, index=tr.index) for s in (0, 1, 2)} for k in PARAMS}
    legrule = pd.Series(np.nan, index=tr.index)
    for a, b in zip(folds[:-1], folds[1:]):
        te = (tr.t_in >= a) & (tr.t_in < b)
        trn = tr.t_out < a - pd.Timedelta(days=5)
        if te.sum() == 0 or trn.sum() < 300:
            continue
        hit = y[trn].groupby(tr.leg[trn]).mean()
        legrule[te] = tr.leg[te].map(hit).fillna(0.5)
        for k, pr in PARAMS.items():
            for s in (0, 1, 2):
                m = lgb.LGBMClassifier(random_state=s, verbose=-1, **pr)
                m.fit(X[trn], y[trn])
                P[k][s][te] = m.predict_proba(X[te])[:, 1]
    oos = legrule.notna()
    base = tr[oos]
    print("oos trades", oos.sum(), "from", base.t_in.min(), "to", base.t_out.max())

    def stream(mask, extra_cost=0.0):
        t = tr[mask & oos]
        rr = (t.net - extra_cost * t.cost) / t.bal
        return rr.groupby(t.day).sum()

    def sharpe(s, days):
        s = s.reindex(days, fill_value=0.0)
        return s.mean() / s.std() * np.sqrt(252) if s.std() > 0 else np.nan

    days = pd.bdate_range(base.day.min(), base.day.max())
    allm = pd.Series(True, index=tr.index)
    res = {}
    res["all trades"] = (sharpe(stream(allm), days), oos.sum())
    res["leg rule >50%"] = (sharpe(stream(legrule > 0.5), days), int((legrule > 0.5).sum()))
    rng = np.random.default_rng(0)
    trials = 0
    for k in PARAMS:
        pm = sum(P[k][s] for s in (0, 1, 2)) / 3
        for thr in (0.45, 0.50, 0.55):
            trials += 3
            keep = pm > thr
            res[f"lgb {k} thr {thr}"] = (sharpe(stream(keep), days), int((keep & oos).sum()))
    # random keep at the pre-registered rate
    keep = (sum(P["A"][s] for s in (0, 1, 2)) / 3) > 0.50
    rate = (keep & oos).sum() / oos.sum()
    rs = []
    for _ in range(200):
        rk = pd.Series(rng.random(len(tr)) < rate, index=tr.index)
        rs.append(sharpe(stream(rk), days))
    res["random same rate (mean)"] = (np.nanmean(rs), int(rate * oos.sum()))
    print("random same rate Sharpe 5/50/95 pct", np.nanpercentile(rs, [5, 50, 95]).round(2))
    # per seed for candidate
    for s in (0, 1, 2):
        kk = P["A"][s] > 0.50
        res[f"seed {s} A 0.50"] = (sharpe(stream(kk), days), int((kk & oos).sum()))
    for k, (sh, n) in res.items():
        print(f"{k:28s} Sharpe {sh:6.2f}  trades {n}")
    print("configs tried (trials):", trials, "+ leg rule + random = counted as", trials + 2)

    # candidate streams, pre-registered A / 0.50, 1x and stress (commission x1.5; the spread is already in the fills)
    cand = stream(keep).reindex(days, fill_value=0.0)
    cstress = stream(keep, extra_cost=0.5).reindex(days, fill_value=0.0)
    out = ROOT / "marketdata/candidates"
    pd.DataFrame({"day": days.strftime("%Y-%m-%d"), "r": cand.values}).to_csv(out / "meta_label_hydra.csv", index=False)
    pd.DataFrame({"day": days.strftime("%Y-%m-%d"), "r": cstress.values}).to_csv(out / "meta_label_hydra_stress.csv", index=False)
    allr = stream(allm).reindex(days, fill_value=0.0)
    print("return all", round(allr.sum(), 3), "kept", round(cand.sum(), 3))
    print("max dd kept / all", round((cand.cumsum() - cand.cumsum().cummax()).min(), 3),
          round((allr.cumsum() - allr.cumsum().cummax()).min(), 3))


if __name__ == "__main__":
    main()
