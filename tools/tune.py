"""Small-grid tuning of one desk edge: a plateau, not a peak (owner 2026-10-31).

    python tools/tune.py EDGE k=1.5,2,2.5,3 hold=20,40,60 [markets=EURUSD,XAUUSD] [stress=1.5] [split=2018-01-01]

The AI proposes the structural change and the 2-3 parameters worth moving; this code tests them, so a search never
turns into hand-picking. Rules it enforces:
- At most 3 parameters and 5 values each (125 runs). A bigger grid is refused: the mass grid of 2026-10-23 raised the
  Deflated Sharpe N and crowded out ideas (tools/spec_factory.py).
- One parameter set for every market: each combination is scored on the pooled monthly R of all the edge's markets.
- A plateau, not a peak: a combination scores the WORST Sharpe of itself and its grid neighbours (one step on one
  parameter), so a lone spike surrounded by losers is never chosen.
- Walk-forward: for each year from the 6th on, choose on all years before it, score the next year; the stitched
  out-of-sample years are compared with the edge's defaults over the same years.
- The gates' split: the pick made on data before `split` (2018-01-01) is the one reported for the gates, scored from
  the split on at 1x and at `stress` x the real cost.
- Every combination is a trial: one line in docs/trials.jsonl with "count" = the grid size, so gates.trials_logged
  and the Deflated Sharpe bar rise with it.
Data stops before the holdout (base.hist_bars cuts 2025-10-13 off). Writes desk/reports/tune_<edge>.md.
"""
import datetime as dt
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desk import edges, paths, sandbox  # noqa: E402
from desk.edges import base  # noqa: E402

TRIALS = ROOT / "docs" / "trials.jsonl"
REPORTS = ROOT / "desk" / "reports"
MAX_PARAMS, MAX_VALUES = 3, 5
MIN_TRAIN_YEARS = 5


def monthly(trades):
    """Pooled R per calendar month (exit month), as a Series."""
    if not trades:
        return pd.Series(dtype=float)
    s = pd.Series([x["r"] for x in trades],
                  index=pd.to_datetime([x["out"] for x in trades], unit="s").to_period("M"))
    return s.groupby(level=0).sum()


def sharpe(m, lo=None, hi=None):
    """Annualised Sharpe of monthly R between two periods (months with no trade count as 0)."""
    if m.empty:
        return float("nan")
    full = pd.period_range(lo or m.index.min(), hi or m.index.max(), freq="M")
    x = m.reindex(full, fill_value=0.0).values
    return float(x.mean() / x.std() * np.sqrt(12)) if len(x) > 2 and x.std() > 0 else float("nan")


def parse_grid(argv):
    grid, opts = {}, {}
    for a in argv:
        k, v = a.split("=", 1)
        if k in ("markets", "stress", "split"):
            opts[k] = v
        else:
            grid[k] = [json.loads(x) for x in v.split(",")]
    if not grid or len(grid) > MAX_PARAMS or any(len(v) > MAX_VALUES for v in grid.values()):
        sys.exit(f"grid: 1-{MAX_PARAMS} parameters, at most {MAX_VALUES} values each (got {grid})")
    return grid, opts


def run(name, grid, markets, stress, cfg):
    """{combo index: (monthly R at 1x, monthly R at stress)} over all markets with one parameter set."""
    e = edges.get(name)
    data = {}
    for m in markets:
        spec = cfg["instruments"].get(m, {})
        if spec.get("cost") is None:
            print(f"skip {m}: no cost in config.json")
            continue
        df = base.hist_bars(m, e["tf"], cfg)
        data[m] = (df, sandbox.context(e, m, cfg), sandbox.costs(df, spec["cost"], spec.get("class")))
    keys = list(grid)
    combos = list(itertools.product(*(range(len(grid[k])) for k in keys)))
    out = {}
    for n, idx in enumerate(combos, 1):
        p = {k: grid[k][i] for k, i in zip(keys, idx)}
        t1, t2 = [], []
        for df, ctx, cost in data.values():
            sigs = edges.run(name, df, p, ctx)
            t1 += sandbox.simulate(df, sigs, cost)
            t2 += sandbox.simulate(df, sigs, cost * stress)
        out[idx] = (monthly(t1), monthly(t2), len(t1))
        print(f"  {n}/{len(combos)} {p}: {len(t1)} trades", flush=True)
    return keys, out, list(data)


def neighbours(idx, sizes):
    for d in range(len(idx)):
        for step in (-1, 1):
            j = idx[d] + step
            if 0 <= j < sizes[d]:
                yield idx[:d] + (j,) + idx[d + 1:]


def plateau(scores, sizes):
    """Each combination's worst Sharpe over itself and its neighbours."""
    return {i: min([s] + [scores[n] for n in neighbours(i, sizes)]) for i, s in scores.items()}


def pick(res, sizes, lo, hi):
    """The plateau's best combination on months lo..hi."""
    sc = {i: np.nan_to_num(sharpe(v[0][(v[0].index >= lo) & (v[0].index <= hi)], lo, hi), nan=-9) for i, v in res.items()}
    pl = plateau(sc, sizes)
    best = max(pl, key=pl.get)
    return best, sc, pl


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        sys.exit(__doc__)
    name, (grid, opts) = argv[0], parse_grid(argv[1:])
    cfg = paths.config()
    e = edges.get(name)
    markets = opts["markets"].split(",") if "markets" in opts else e["markets"]
    stress = float(opts.get("stress", 1.5))
    split = pd.Period(opts.get("split", "2018-01-01"), freq="M")
    unknown = set(grid) - set(e["defaults"])
    if unknown:
        sys.exit(f"{name} has no parameter {sorted(unknown)}; its defaults are {e['defaults']}")
    print(f"tune {name} on {len(markets)} markets, grid {grid}, stress {stress}x")
    keys, res, used = run(name, grid, markets, stress, cfg)
    sizes = [len(grid[k]) for k in keys]
    label = lambda i: ", ".join(f"{k}={grid[k][j]}" for k, j in zip(keys, i))  # noqa: E731
    first = min(v[0].index.min() for v in res.values() if not v[0].empty)
    last = max(v[0].index.max() for v in res.values() if not v[0].empty)

    # the defaults as a combination of the grid, when they sit on it (the walk-forward's comparison)
    dflt = tuple(grid[k].index(e["defaults"][k]) if e["defaults"][k] in grid[k] else None for k in keys)
    if None in dflt:
        dflt = None

    # 1. the gates' pick: plateau on months before the split, scored from the split on
    best, sc, pl = pick(res, sizes, first, split - 1)
    after = lambda i, k=0: sharpe(res[i][k][res[i][k].index >= split], split, last)  # noqa: E731

    # 2. walk-forward by year
    wf, rows = [], []
    for y in range(first.year + MIN_TRAIN_YEARS, last.year + 1):
        lo, hi = pd.Period(f"{y}-01", "M"), min(pd.Period(f"{y}-12", "M"), last)
        b, _, _ = pick(res, sizes, first, lo - 1)
        m = res[b][0]
        wf.append(m[(m.index >= lo) & (m.index <= hi)].reindex(pd.period_range(lo, hi, freq="M"), fill_value=0.0))
        d = res[dflt][0] if dflt else None
        rows.append(f"| {y} | {label(b)} | {wf[-1].sum():+.1f} | "
                    + (f"{d[(d.index >= lo) & (d.index <= hi)].sum():+.1f} |" if dflt else "- |"))
    oos = pd.concat(wf) if wf else pd.Series(dtype=float)
    oos_sr = float(oos.mean() / oos.std() * np.sqrt(12)) if len(oos) > 2 and oos.std() > 0 else float("nan")
    d_sr = sharpe(res[dflt][0][res[dflt][0].index >= oos.index.min()], oos.index.min(), last) if dflt and wf else None

    stamp = dt.datetime.now().isoformat(timespec="seconds")
    verdict = (f"pick {label(best)}: plateau SR<{split} {pl[best]:.2f}, SR>={split} {after(best):.2f}, "
               f"{stress}x {after(best, 1):.2f}; walk-forward SR {oos_sr:.2f}"
               + (f" vs defaults {d_sr:.2f}" if d_sr is not None else ""))
    with TRIALS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": f"tune:{name}:{'+'.join(keys)}", "when": stamp, "verdict": verdict,
                            "count": len(res)}) + "\n")

    top = sorted(res, key=lambda i: -pl[i])[:10]
    lines = [f"# Tuning {name} ({stamp[:10]})", "",
             f"Markets (one parameter set): {', '.join(used)}. Grid: {json.dumps(grid)} = {len(res)} combinations, "
             f"logged as {len(res)} trials in docs/trials.jsonl. Data {first} to {last} (before the holdout). "
             f"Score: annualised Sharpe of pooled monthly R. Plateau = worst of a combination and its neighbours.", "",
             f"**Pick (chosen on data before {split}):** {label(best)}", "",
             f"- Sharpe before {split}: own {sc[best]:.2f}, plateau {pl[best]:.2f}",
             f"- Sharpe from {split}: {after(best):.2f} at 1x cost, {after(best, 1):.2f} at {stress}x",
             f"- Walk-forward (re-chosen each year on the years before it): Sharpe {oos_sr:.2f} over {len(oos)} months"
             + (f"; the defaults {e['defaults']} over the same months: {d_sr:.2f}" if d_sr is not None else
                "; the defaults are not on the grid, so no comparison"), "",
             "Read it: worth building only if the pick holds from the split on at the stress cost AND the walk-forward "
             "beats the defaults. A pick that changes every year means there is no plateau: keep the defaults.", "",
             "## Top 10 by plateau (before the split)", "",
             "| params | own SR | plateau SR | SR from split | stress SR | trades |", "|---|---|---|---|---|---|"]
    lines += [f"| {label(i)} | {sc[i]:.2f} | {pl[i]:.2f} | {after(i):.2f} | {after(i, 1):.2f} | {res[i][2]} |" for i in top]
    lines += ["", "## Walk-forward", "", "| test year | chosen on the years before | R that year | defaults R |",
              "|---|---|---|---|"] + rows
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"tune_{name}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(verdict)
    print(f"wrote {out}; logged {len(res)} trials to {TRIALS}")


if __name__ == "__main__":
    main()
