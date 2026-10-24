"""Index legs for AurumFunded on SPXUSD (US500; no US100 data): overnight drift and opening-range breakout.

Clock: cash open 16:30, cash close 23:00 on the data clock (checked from mean |1-min move| by half hour, winter and
summer). Config choice on the train half (to 2017) only; judged 2018 on; holdout dropped. Cost 1.5 bp round trip
(as research/tod_weekday_scan.py), stress 1.5x. Trials: 2 overnight + 4 ORB windows x 2 sides = 10.

    python research/index_legs_funded.py
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import holdout  # noqa: E402

COST = 1.5e-4
SPLIT = pd.Timestamp("2018-01-01")


def load():
    d = pd.read_csv(ROOT / "marketdata" / "histdata" / "SPXUSD_M1.csv.gz")
    d.index = pd.to_datetime(d.time, unit="s")
    return holdout.drop(d)


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(252) if len(r) > 50 and r.std() > 0 else float("nan")


def overnight(d, start_hm):
    """long from start (23:00 prev day or 01:00) to 16:30 same day; return booked on the exit day."""
    out = {}
    px = d.close
    for day, g in d.groupby(d.index.normalize()):
        if day.dayofweek > 4:
            continue
        a = g.between_time(*start_hm).close if False else None
        e = g[(g.index.hour == 16) & (g.index.minute == 30)]
        if e.empty:
            continue
        out[day] = e.open.iloc[0]
    return out


def main():
    d = load()
    days = {}
    for day, g in d.groupby(d.index.normalize()):
        if day.dayofweek > 4:
            continue
        days[day] = g
    keys = sorted(days)
    streams = {}
    # overnight: close at 22:59 of previous trading day (entry 23:00) or open at 01:00 -> open 16:30
    for name, ent in (("on_2300", (22, 59)), ("on_0100", (1, 0))):
        rs = {}
        prev = None
        for k in keys:
            g = days[k]
            e = g[(g.index.hour == 16) & (g.index.minute == 30)]
            if e.empty:
                continue
            if name == "on_2300":
                if prev is None:
                    prev = g
                    continue
                p = prev.close.iloc[-1]
            else:
                s = g[(g.index.hour == 1) & (g.index.minute == 0)]
                if s.empty:
                    prev = g
                    continue
                p = s.open.iloc[0]
            rs[k] = np.log(e.open.iloc[0] / p) - COST
            prev = g
        streams[name] = pd.Series(rs)
    # ORB
    for n in (5, 15, 30, 60):
        for side in ("both", "long"):
            rs = {}
            for k in keys:
                g = days[k]
                t = g[(g.index.hour * 60 + g.index.minute >= 16 * 60 + 30) & (g.index.hour < 23)]
                if len(t) < n + 30:
                    continue
                rng = t.iloc[:n]
                hi, lo = rng.high.max(), rng.low.min()
                rest = t.iloc[n:]
                pos = 0
                entry = None
                r = 0.0
                for ts, row in rest.iterrows():
                    if pos == 0:
                        if row.high > hi:
                            pos, entry = 1, hi
                        elif side == "both" and row.low < lo:
                            pos, entry = -1, lo
                        if pos:
                            stop = lo if pos == 1 else hi
                    else:
                        if pos == 1 and row.low <= stop:
                            r = np.log(stop / entry) - COST
                            pos = 2
                            break
                        if pos == -1 and row.high >= stop:
                            r = np.log(entry / stop) - COST
                            pos = 2
                            break
                if pos in (1, -1):
                    last = rest.close.iloc[-1]
                    r = pos * np.log(last / entry) - COST
                if pos != 0:
                    rs[k] = r
            streams[f"orb{n}_{side}"] = pd.Series(rs)
    rows = []
    for nme, s in streams.items():
        s = s.reindex(keys).fillna(0.0) if nme.startswith("orb") else s
        tr, te = s[s.index < SPLIT], s[s.index >= SPLIT]
        rows.append((nme, sharpe(tr), sharpe(te), s.mean() * 1e4, (s != 0).mean()))
        print(f"{nme:12s} train {sharpe(tr):6.2f} test {sharpe(te):6.2f} mean/day {s.mean()*1e4:6.2f} bp  active {(s!=0).mean():.2f}")
    best = max(rows, key=lambda x: (x[1] if x[1] == x[1] else -9))
    print("best on train:", best[0])
    s = streams[best[0]]
    s = s.reindex(keys).fillna(0.0) if best[0].startswith("orb") else s
    n = (s != 0)
    s2 = s - n * COST * 0.5
    cand = ROOT / "marketdata" / "candidates"
    s.rename("r").to_csv(cand / "index_legs_funded.csv", index_label="day")
    s2.rename("r").to_csv(cand / "index_legs_funded_stress.csv", index_label="day")
    print("2x cost halves:", sharpe((s - n * COST)[s.index < SPLIT]), sharpe((s - n * COST)[s.index >= SPLIT]))


if __name__ == "__main__":
    main()
