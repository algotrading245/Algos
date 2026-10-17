"""The fixed gates every candidate leg must pass before it goes into an EA (pipeline steps 7-11).  The thresholds are
constants in this file on purpose: an agent that builds a candidate may not change them, and the reviewer checks
that they were not changed (`git log -p tools/gates.py`).

A candidate is a daily return series (fraction of equity at the size it would trade at) in
marketdata/candidates/<id>.csv (columns day,r) with the same at 1.5x costs in <id>_stress.csv, or one of the
cached legs in marketdata/candidate_legs_daily.csv.gz (noise, breakout).

    python tools/gates.py breakout                 # judge, log one trial, write the verdict into docs/candidates.json
    python tools/gates.py noise --weight 0.55      # a fixed weight instead of the one fitted to 2017
    python tools/gates.py breakout --dry-run       # judge only (the reviewer's run): no trial logged, nothing written

Gates, in order; the first failure stops the idea (the ledger records which gate):
  1 halves   Sharpe at the real cost >= 0.5 both to 2017 and from 2018 (settings chosen to 2017, judged after)
  2 costs    Sharpe at 1.5x the cost >= 0.3 over the whole sample
  3 dsr      Deflated Sharpe Ratio (Bailey, Lopez de Prado 2014) >= 0.90, with N = every trial ever logged in
             docs/trials.jsonl plus the 47 counted before the log existed (london_breakout.py's generous count)
  4 corr     correlation with the Hydra book <= +0.20 and with each Hydra leg <= +0.30; only positive correlation
             fails (a negative one is a hedge, which helps the book)
  5 goal     with the weight fitted on data to 2017, Hydra's Sharpe from 2018 rises by >= 0.03, and so does
             P(5x in a month) = N(N^-1(0.2) + Sharpe sqrt(1/12)) (Browne 1999)
"""
import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

ROOT = Path(__file__).resolve().parent.parent
HYDRA = ROOT / "marketdata" / "hydra_legs_daily.csv.gz"
CACHED = ROOT / "marketdata" / "candidate_legs_daily.csv.gz"
CANDIDATES = ROOT / "marketdata" / "candidates"
TRIALS = ROOT / "docs" / "trials.jsonl"
LEDGER = ROOT / "docs" / "candidates.json"

SPLIT = "2018-01-01"
MIN_HALF_SHARPE = 0.5
MIN_STRESS_SHARPE = 0.3
MIN_DSR = 0.90
TRIALS_BEFORE_LOG = 47
MAX_CORR_BOOK = 0.20
MAX_CORR_LEG = 0.30
MIN_SHARPE_GAIN = 0.03
EULER = 0.5772156649


def sharpe(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std() * np.sqrt(252)) if len(x) > 2 and x.std() > 0 else 0.0


def p_goal(s):
    return float(norm.cdf(norm.ppf(0.2) + s * math.sqrt(1 / 12)))


def trials_logged():
    """One per gates.py run, plus every rule a scan tried (tools/edge_scan.py logs its whole search as one line
    with "count": the number of rules it looked at, not only the survivors)."""
    if not TRIALS.exists():
        return 0
    return sum(int(json.loads(line).get("count", 1)) for line in TRIALS.open() if line.strip())


def deflated(r, n_trials):
    """Probability that the true Sharpe beats the best of n_trials lucky ones (daily figures, null variance 1/T)."""
    r = pd.Series(r).dropna()
    t = len(r)
    sr = r.mean() / r.std()
    sr0 = math.sqrt(1 / t) * ((1 - EULER) * norm.ppf(1 - 1 / n_trials)
                              + EULER * norm.ppf(1 - 1 / (n_trials * math.e)))
    g3, g4 = skew(r), kurtosis(r, fisher=False)
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return float(norm.cdf(z)), float(sr0 * math.sqrt(252))


def load(cid):
    f = CANDIDATES / f"{cid}.csv"
    if f.exists():
        r = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
        fs = CANDIDATES / f"{cid}_stress.csv"
        stress = pd.read_csv(fs, index_col=0, parse_dates=True).iloc[:, 0] if fs.exists() else None
        return r, stress
    c = pd.read_csv(CACHED, index_col=0, parse_dates=True)
    if cid in c:
        return c[cid], None
    sys.exit(f"no series for {cid}: write {f} (columns day,r)")


def judge(cid, weight=None, stress_sharpe=None, n_extra=1):
    r, stress = load(cid)
    legs = pd.read_csv(HYDRA, index_col=0, parse_dates=True)
    legs = legs[legs.index.dayofweek < 5]
    book = legs.sum(axis=1)
    r = r[r.index.dayofweek < 5].reindex(book.index.union(r.index)).fillna(0.0)
    r = r[r.index >= book.index[0]]
    gates = []

    def gate(name, ok, figure, rule):
        gates.append({"gate": name, "pass": None if ok is None else bool(ok), "figure": figure, "rule": rule})

    a, b = sharpe(r[r.index < SPLIT]), sharpe(r[r.index >= SPLIT])
    gate("halves", a >= MIN_HALF_SHARPE and b >= MIN_HALF_SHARPE, f"{a:.2f} / {b:.2f}",
         f">= {MIN_HALF_SHARPE} to 2017 and from 2018")
    if stress is not None:
        stress_sharpe = sharpe(stress[stress.index.dayofweek < 5])
    gate("costs", None if stress_sharpe is None else stress_sharpe >= MIN_STRESS_SHARPE,
         "missing" if stress_sharpe is None else f"{stress_sharpe:.2f}", f">= {MIN_STRESS_SHARPE} at 1.5x cost")
    n = TRIALS_BEFORE_LOG + trials_logged() + n_extra
    p, sr0 = deflated(r[r != 0] if (r == 0).mean() > 0.5 else r, n)
    gate("dsr", p >= MIN_DSR, f"{p:.3f} (N={n}, luck bar {sr0:.2f})", f">= {MIN_DSR}")
    joint = book.index.intersection(r.index)
    cb = float(np.corrcoef(book[joint], r[joint])[0, 1])
    cl = {k: float(np.corrcoef(legs[k][joint], r[joint])[0, 1]) for k in legs}
    worst = max(cl, key=cl.get)
    gate("corr", cb <= MAX_CORR_BOOK and cl[worst] <= MAX_CORR_LEG,
         f"book {cb:+.2f}, max leg {worst} {cl[worst]:+.2f}", f"book <= +{MAX_CORR_BOOK}, each leg <= +{MAX_CORR_LEG} (negative passes)")
    bk, rr = book[joint], r[joint]
    how = "weight fitted to 2017" if weight is None else "weight fixed by --weight"
    if weight is None:
        grid = np.linspace(0, 3, 61) * bk.std() / max(rr.std(), 1e-12)
        pre = bk.index < SPLIT
        weight = float(max(grid, key=lambda w: sharpe((bk + w * rr)[pre])))
    s0, s1 = sharpe(bk[bk.index >= SPLIT]), sharpe((bk + weight * rr)[bk.index >= SPLIT])
    gate("goal", s1 - s0 >= MIN_SHARPE_GAIN,
         f"Hydra 2018+ {s0:.2f} -> {s1:.2f} at weight {weight:.3g}; P(5x) {p_goal(s0):.1%} -> {p_goal(s1):.1%}",
         f"Sharpe gain >= {MIN_SHARPE_GAIN}, {how}")
    failed = next((g["gate"] for g in gates if g["pass"] is False), None)
    verdict = f"FAIL at {failed}" if failed else ("INCOMPLETE" if any(g["pass"] is None for g in gates) else "PASS")
    return {"id": cid, "when": datetime.now().isoformat(timespec="seconds"), "verdict": verdict, "gates": gates,
            "weight": weight, "p5x": [p_goal(s0), p_goal(s1)]}


def record(res):
    with TRIALS.open("a") as f:
        f.write(json.dumps({"id": res["id"], "when": res["when"], "verdict": res["verdict"]}) + "\n")
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"candidates": []}
    entry = next((c for c in ledger["candidates"] if c["id"] == res["id"]), None)
    if entry is None:
        entry = {"id": res["id"], "name": res["id"], "status": "testing", "step": 9}
        ledger["candidates"].append(entry)
    entry["gates"] = res
    LEDGER.write_text(json.dumps(ledger, indent=1) + "\n")
    (ROOT / "docs" / "gates").mkdir(exist_ok=True)
    (ROOT / "docs" / "gates" / f"{res['id']}.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--weight", type=float)
    ap.add_argument("--stress-sharpe", type=float, help="Sharpe at 1.5x cost when no _stress.csv exists (cite it)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = judge(a.id, a.weight, a.stress_sharpe, 0 if a.dry_run else 1)
    for g in res["gates"]:
        mark = {True: "pass", False: "FAIL", None: "----"}[g["pass"]]
        print(f"  {mark}  {g['gate']:7s} {g['figure']:60s} ({g['rule']})")
    print(f"{res['id']}: {res['verdict']}")
    if not a.dry_run:
        record(res)
