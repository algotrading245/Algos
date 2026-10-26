"""The open edge library: every registered edge, legs and benchmark alike (DESIGN.md section 6).

Pods add edges as single files in desk/edges/new/ (one @edge per file, pod set to the author). They load here; a file
that fails to import is journaled and skipped, so one bad edge never stops the clock.
"""
import importlib.util

from desk.edges import benchmark, legs  # noqa: F401  (registers the edges)
from desk.edges.base import EDGES, describe, get, hist_bars, run  # noqa: F401
from desk import paths

NEW = paths.DESK / "edges" / "new"
BROKEN = {}


def load_new():
    for f in sorted(NEW.glob("*.py")) if NEW.exists() else []:
        if f.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"desk.edges.new.{f.stem}", f)
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
            BROKEN.pop(f.name, None)
        except Exception as e:  # noqa: BLE001  an agent's file must not break the desk
            BROKEN[f.name] = f"{type(e).__name__}: {e}"
    return BROKEN


load_new()
