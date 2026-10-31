"""Every desk module reads its paths at import, so the env vars point into a temp dir before any desk import."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="desk_test_"))
for name in ("journal", "memory", "inbox", "reports", "playbooks", "logs"):
    (TMP / name).mkdir()
shutil.copy(ROOT / "desk" / "risk.json", TMP / "risk.json")
shutil.copy(ROOT / "desk" / "config.json", TMP / "config.json")
os.environ.update({
    "AURUM_DESK_LOGS": str(TMP / "logs"), "AURUM_DESK_JOURNAL": str(TMP / "journal"),
    "AURUM_DESK_MEMORY": str(TMP / "memory"), "AURUM_DESK_INBOX": str(TMP / "inbox"),
    "AURUM_DESK_REPORTS": str(TMP / "reports"), "AURUM_DESK_PLAYBOOKS": str(TMP / "playbooks"),
    "AURUM_DESK_TICKETS": str(TMP / "tickets.jsonl"), "AURUM_DESK_RISK": str(TMP / "risk.json"),
    "AURUM_DESK_CONFIG": str(TMP / "config.json"), "AURUM_DESK_NOLAUNCH": "1",
    "AURUM_DESK_MUTEX_SUFFIX": "_test", "AURUM_DESK_NOW": "2026-10-21T14:00:00",  # a Wednesday, London/NY overlap
    "AURUM_DESK_BOARD": str(TMP / "board.jsonl"),
})
os.environ.pop("AURUM_DESK_ROLE", None)
os.environ.pop("AURUM_DESK_DRY", None)
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from desk import broker, journal, news, paths, phase, risk_gate, spreads, tickets  # noqa: E402

EURUSD = {"tick_size": 0.00001, "tick_value": 1.0, "point": 0.00001, "digits": 5, "vol_min": 0.01, "vol_step": 0.01,
          "vol_max": 100.0, "stops_level": 0, "trade_mode": 4, "spread_pts": 10, "contract": 100000}


def set_now(monkeypatch, iso):
    monkeypatch.setenv("AURUM_DESK_NOW", iso)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_NOW", "2026-10-21T14:00:00")
    monkeypatch.delenv("AURUM_DESK_ROLE", raising=False)
    for p in (paths.STATE, paths.JOURNAL, paths.INBOX, paths.MEMORY, paths.REPORTS, paths.PLAYBOOKS):
        shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)
    for f in (tickets.FILE, paths.KILL, TMP / "board.jsonl"):
        if Path(f).exists():
            Path(f).unlink()
    # the owner's profiles, but the tests' baseline is demo_10k whatever the owner has active
    paths.write_json(paths.RISK, {**paths.read_json(ROOT / "desk" / "risk.json", {}), "active": "demo_10k"})
    monkeypatch.setattr(risk_gate.spreads, "check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(risk_gate.news, "blocking", lambda *a, **k: None)
    phase.start("demo")
    yield


@pytest.fixture
def cfg():
    return paths.config()


@pytest.fixture
def b():
    pb = broker.PaperBroker(balance=10000.0, specs={"EURUSD": dict(EURUSD)})
    pb.set_price("EURUSD", 1.10000, 1.10010)
    return pb


def backdate_phase(days):
    """Move day 0 back so the desk is in a later phase (28+ days: phase 3, full risk)."""
    import datetime as dt
    from desk import clocks
    s = phase.state()
    s["day0"] = (clocks.now() - dt.timedelta(days=days)).isoformat(timespec="seconds")
    paths.write_json(phase.FILE, s)


def ticket(**over):
    t = {"pod": "fxmacro", "instrument": "EURUSD", "side": "buy", "stop": 1.09500, "thesis": "test long",
         "invalidation": "below 1.095", "edge": "test_edge"}
    t.update(over)
    return t
