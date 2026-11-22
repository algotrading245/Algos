"""Chen-Rogoff-Rossi 2010: sign of the month return of AUD, NZD, CAD (vs USD, equal weight) -> long/short commodity next month.
No fitting. Commodities from marketdata/commod (roll days zeroed). Costs: spread per switch, swap per calendar night.
Run: python research/chen_rogoff_rossi_fx_commod.py [--write]"""
import sys
sys.path.insert(0, "tools")
import numpy as np, pandas as pd
import holdout

SWAP_BP = 2.5     # per calendar night, either side (conservative)
SPREAD = {"CL": 4.0, "BZ": 4.0, "HG": 5.0, "SI": 5.0, "GC": 1.5}   # bp per side

def fx_month():
    out = []
    for f, inv in [("DEXUSAL", 1), ("DEXUSNZ", 1), ("DEXCAUS", -1)]:
        d = pd.read_csv(f"marketdata/fred/{f}.csv", parse_dates=["observation_date"]).set_index("observation_date").iloc[:, 0]
        d = pd.to_numeric(d, errors="coerce").dropna()
        m = d.groupby(d.index.to_period("M")).last()
        out.append(inv * np.log(m).diff())
    s = pd.concat(out, axis=1).mean(axis=1).dropna()
    return s

def load(sym):
    d = pd.read_csv(f"marketdata/commod/{sym}.csv", parse_dates=["date"]).set_index("date")["close"]
    r = d.pct_change()
    r[r.abs() > 0.10] = 0.0
    return holdout.drop(r.dropna())

def run(sym, sig, cm=1.0, side="both"):
    r = load(sym)
    per = r.index.to_period("M")
    pos = pd.Series([np.sign(sig.get(p - 1, 0.0)) for p in per], index=r.index)
    if side == "long": pos = pos.clip(lower=0)
    if side == "short": pos = pos.clip(upper=0)
    gap = pd.Series(r.index, index=r.index).diff().dt.days.fillna(1).clip(1, 4)
    held = pos.shift(1).fillna(0)
    swap = held.abs() * gap * SWAP_BP * 1e-4 * cm
    sw = pos.diff().abs().fillna(0) * SPREAD[sym] * 1e-4 * cm
    return held * r - swap - sw

def sh(x):
    return x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else 0

if __name__ == "__main__":
    sig = fx_month()
    sig = sig[sig.index < pd.Period("2025-10", "M")]
    print("fx months", len(sig), sig.index[0], sig.index[-1])
    mk = {}
    for s in ["CL", "BZ", "HG", "SI"]:
        for side in ["both", "long", "short"]:
            x = run(s, sig, 1.0, side)
            a, b = x[x.index < "2018-01-01"], x[x.index >= "2018-01-01"]
            print(f"{s} {side}: all {sh(x):.2f} h1 {sh(a):.2f} h2 {sh(b):.2f}")
        mk[s] = run(s, sig, 1.0)
        print(f"{s} x1.5 {sh(run(s, sig, 1.5)):.2f} x2 {sh(run(s, sig, 2.0)):.2f}")
    M = pd.DataFrame(mk).dropna(how="all").fillna(0)
    M = M[M.index >= "2010-01-01"]
    for name, cols in [("ALL4", list(M.columns)), ("CL+HG+SI", ["CL", "HG", "SI"]), ("HG+SI", ["HG", "SI"])]:
        bk = M[cols].mean(axis=1)
        S = pd.DataFrame({k: run(k, sig, 1.5) for k in cols}).fillna(0).mean(axis=1)
        S = S[S.index >= "2010-01-01"]
        a, b = bk[bk.index < "2018-01-01"], bk[bk.index >= "2018-01-01"]
        print(name, "all", round(sh(bk), 2), "h1", round(sh(a), 2), "h2", round(sh(b), 2), "stress", round(sh(S), 2))
    if "--write" in sys.argv:
        cols = ["CL", "HG", "SI"]
        bk = M[cols].mean(axis=1)
        S = pd.DataFrame({k: run(k, sig, 1.5) for k in cols}).fillna(0).mean(axis=1)
        S = S[S.index >= "2010-01-01"]
        bk.rename("r").rename_axis("day").to_csv("marketdata/candidates/chen_rogoff_rossi_fx_commod.csv")
        S.rename("r").rename_axis("day").to_csv("marketdata/candidates/chen_rogoff_rossi_fx_commod_stress.csv")
        M[cols].rename_axis("day").to_csv("marketdata/candidates/chen_rogoff_rossi_fx_commod_markets.csv")
        print("written")
