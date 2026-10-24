"""Builds the pipeline dashboard: dashboard/index.html (static page) and dashboard/data.js (everything it shows), plus
docs/candidates.md, the readable form of the ledger.  Open dashboard/index.html in a browser, no server needed.
tools/dashboard_live.py (started by the keeper) writes dashboard/live.js each second for the Live tab and reruns this
script every minute; the page reloads both.

    python tools/dashboard.py

Reads docs/pipeline.json, docs/ideas/queue.jsonl (the funnel), docs/candidates.json, docs/gates/*.json, docs/prop_routes.json, docs/demo_log.md,
.claude/agents/*.md, backtests/*/ (result.json, summary.md, job.json) and, when the market data is there, the Hydra
legs for the book's Sharpe with the candidate legs added.  Nothing private is copied: job.json gives only the test
settings (no paths), and demo_check drops any line that could hold a login or account number.
"""
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "dashboard"
sys.path.insert(0, str(ROOT / "tools"))
EXPERT_TO_ID = {"AurumBreakout": "breakout", "AurumNoise": "noise"}
JOB_KEYS = ("Expert", "Symbol", "From", "To", "Deposit", "Leverage", "Period", "Set", "Started")


def load_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def expected_for(ledger, expert, symbol):
    cid = EXPERT_TO_ID.get(expert)
    c = next((c for c in ledger["candidates"] if c["id"] == cid), None)
    if not c or "expected_tester" not in c:
        return None
    exp = c["expected_tester"]
    exp = exp if isinstance(exp, list) else [exp]
    return next((e for e in exp if e.get("symbol") == symbol), None)


def runs(ledger):
    out = []
    for d in sorted((ROOT / "backtests").iterdir(), reverse=True):
        if not d.is_dir():
            continue
        job = load_json(d / "job.json", {}) if (d / "job.json").exists() else {}
        res = load_json(d / "result.json")
        md = (d / "summary.md").read_text(encoding="utf-8") if (d / "summary.md").exists() else None
        if not res and not md:
            out.append({"name": d.name, "state": "no report (run killed or still going)"})
            continue
        run = {"name": d.name, "job": {k: job[k] for k in JOB_KEYS if k in job}, "summary": md, "state": "done"}
        if res:
            run["result"] = {k: v for k, v in res.items() if k != "report"}
            run["expected"] = expected_for(ledger, res.get("expert") or job.get("Expert"), res.get("symbol"))
        out.append(run)
    return out


def budget_status():
    """This week's agent spend (tools/autopilot/budget.py), or None when there is no usage log yet."""
    try:
        sys.path.insert(0, str(ROOT / "tools" / "autopilot"))
        import budget
        return budget.status()
    except Exception:
        return None


def agents():
    out = [{"name": "judge", "model": "opus", "tools": "all", "steps": "5",
            "description": "Judges each Strategy Tester result against the Python figures, has the reviewer check the "
                           "EA change and records the verdict on the queue item; handles demo orders and ALERTs. "
                           "Prompt: tools/autopilot/prompts/judge.md. Asks the owner before anything live."}]
    for f in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        m = re.match(r"---\s*\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
        if not m:
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
        steps = re.search(r"[Ss]teps? ([\d ,and-]+)", meta.get("description", ""))
        out.append({"name": meta.get("name", f.stem), "model": meta.get("model", "?"), "tools": meta.get("tools", ""),
                    "description": meta.get("description", ""), "steps": steps.group(1).strip(" ,.") if steps else ""})
    return out


def funnel():
    """The one idea queue (docs/ideas/queue.jsonl): how many ideas at each status and from each source, newest first."""
    items = []
    f = DOCS / "ideas" / "queue.jsonl"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            try:
                items.append(json.loads(ln))
            except ValueError:
                pass
    by_status, by_source = {}, {}
    for x in items:
        by_status[x.get("status", "?")] = by_status.get(x.get("status", "?"), 0) + 1
        by_source[x.get("source", "?")] = by_source.get(x.get("source", "?"), 0) + 1
    recent = [{k: x.get(k) for k in ("id", "source", "title", "status", "added", "verdict")} for x in items[::-1][:30]]
    return {"total": len(items), "by_status": by_status, "by_source": by_source, "recent": recent}


def book(ledger):
    """The equal-risk book (tools/book_sim.py, docs/book.json): its legs' weights, the book's Sharpe from 2018 without
    and with each candidate leg that passed the gates, and the headline numbers (profitable months, FTMO, payout)."""
    try:
        f = ROOT / "docs" / "book.json"
        out = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        sharpe = {"Hydra book": out.get("backtest", {}).get("sharpe_2018")}
        for c in ledger["candidates"]:
            g = c.get("gates") or {}
            fig = next((x["figure"] for x in g.get("gates", []) if x.get("gate") == "book"), "")
            if g.get("verdict") == "PASS" and "->" in fig:
                a, b = fig.split("2018+ ")[-1].split(" -> ")
                sharpe["Hydra book"] = sharpe["Hydra book"] or float(a)
                sharpe[f"+ {c['id']}"] = float(b.split()[0])
        out.update(weights={k: v["weight"] for k, v in out.get("legs", {}).items()}, since="2018-01-01",
                   sharpe={k: v for k, v in sharpe.items() if v is not None})
        return out if out.get("legs") else {"error": "run python tools/book_sim.py to write docs/book.json"}
    except Exception as e:  # the page still works without it
        return {"error": f"book figures unavailable: {e}"}


def demo():
    try:
        import demo_check
        today = demo_check.check(date.today())
    except Exception as e:
        today = {"error": str(e)}
    log = DOCS / "demo_log.md"
    return {"today": today, "log": log.read_text(encoding="utf-8") if log.exists() else None}


def candidates_md(ledger):
    lines = ["# Candidate ledger", "", "Generated from `docs/candidates.json` by `python tools/dashboard.py`; edit the "
             "JSON, not this file.", ""]
    for c in ledger["candidates"]:
        lines += [f"## {c['name']} (`{c['id']}`)", "",
                  f"Status **{c['status']}**, pipeline step {c['step']} of 5. Source: {c.get('source', '-')}.", "",
                  c.get("summary", ""), ""]
        g = c.get("gates")
        if g:
            lines += [f"Gates ({g['when'][:10]}{', dry run' if g.get('dry_run') else ''}): **{g['verdict']}**", "",
                      "| Gate | Result | Figure | Rule |", "|---|---|---|---|"]
            lines += [f"| {x['gate']} | {'pass' if x['pass'] else 'FAIL' if x['pass'] is False else '-'} | "
                      f"{x['figure']} | {x['rule']} |" for x in g["gates"]]
            lines.append("")
        for t in c.get("tester", []):
            lines += [f"Strategy Tester ({t['run']}): {t['trades']} trades, {t['win_rate']}% winners, PF "
                      f"{t['profit_factor']}, {t['return_pct']:+}%, max equity drawdown {t['eq_dd_max_pct']}% - "
                      f"{t['verdict']}.", ""]
        if c.get("notes"):
            lines += [f"Notes: {c['notes']}", ""]
    lines += ["## Rejected families", "", "| Family | Examples | Why |", "|---|---|---|"]
    lines += [f"| {r['family']} | {r['examples']} | {r['why']} |" for r in ledger.get("rejected", [])]
    return "\n".join(lines) + "\n"


def main():
    ledger = load_json(DOCS / "candidates.json", {"candidates": [], "rejected": []})
    gates_dir = DOCS / "gates"
    data = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "pipeline": load_json(DOCS / "pipeline.json"),
        "ledger": ledger,
        "gates": {p.stem: load_json(p) for p in sorted(gates_dir.glob("*.json"))} if gates_dir.exists() else {},
        "trials": sum(1 for _ in (DOCS / "trials.jsonl").open()) if (DOCS / "trials.jsonl").exists() else 0,
        "props": load_json(DOCS / "prop_routes.json"),
        "runs": runs(ledger),
        "agents": agents(),
        "budget": budget_status(),
        "book": book(ledger),
        "demo": demo(),
        "funnel": funnel(),
    }
    OUT.mkdir(exist_ok=True)
    tmp = OUT / "data.js.tmp"                                       # whole file or nothing: the live page reloads it
    tmp.write_text("window.AURUM = " + json.dumps(data, indent=1) + ";\n", encoding="utf-8")
    os.replace(tmp, OUT / "data.js")
    (OUT / "index.html").write_text(PAGE, encoding="utf-8")
    (DOCS / "candidates.md").write_text(candidates_md(ledger), encoding="utf-8")
    b = data["book"].get("sharpe", {})
    print(f"dashboard/index.html: {len(data['runs'])} runs, {len(ledger['candidates'])} candidates, book {b}")


PAGE = (Path(__file__).with_name("dashboard_page.html")).read_text(encoding="utf-8") \
    if (Path(__file__).with_name("dashboard_page.html")).exists() else ""

if __name__ == "__main__":
    if not PAGE:
        sys.exit("tools/dashboard_page.html is missing")
    main()
