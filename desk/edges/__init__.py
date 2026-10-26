"""The open edge library: every registered edge, legs and benchmark alike (DESIGN.md section 6).

Pods add edges as single files in desk/edges/new/ (one @edge per file, pod set to the author). They load here; a file
that fails to import is journaled and skipped, so one bad edge never stops the clock.

A new edge is computation on the bars it is given, nothing else. It runs inside the desk's own process, so before it
is imported its source is checked: imports only from numpy, pandas, math, datetime, statistics and the helpers of
desk.edges.base, no names or attributes that reach files, the shell, the network or the interpreter's insides, and
it may not replace an edge that is already registered or call itself a benchmark.
"""
import ast
import importlib.util

from desk.edges import benchmark, legs  # noqa: F401  (registers the edges)
from desk.edges.base import EDGES, describe, get, hist_bars, run  # noqa: F401
from desk import paths

NEW = paths.DESK / "edges" / "new"
BROKEN = {}
BUILTIN = set(EDGES)
OWNER = {}  # edge name -> the new/ file that registered it

MODULES = {"numpy", "pandas", "math", "datetime", "statistics"}
BASE = "desk.edges.base"
BASE_OK = {"DAY", "ZONES", "HOLDOUT", "at", "atr", "bar_before", "close_sig", "date_of", "day_of", "days", "edge",
           "last_weekday_of_month", "rsi", "sig", "sma", "spx", "std", "tf_secs", "to_utc", "tod", "trade_days",
           "weekday"}
NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
         "delattr", "input", "breakpoint", "memoryview", "help", "exit", "quit", "EDGES"}
ATTRS = {"save", "savez", "savez_compressed", "savetxt", "load", "loadtxt", "fromfile", "tofile", "genfromtxt",
         "memmap", "open_memmap", "ctypeslib", "lib", "io", "f2py", "testing", "system", "popen", "eval", "query",
         "format", "format_map", "pipe"}
TO_OK = {"to_datetime", "to_numeric", "to_numpy", "to_timedelta", "to_list", "to_dict", "to_pydatetime"}


def check(src):
    """The reasons a new edge's source may not load (empty when it may)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"syntax: {e}"]
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += [f"import {a.name}" for a in n.names if a.name.split(".")[0] not in MODULES]
        elif isinstance(n, ast.ImportFrom):
            if n.level or not n.module:
                bad.append("relative import")
            elif n.module == BASE:
                bad += [f"{BASE}.{a.name}" for a in n.names if a.name not in BASE_OK]
            elif n.module.split(".")[0] not in MODULES:
                bad.append(f"from {n.module} import")
        elif isinstance(n, ast.Name) and (n.id in NAMES or n.id.startswith("__")):
            bad.append(n.id)
        elif isinstance(n, ast.Attribute) and (n.attr.startswith("_") or n.attr in ATTRS or n.attr.startswith("read_")
                                               or n.attr.startswith("to_") and n.attr not in TO_OK):
            bad.append(f".{n.attr}")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            bad.append(type(n).__name__.lower())
    return sorted(set(bad))


def _load(f):
    """Import one new/ file; refuse it if it replaced an edge it does not own or registered a benchmark."""
    before = dict(EDGES)
    spec = importlib.util.spec_from_file_location(f"desk.edges.new.{f.stem}", f)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    added = [k for k, v in EDGES.items() if before.get(k) is not v]
    clash = [k for k in added if k in BUILTIN or OWNER.get(k, f.name) != f.name]
    bench = [k for k in added if EDGES[k].get("kind") == "benchmark"]
    if clash or bench:
        EDGES.clear()
        EDGES.update(before)
        raise ValueError(f"replaces {', '.join(clash)}" if clash else f"benchmark kind on {', '.join(bench)}")
    for k in added:
        OWNER[k] = f.name


def load_new():
    for f in sorted(NEW.glob("*.py")) if NEW.exists() else []:
        if f.name.startswith("_"):
            continue
        bad = check(f.read_text(encoding="utf-8"))
        if bad:
            BROKEN[f.name] = "not allowed in an edge: " + ", ".join(bad)
            continue
        try:
            _load(f)
            BROKEN.pop(f.name, None)
        except Exception as e:  # noqa: BLE001  an agent's file must not break the desk
            BROKEN[f.name] = f"{type(e).__name__}: {e}"
    return BROKEN


load_new()
