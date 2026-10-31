"""Gold vs EURUSD residual fade (queue item prebuilt_gold_eur_residual_fade).
Daily closes at 21:00 UTC (XAUUSD dukascopy M1 UTC; EURUSD histdata M1, clock UTC-5 -> +5h).
Rule: r5 log return, beta = rolling 250d OLS (past only), z = e / rolling 250d sd, fade |z|>2, hold <=5d, exit z cross 0.
Signal at close t, earns return of t+1 onward. Costs per unit position change (fraction of notional).
Writes marketdata/candidates/gold_eur_resid{,_stress,_markets}.csv"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "tools")
import holdout

D = "marketdata/"


def daily_from_m1(path, shift_h, cols=("time", "close")):
    x = pd.read_csv(path, usecols=list(cols))
    t = pd.to_datetime(x.time + shift_h * 3600, unit="s")
    s = pd.Series(x.close.values, index=t).sort_index()
    s = s[~s.index.duplicated()]
    s = s[(s.index.hour < 21) | ((s.index.hour == 21) & (s.index.minute == 0))]
    # last bar at or before 21:00 on each calendar day
    d = s.groupby(s.index.normalize()).last()
    d = d[s.groupby(s.index.normalize()).apply(lambda g: g.index[-1].hour >= 19)]
    return d


def cached(name, fn):
    import os
    p = f"research/_cache_{name}.csv"
    if os.path.exists(p):
        return pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    s = fn()
    s.to_csv(p)
    return s


def futs(sym):
    x = pd.read_csv(D + f"commod/{sym}.csv", parse_dates=["date"]).set_index("date").close
    return x


def signal_pos(t, a, hold=5, zin=2.0, win=250):
    lt, la = np.log(t), np.log(a)
    rt, ra = lt.diff(5), la.diff(5)
    cov = rt.rolling(win).cov(ra)
    beta = cov / ra.rolling(win).var()
    e = rt - beta * ra
    z = e / e.rolling(win).std()
    zv = z.values
    pos = np.zeros(len(z))
    p = 0
    held = 0
    for i in range(len(z)):
        if np.isnan(zv[i]):
            pos[i] = 0
            continue
        if p != 0:
            held += 1
            if held >= hold or (p == 1 and zv[i] >= 0) or (p == -1 and zv[i] <= 0):
                p = 0
        if p == 0:
            if zv[i] > zin:
                p, held = -1, 0
            elif zv[i] < -zin:
                p, held = 1, 0
        pos[i] = p
    return pd.Series(pos, index=z.index)


def run(t, a, cost, **kw):
    pos = signal_pos(t, a, **kw)
    r = np.log(t).diff()
    gross = pos.shift(1) * r
    turn = pos.shift(1).diff().abs().fillna(0)
    return (gross - turn * cost).dropna(), pos


def sh(r):
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan


def report(name, r):
    r = holdout.drop(r)
    a, b = r[r.index < "2018-01-01"], r[r.index >= "2018-01-01"]
    print(f"{name:28s} all {sh(r):5.2f}  to2017 {sh(a):5.2f} (n={len(a)})  2018on {sh(b):5.2f} (n={len(b)})  ann {r.mean()*252*100:5.2f}%")


if __name__ == "__main__":
    xau = cached("xau", lambda: daily_from_m1(D + "dukascopy/XAUUSD_M1.csv.gz", 0))
    eur = cached("eur", lambda: daily_from_m1(D + "histdata/EURUSD_M1.csv.gz", 5))
    df = pd.concat([xau.rename("xau"), eur.rename("eur")], axis=1).dropna()
    df = holdout.drop(df)
    print("overlap", df.index[0].date(), df.index[-1].date(), len(df))
    si, gc = futs("SI"), futs("GC")
    sg = holdout.drop(pd.concat([si.rename("si"), gc.rename("gc")], axis=1).dropna())
    sg = sg[sg.si > 3]
    print("silver/gold futs", sg.index[0].date(), len(sg))
    # per-side costs (fraction): 1x
    C = {"xau": 2e-4, "eur": 1e-4, "si": 4e-4}
    legs = {}
    for k, (tgt, anc, c) in {"xau_vs_eur": (df.xau, df.eur, C["xau"]), "eur_vs_xau": (df.eur, df.xau, C["eur"]),
                              "si_vs_gc": (sg.si, sg.gc, C["si"])}.items():
        for m in (1, 1.5, 2):
            r, _ = run(tgt, anc, c * m)
            report(f"{k} cost x{m}", r)
            legs[(k, m)] = r
    main = {m: legs[("xau_vs_eur", m)] for m in (1, 1.5, 2)}
    # gold leg 1x/1.5x as candidate; combined xau+eur legs (two-pair book), equal weight
    comb = {m: (legs[("xau_vs_eur", m)].add(legs[("eur_vs_xau", m)], fill_value=0) / 2) for m in (1, 1.5, 2)}
    for m in (1, 1.5, 2):
        report(f"combined xau+eur x{m}", comb[m])
    for nm, d in (("gold_eur_resid", comb[1]), ("gold_eur_resid_stress", comb[1.5])):
        o = d.rename("r").rename_axis("day")
        o.to_csv(f"marketdata/candidates/{nm}.csv")
    mk = pd.concat([legs[(k, 1)].rename(k) for k in ("xau_vs_eur", "eur_vs_xau", "si_vs_gc")], axis=1).fillna(0)
    mk.rename_axis("day").to_csv("marketdata/candidates/gold_eur_resid_markets.csv")
