import json
import threading
import urllib.error
import urllib.request

import pytest

from desk import dashboard, paths, risk_gate


@pytest.fixture
def srv(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_DRY", "1")  # never attach to a terminal from a test
    s = dashboard.server("127.0.0.1", 0)
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    s.server_close()


def _post(url, headers=None):
    req = urllib.request.Request(url + "/api/kill", data=b'{"why": "test"}', method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_state_has_every_section(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_DRY", "1")
    s = dashboard.State().build()
    for k in ("t", "status", "limits", "live", "equity_series", "pods", "budgets", "board", "journal", "agents",
              "tickets", "r_series", "news", "runner", "edges", "live_gate", "phase", "schedule", "needs_you"):
        assert k in s, k
    assert s["live"]["source"] == "heartbeat"
    assert {p["name"] for p in s["pods"]} >= {"systematic", "fxmacro"}
    assert s["phase"]["phase"] == 1
    json.dumps(s, default=str)


def test_page_and_api(srv):
    with urllib.request.urlopen(srv + "/", timeout=10) as r:
        assert r.status == 200 and b"/api/state" in r.read()
    with urllib.request.urlopen(srv + "/api/state", timeout=30) as r:
        assert "pods" in json.loads(r.read())
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(srv + "/nope", timeout=10)


def test_kill_needs_the_header_and_a_local_origin(srv):
    assert _post(srv)[0] == 403
    assert _post(srv, {"X-Desk": "kill", "Origin": "https://evil.example"})[0] == 403
    assert not paths.KILL.exists()
    code, body = _post(srv, {"X-Desk": "kill", "Origin": srv})
    assert code == 200 and body["ok"]
    assert paths.KILL.exists() and "owner: test" in paths.KILL.read_text(encoding="utf-8")
    assert risk_gate.halted().startswith("KILL file")
