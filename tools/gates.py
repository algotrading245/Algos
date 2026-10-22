"""The fixed gates every candidate leg must pass before it goes into an EA (pipeline step 2).  The thresholds are
constants in this file on purpose: an agent that builds a candidate may not change them, and the reviewer checks
that they were not changed (`git log -p tools/gates.py`).

Portfolio rule, approved by the owner 2026-10-22: a leg does not have to be strong on its own; it has to be real and
make the book better.  The book is tools/book_sim.py: every leg we trade at equal risk, weights set walk-forward.

A candidate is a daily return series (fraction of equity at the size it would trade at) in
marketdata/candidates/<id>.csv (columns day,r) with the same at 1.5x costs in <id>_stress.csv, or one of the
cached legs in marketdata/candidate_legs_daily.csv.gz.

    python tools/gates.py breakout --published https://...     # judge, log one trial, write the verdict
    python tools/gates.py volforecast_sizing --replaces hold   # an overlay: judged as a swap for leg(s) it re-sizes
    python tools/gates.py breakout --dry-run                   # judge only (the reviewer's run): nothing logged

Leg gates (is it real?):
  1 halves   Sharpe at the real cost >= 0.2 to 2017 and from 2018 (the leg's own history split at its middle
             instead when either side has under two years)
  2 costs    still profitable at 1.5x the cost (Sharpe > 0)
  3 corr     correlation with the book <= +0.30 and with each leg <= +0.30; a negative one passes (a hedge)
  4 belief   a reason to believe it is not luck: a published source (--published <url>, or "published" in the
             ledger entry), or the same parameters profitable on 3+ markets (<id>_markets.csv, one column a market,
             every column Sharpe > 0)
Book gates (does it help?):
  5 book     the walk-forward equal-risk book's Sharpe from 2018 rises by >= 0.03 with the leg in (with the leg(s)
             in --replaces out)
  6 dsr      Deflated Sharpe Ratio (Bailey, Lopez de Prado 2014) of the new book >= 0.90, N = every trial ever
             logged in docs/trials.jsonl plus the 47 counted before the log existed
The first failure names the verdict.  Profitable months with and without the leg are printed as information.
Nothing on or after the owner's holdout (tools/holdout.py) is used.
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
sys.path.insert(0, str(ROOT / "tools"))
import book_sim as B  # noqa: E402

CANDIDATES = ROOT / "marketdata" / "candidates"
TRIALS = ROOT / "docs" / "trials.jsonl"
LEDGER = ROOT / "docs" / "candidates.json"

SPLIT = "2018-01-01"
MIN_HALF_SHARPE = 0.2
MIN_HALF_DAYS = 504
MIN_STRESS_SHARPE = 0.0
MAX_CORR_BOOK = 0.30
MAX_CORR_LEG = 0.30
MIN_MARKETS = 3
MIN_BOOK_GAIN = 0.03
MIN_DSR = 0.90
TRIALS_BEFORE_LOG = 47
EULER = 0.5772156649

sharpe = B.sharpe


def trials_logged():
    """One per gates.py run, plus every rule a scan tried (tools/edge_scan.py logs its whole search as one line
    with "count": the number of rules it looked at, not only the survivors)."""
    if not TRIALS.exists():
        return 0
    return sum(int(json.loads(line).get("count", 1)) for line in TRIALS.open(encoding="utf-8") if line.strip())


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


def ledger_entry(cid):
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"candidates": []}
    return next((c for c in ledger["candidates"] if c["id"] == cid), {})


def markets(cid):
    """Sharpe of the same parameters on each market, from <id>_markets.csv, or {}."""
    f = CANDIDATES / f"{cid}_markets.csv"
    if not f.exists():
        return {}
    m = B.clip(pd.read_csv(f, index_col=0, parse_dates=True))
    return {k: sharpe(m[k]) for k in m}


def profitable_months(book):
    m = B.months(B.risk_layer(book))
    m = m[m.index >= pd.Period(SPLIT, "M")]
    return float((m > 0).mean())


def judge(cid, stress_sharpe=None, n_extra=1, published=None, replaces=()):
    r, stress = B.series(cid)
    if r is None:
        sys.exit(f"no series for {cid}: write {CANDIDATES / (cid + '.csv')} (columns day,r)")
    r = B.clip(r)
    first = r.first_valid_index()
    gates = []

    def gate(name, ok, figure, rule):
        gates.append({"gate": name, "pass": None if ok is None else bool(ok), "figure": figure, "rule": rule})

    # 1 halves, on the leg's own history
    own = r[r.index >= first].fillna(0.0)
    pre, post = own[own.index < SPLIT], own[own.index >= SPLIT]
    if len(pre) < MIN_HALF_DAYS or len(post) < MIN_HALF_DAYS:
        mid = own.index[len(own) // 2]
        pre, post, where = own[own.index < mid], own[own.index >= mid], f"split at its middle {mid.date()}"
    else:
        where = "to 2017 / from 2018"
    a, b = sharpe(pre), sharpe(post)
    gate("halves", a >= MIN_HALF_SHARPE and b >= MIN_HALF_SHARPE, f"{a:.2f} / {b:.2f} ({where})",
         f">= {MIN_HALF_SHARPE} each half")

    # 2 costs (the stress file, else --stress-sharpe, else the figure cited in the ledger entry)
    if stress is not None:
        stress_sharpe = sharpe(B.clip(stress))
    elif stress_sharpe is None:
        stress_sharpe = ledger_entry(cid).get("stress_sharpe")
    gate("costs", None if stress_sharpe is None else stress_sharpe > MIN_STRESS_SHARPE,
         "missing" if stress_sharpe is None else f"{stress_sharpe:.2f}", f"> {MIN_STRESS_SHARPE} at 1.5x cost")

    # the book without the candidate (it may already be in it) and with it
    base_legs = B.legs(without=[cid])
    new_legs = B.legs(without=[cid, *replaces], extra={cid: r})
    base, _ = B.combine(base_legs)
    new, _ = B.combine(new_legs)

    # 3 corr, against what stays in the book
    others = [k for k in base_legs if k not in replaces]
    rest, _ = B.combine(base_legs[others]) if replaces else (base, None)
    joint = rest.index.intersection(own.index)
    cb = float(np.corrcoef(rest[joint], own[joint])[0, 1])
    lf = base_legs[others].loc[joint]
    cl = {k: float(np.corrcoef(lf[k].fillna(0.0), own[joint])[0, 1]) for k in lf if lf[k].notna().sum() > 60}
    worst = max(cl, key=cl.get)
    gate("corr", cb <= MAX_CORR_BOOK and cl[worst] <= MAX_CORR_LEG,
         f"book {cb:+.2f}, max leg {worst} {cl[worst]:+.2f}",
         f"book <= +{MAX_CORR_BOOK}, each leg <= +{MAX_CORR_LEG} (negative passes)")

    # 4 belief
    published = published or ledger_entry(cid).get("published")
    mk = markets(cid)
    good = [k for k, s in mk.items() if s > 0]
    ok = bool(published) or (len(mk) >= MIN_MARKETS and len(good) == len(mk))
    why = (f"published {published}" if published else
           f"{len(good)}/{len(mk)} markets profitable" if mk else "no source, no other markets")
    gate("belief", ok, why, f"a published source, or the same parameters profitable on all of {MIN_MARKETS}+ markets")

    # 5 book
    s0, s1 = sharpe(base[base.index >= SPLIT]), sharpe(new[new.index >= SPLIT])
    swap = f" replacing {','.join(replaces)}" if replaces else ""
    gate("book", s1 - s0 >= MIN_BOOK_GAIN, f"book 2018+ {s0:.2f} -> {s1:.2f}{swap}",
         f"gain >= {MIN_BOOK_GAIN}, equal risk, weights walk-forward")

    # 6 dsr of the new book
    n = TRIALS_BEFORE_LOG + trials_logged() + n_extra
    p, sr0 = deflated(new, n)
    gate("dsr", p >= MIN_DSR, f"{p:.3f} (book, N={n}, luck bar {sr0:.2f})", f">= {MIN_DSR}")

    failed = next((g["gate"] for g in gates if g["pass"] is False), None)
    verdict = f"FAIL at {failed}" if failed else ("INCOMPLETE" if any(g["pass"] is None for g in gates) else "PASS")
    return {"id": cid, "when": datetime.now().isoformat(timespec="seconds"), "verdict": verdict, "gates": gates,
            "replaces": list(replaces), "published": published,
            "profitable_months_2018": [round(profitable_months(base), 3), round(profitable_months(new), 3)]}


def record(res):
    with TRIALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": res["id"], "when": res["when"], "verdict": res["verdict"]}) + "\n")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"candidates": []}
    entry = next((c for c in ledger["candidates"] if c["id"] == res["id"]), None)
    if entry is None:
        entry = {"id": res["id"], "name": res["id"], "status": "testing", "step": 2}
        ledger["candidates"].append(entry)
    if res["verdict"].startswith("FAIL") and entry.get("status") == "testing":
        # a FAIL never leaves a "testing" entry behind (it used to, and the worker then added a second one)
        entry.update(status="rejected", step=2, reason=entry.get("reason") or f"gates: {res['verdict']}",
                     tag=res["verdict"].split()[-1])
    if res.get("published"):
        entry["published"] = res["published"]
    entry["gates"] = res
    LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "docs" / "gates").mkdir(exist_ok=True)
    (ROOT / "docs" / "gates" / f"{res['id']}.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--stress-sharpe", type=float, help="Sharpe at 1.5x cost when no _stress.csv exists (cite it)")
    ap.add_argument("--published", help="link to the paper or write-up the rule comes from")
    ap.add_argument("--replaces", default="", help="leg(s) an overlay re-sizes, comma list")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = judge(a.id, a.stress_sharpe, 0 if a.dry_run else 1, a.published,
                [k for k in a.replaces.split(",") if k])
    for g in res["gates"]:
        mark = {True: "pass", False: "FAIL", None: "----"}[g["pass"]]
        print(f"  {mark}  {g['gate']:7s} {g['figure']:60s} ({g['rule']})")
    pm = res["profitable_months_2018"]
    print(f"  info  profitable months 2018+ {pm[0]:.0%} -> {pm[1]:.0%}")
    print(f"{res['id']}: {res['verdict']}")
    if not a.dry_run:
        record(res)
