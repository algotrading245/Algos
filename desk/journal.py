"""The desk record: append-only, one file a day (desk/journal/YYYY-MM-DD.jsonl, UTC dates). Every module logs here."""
import os

from desk import clocks, paths


def log(_kind, /, **data):
    t = clocks.now()
    row = {"t": t.isoformat(timespec="seconds"), "kind": _kind, "by": os.environ.get("AURUM_DESK_ROLE", "code")}
    row.update({("data_" + k if k in ("t", "kind") else k): v for k, v in data.items()})
    paths.append_jsonl(paths.JOURNAL / f"{t.date().isoformat()}.jsonl", row)
    return row


def day(date_str):
    return paths.read_jsonl(paths.JOURNAL / f"{date_str}.jsonl")


def recent(kinds=None, days=7):
    """Rows of the last `days` journal files, oldest first, optionally only these kinds."""
    files = sorted(paths.JOURNAL.glob("*.jsonl"))[-days:]
    out = []
    for f in files:
        for r in paths.read_jsonl(f):
            if kinds is None or r.get("kind") in kinds:
                out.append(r)
    return out
