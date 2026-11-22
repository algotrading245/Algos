"""Daily z-score mean reversion on AUDNZD, EURGBP, EURCHF, NZDCAD, one parameter set.
Daily close = last M1 bar at 20:xx UTC (file clock Europe/Athens), outside the 23-01 rollover. z = (close - mean20)/sd20 using
closes up to and including today. Long below -2, short above +2, exit when z crosses 0, time stop 5 days. Signal and fill at the same
snapshot close (decided on that close price, filled at it, spread charged). Round-trip cost bp: AUDNZD 2.0, EURGBP 1.2, EURCHF 1.6,
NZDCAD 2.6 (research/grid_crosses.py), swap 1bp per held day at 1x (conservative). x1, x1.5, x2. No tuning: defaults from the item.
Portfolio = mean of the 4 markets scaled to 10% vol on <=2017. Holdout dropped via tools/holdout."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "leg_cross_dailyz_meanrev_3mkts"
COST = {"AUDNZD": 2.0, "EURGBP": 1.2, "EURCHF": 1.6, "NZDCAD": 2.6}
SWAP_BP = 1.0
LB, Z, MAXH = 20, 2.0, 5


def snap(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz", usecols=["time", "close"])
    h.index = pd.to_datetime(h.time, unit="s")
    h = holdout.drop(h[["close"]])
    idx = h.index.tz_localize("Europe/Athens", nonexistent="shift_forward", ambiguous=True).tz_convert("UTC")
    s = pd.Series(h.close.values, index=idx)
    sel = s[(s.index.hour == 20)]
    d = sel.groupby(sel.index.normalize().tz_localize(None)).last()
    return d[d.index.weekday < 5]


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def run(c, cost_bp, cm):
    l = np.log(c.values)
    m = pd.Series(c.values).rolling(LB).mean().values
    sd = pd.Series(c.values).rolling(LB).std().values
    z = (c.values - m) / sd
    n = len(c)
    ret = np.zeros(n)
    pos = 0
    held = 0
    for i in range(LB, n - 1):
        # P&L accrual i -> i+1 for position held at close i
        if pos != 0:
            ret[i + 1] += pos * (l[i + 1] - l[i]) - SWAP_BP * cm / 1e4
            held += 1
        if pos != 0 and ((pos == 1 and z[i + 1] >= 0) or (pos == -1 and z[i + 1] <= 0) or held >= MAXH):
            pass  # exit decided on day i+1 close, handled in next iteration
        # decisions at close i (price known)
        if pos != 0 and ((pos == 1 and z[i] >= 0) or (pos == -1 and z[i] <= 0) or held >= MAXH):
            ret[i] -= cost_bp * cm / 2e4
            pos = 0
        if pos == 0 and np.isfinite(z[i]):
            if z[i] < -Z:
                pos, held = 1, 0
                ret[i] -= cost_bp * cm / 2e4
            elif z[i] > Z:
                pos, held = -1, 0
                ret[i] -= cost_bp * cm / 2e4
    return pd.Series(ret, index=c.index)


def main():
    S = {s: snap(s) for s in COST}
    for s, v in S.items():
        print(s, len(v), v.index[0].date(), v.index[-1].date())
    res = {}
    for cm in (1.0, 1.5, 2.0):
        df = pd.DataFrame({s: run(S[s], COST[s], cm) for s in COST}).fillna(0)
        res[cm] = df
    df1 = res[1.0]
    port1 = df1.mean(axis=1)
    sc = 0.10 / (port1[port1.index < "2018"].std() * np.sqrt(252))
    for cm in (1.0, 1.5, 2.0):
        p = res[cm].mean(axis=1) * sc
        a, b = p[p.index < "2018"], p[p.index >= "2018"]
        print(f"x{cm}: all {sh(p):.2f} <=2017 {sh(a):.2f} 2018+ {sh(b):.2f} | markets", {c: round(sh(res[cm][c]), 2) for c in res[cm]}, "scale", round(sc, 2))
    for c in df1:
        x = df1[c]
        print(c, "pre", round(sh(x[x.index < "2018"]), 2), "post", round(sh(x[x.index >= "2018"]), 2))
    p = res[1.0].mean(axis=1) * sc
    ps = res[1.5].mean(axis=1) * sc
    OUT.mkdir(exist_ok=True)
    pd.DataFrame({"day": p.index.strftime("%Y-%m-%d"), "r": p.values}).to_csv(OUT / f"{ID}.csv", index=False)
    pd.DataFrame({"day": ps.index.strftime("%Y-%m-%d"), "r": ps.values}).to_csv(OUT / f"{ID}_stress.csv", index=False)
    mk = df1.copy()
    mk.insert(0, "day", mk.index.strftime("%Y-%m-%d"))
    mk.to_csv(OUT / f"{ID}_markets.csv", index=False)


if __name__ == "__main__":
    main()
