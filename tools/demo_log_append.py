"""Appends the monitor's draft entry to docs/demo_log.md, then deletes the draft (owner 2026-10-27).

The monitor never writes docs/demo_log.md itself (the settings deny it): it writes the day's entry to
docs/demo_log_entry.md and runs this, so the log only ever grows and past entries keep their wrap.

    python tools/demo_log_append.py [DRAFT]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "docs" / "demo_log.md"
DRAFT = ROOT / "docs" / "demo_log_entry.md"


def append(draft=DRAFT):
    draft = Path(draft)
    if not draft.exists():
        return f"no draft at {draft}"
    entry = draft.read_text(encoding="utf-8").strip()
    if not entry:
        return f"the draft {draft.name} is empty; nothing appended"
    old = LOG.read_text(encoding="utf-8") if LOG.exists() else "# Demo log\n"
    sep = "" if old.endswith("\n\n") else ("\n" if old.endswith("\n") else "\n\n")
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        if not LOG.stat().st_size:
            f.write("# Demo log\n")
        f.write(sep + entry + "\n")
    draft.unlink()
    return f"appended {len(entry.splitlines())} lines to docs/demo_log.md"


if __name__ == "__main__":
    print(append(*sys.argv[1:2]))
