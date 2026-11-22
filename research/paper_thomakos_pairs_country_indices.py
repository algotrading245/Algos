"""Gatev/Thomakos pairs on index CFDs (SPXUSD, GRXEUR, JPXJPY; NSXUSD has no data). Daily snapshot 15:00 UTC (file clock
is Athens; we use bars whose server time maps to 15:00 UTC), past-only.
Formation 120d: normalise each index to 1 at formation start, sd of the normalised spread over formation; open when the
spread at day t close exceeds K*sd (K=0.5 base, 2.0 Gatev variant), enter at day t+1 snapshot (one-day wait), exit when the
spread crosses 0 (decided at close, executed next snapshot) or after 20 days. Formation window rolls (re-based each day, so
spread = normalised gap since window start). Equal notional long cheap/short rich, each leg 0.5 notional scaled to a pair
vol target 10%. Cost bp per side per leg: SPX 1.0, GRX 1.5, JPX 3.0 (x1,1.5,2). Swap not charged (index CFD financing
roughly a few % a year on notional; added as 3%/yr on gross 1.0 notional per held day as extra cost).
Choose on <=2017, judge 2018+. Holdout dropped via tools/holdout."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

OUT = ROOT / "marketdata" / "candidates"
ID = "paper_thomakos_pairs_country_indices"
COST = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 3.0}
SWAP = 0.03 / 252  # per day on gross notional 1 (0.5 per leg x2), conservative


def snap(sym):
    h = pd.read_csv(ROOT / "marketdata" / "histdata" / f"{sym}_M1.csv.gz", usecols=["time", "close"])
    t = pd.to_datetime(h.time, unit="s")
    h.index = t
    h = holdout.drop(h[["close"]])
    # file clock = Europe/Athens; convert to UTC
    idx = h.index.tz_localize("Europe/Athens", nonexistent="shift_forward", ambiguous=True).tz_convert("UTC")
    s = pd.Series(h.close.values, index=idx)
    s = s[(s.index.hour == 14) & (s.index.minute == 55)] if False else s
    sel = s[(s.index.hour == 14) & (s.index.minute >= 50)]
    d = sel.groupby(sel.index.normalize().tz_localize(None)).last()
    return d[d.index.weekday < 5]


def sh(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def pair(a, b, K, cm, form=120, maxh=20):
    df = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    la = np.log(df.a.values)
    lb = np.log(df.b.values)
    n = len(df)
    ret = np.zeros(n)
    pos = 0
    held = 0
    ca = COST[a.name] if hasattr(a, "name") else 1
    cb = COST[b.name]
    cost_bp = (COST[a.name] + COST[b.name]) / 2
    # spread series: normalised gap, rebased at window start
    pend = None  # pending order to execute at day i snapshot: ('open', dir) or ('close',)
    for i in range(form, n - 1):
        # execute pending at snapshot i (entered at i price, return accrues i->i+1)
        if pend is not None:
            if pend[0] == "open" and pos == 0:
                pos = pend[1]
                held = 0
                ret[i] -= (ca + cb) * cm / 1e4 * 0.5  # entry both legs notional 0.5 each
            elif pend[0] == "close" and pos != 0:
                ret[i] -= (ca + cb) * cm / 1e4 * 0.5
                pos = 0
            pend = None
        if pos != 0:
            # pos=+1: long a short b
            r = 0.5 * (la[i + 1] - la[i]) - 0.5 * (lb[i + 1] - lb[i])
            ret[i + 1] += pos * r - SWAP * cm
            held += 1
        # signal at close of day i+? use info up to i (known at snapshot i): evaluated for execution at i+1
        w = slice(i - form, i + 1)
        na = la[w] - la[i - form]
        nb = lb[w] - lb[i - form]
        sp = na - nb
        sd = sp[:-1].std()
        cur = sp[-1]
        if pos == 0:
            if sd > 0 and abs(cur) > K * sd:
                pend = ("open", -int(np.sign(cur)))  # a rich (cur>0) -> short a long b
        else:
            if (pos == 1 and cur >= 0) or (pos == -1 and cur <= 0) or held >= maxh:
                pend = ("close",)
    return pd.Series(ret, index=df.index)


def main():
    S = {s: snap(s) for s in COST}
    for s, v in S.items():
        v.name = s
        print(s, len(v), v.index[0].date(), v.index[-1].date())
    pairs = [("SPXUSD", "GRXEUR"), ("SPXUSD", "JPXJPY"), ("GRXEUR", "JPXJPY")]
    res = {}
    for K in (0.5, 2.0):
        for cm in (1.0, 1.5, 2.0):
            cols = {f"{a}-{b}": pair(S[a], S[b], K, cm) for a, b in pairs}
            df = pd.DataFrame(cols).fillna(0)
            port = df.mean(axis=1) * 1.0
            vol = port[port.index < "2018"].std() * np.sqrt(252)
            sc = 0.10 / vol if vol > 0 else 1
            port = port * sc
            res[(K, cm)] = (df, port)
            a, b = port[port.index < "2018"], port[port.index >= "2018"]
            print(f"K={K} x{cm}: all {sh(port):.2f} <=2017 {sh(a):.2f} 2018+ {sh(b):.2f} | pairs", {c: round(sh(df[c]), 2) for c in df}, "scale", round(sc, 2))
    # choose variant on <=2017 at 1x
    best = max((0.5, 2.0), key=lambda K: sh(res[(K, 1.0)][1][res[(K, 1.0)][1].index < "2018"]))
    print("chosen K (<=2017):", best)
    OUT.mkdir(exist_ok=True)
    p = res[(best, 1.0)][1]
    ps = res[(best, 1.5)][1]
    pd.DataFrame({"day": p.index.strftime("%Y-%m-%d"), "r": p.values}).to_csv(OUT / f"{ID}.csv", index=False)
    pd.DataFrame({"day": ps.index.strftime("%Y-%m-%d"), "r": ps.values}).to_csv(OUT / f"{ID}_stress.csv", index=False)
    m = res[(best, 1.0)][0]
    mk = m.copy()
    mk.insert(0, "day", mk.index.strftime("%Y-%m-%d"))
    mk.to_csv(OUT / f"{ID}_markets.csv", index=False)


if __name__ == "__main__":
    main()
