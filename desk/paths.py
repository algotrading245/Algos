"""Where the desk keeps things, and the small file helpers every desk module uses.

desk/            code, risk.json (owner-only), config.json, journal/, playbooks/, edges/, memory/ (committed)
logs/desk/       runtime state, run transcripts, the KILL file (out of git)
"""
import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT / "desk"
LOGS = Path(os.environ.get("AURUM_DESK_LOGS", ROOT / "logs" / "desk"))
STATE = LOGS / "state"
RUNS = LOGS / "runs"
JOURNAL = Path(os.environ.get("AURUM_DESK_JOURNAL", DESK / "journal"))
MEMORY = Path(os.environ.get("AURUM_DESK_MEMORY", DESK / "memory"))
PLAYBOOKS = Path(os.environ.get("AURUM_DESK_PLAYBOOKS", DESK / "playbooks"))
INBOX = Path(os.environ.get("AURUM_DESK_INBOX", DESK / "inbox"))
REPORTS = Path(os.environ.get("AURUM_DESK_REPORTS", DESK / "reports"))
KILL = LOGS / "KILL"
RISK = Path(os.environ.get("AURUM_DESK_RISK", DESK / "risk.json"))
CONFIG = Path(os.environ.get("AURUM_DESK_CONFIG", DESK / "config.json"))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, obj):
    """Atomic write: a reader never sees half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)
    for i in range(3):  # Windows refuses the replace while a reader (the dashboard, an editor) holds the file
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 2:
                os.unlink(tmp)
                raise
            time.sleep(0.2)


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return out


def risk():
    return read_json(RISK, {})


def config():
    return read_json(CONFIG, {})
