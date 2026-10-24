"""Free pre-screen before the builder (owner 2026-10-24, change 6): obvious failures never reach a builder run.

A finder may give a queue item a "screen" field: a simple daily-rule or session proxy of the idea in the idea engine's
spec format (docs/ideas/specs/README.md), e.g. {"rule": "meanrev", "symbols": ["SPXUSD"], "side": "long",
"when": {"trend": "up"}} or {"symbols": ["XAUUSD"], "entry": ["03:00"], "hold": [2, 4]}. The relay runs this script
before it starts a builder. For each "new" item with a screen and no "screened" mark, the engine tests the proxy at
real costs (best variant picked before 2018, judged from 2018 to the holdout):
  - a Sharpe under the gate's 0.2 in either half, or no variant with enough trades: the item is set to "rejected"
    with the figures in "result" (no builder run);
  - otherwise it is marked "screened" and waits for the builder as before.
A proxy the engine cannot run (bad spec, missing data) only gets a note; the builder still takes the item.
Every variant tried is logged as a DSR trial in docs/trials.jsonl. Items with no screen are left alone.

    python tools/prescreen.py             # screen and write
    python tools/prescreen.py --dry-run   # print the verdicts, write nothing
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

QUEUE = ROOT / "docs" / "ideas" / "queue.jsonl"
TRIALS = ROOT / "docs" / "trials.jsonl"                             # the DSR trial log (tools/gates.py)
HALF_MIN = 0.2                                                      # the gate's Sharpe floor in each half
DRY = "--dry-run" in sys.argv


def todo(item):
    return (isinstance(item, dict) and item.get("status") == "new" and item.get("source") != "data"
            and isinstance(item.get("screen"), dict) and "screened" not in item)


def main():
    raw = QUEUE.read_text(encoding="utf-8").splitlines()
    items = []
    for line in raw:
        try:
            items.append(json.loads(line) if line.strip() else None)
        except ValueError:
            items.append(None)
    picks = [i for i, it in enumerate(items) if todo(it)]
    if not picks:
        return
    import idea_engine as E                                         # slow (pandas, prices): only when needed
    G = E.Grid()
    when = datetime.now().isoformat(timespec="seconds")
    trials = []
    for i in picks:
        it = items[i]
        spec = dict(it["screen"])
        spec.setdefault("id", f"screen_{it['id']}")
        spec.setdefault("side", "both")
        try:
            best, tried, note = (E.test_rule if "rule" in spec else E.test_spec)(G, spec)
        except Exception as e:                                      # a broken proxy must not stop the relay
            best, tried, note = None, 0, f"{type(e).__name__}: {e}"
        if tried == 0:
            it["screened"] = f"not run: {note}"[:300]
            print(f"{it['id']}: proxy not run ({note[:120]}); left for the builder")
        else:
            pre = (best or {}).get("sharpe_pre", 0.0)
            post = (best or {}).get("sharpe_post", 0.0)
            fig = f"Sharpe pre-2018 {pre:.2f} / from 2018 {post:.2f} on {tried} variants"
            if best is None or min(pre, post) < HALF_MIN:
                it["status"] = "rejected"
                it["result"] = f"prescreen: {note or fig} (simple-rule proxy, gate needs {HALF_MIN} in each half); no builder run"
                it["screened"] = "fail"
                print(f"{it['id']}: REJECTED, {note or fig}")
            else:
                it["screened"] = f"pass, {fig}"
                print(f"{it['id']}: passed, {fig}; left for the builder")
            trials.append({"id": f"prescreen:{it['id']}", "when": when,
                           "verdict": "SCREEN_FAIL" if it["status"] == "rejected" else "SCREEN_PASS", "count": tried})
        raw[i] = json.dumps(it, ensure_ascii=False)
    if DRY:
        return
    QUEUE.write_text("\n".join(raw) + "\n", encoding="utf-8")     # only the screened lines change
    if trials:
        with TRIALS.open("a") as f:
            for t in trials:
                f.write(json.dumps(t) + "\n")


if __name__ == "__main__":
    main()
