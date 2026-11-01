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
    with urllib.request.urlopen(srv + "/", timeout=30) as r:
        assert r.status == 200 and b"__bundler/manifest" in r.read()
    with urllib.request.urlopen(srv + "/classic", timeout=10) as r:
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


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def test_read_js_parses_wrapper_and_caches(tmp_path):
    f = tmp_path / "x.js"
    f.write_text('window.AURUM = {"a": 1, "runs": [1,2]};\n', encoding="utf-8")
    d, mt = dashboard.read_js(f)
    assert d == {"a": 1, "runs": [1, 2]} and mt
    assert dashboard.read_js(f)[0] is d  # same mtime: cached object
    d2, mt2 = dashboard.read_js(tmp_path / "missing.js")
    assert "error" in d2 and mt2 is None


def test_slim_aurum_cuts_runs_and_gates():
    big = {"runs": [{"n": i} for i in range(100)], "demo": {"log": "x" * 9000},
           "ledger": {"candidates": [{"id": "a", "notes": "long", "status": "tester"}], "rejected": []},
           "gates": {"g": {"id": "g", "verdict": "PASS", "extra": 1, "gates": [{"gate": "dsr", "pass": True, "figure": "1", "rule": "r"}]}}}
    o = dashboard.slim_aurum(big)
    assert len(o["runs"]) == 40 and o["runs"][-1] == {"n": 99}
    assert len(o["demo"]["log"]) == 3000
    assert o["ledger"]["candidates"] == [{"id": "a", "status": "tester"}]
    assert o["gates"]["g"]["gates"] == [{"gate": "dsr", "pass": True, "figure": "1"}]


def test_live_aurum_queue_usage_routes(srv, monkeypatch, tmp_path):
    live = tmp_path / "live.js"
    live.write_text('window.AURUM_LIVE = {"paused": false, "roles": {}};', encoding="utf-8")
    monkeypatch.setattr(dashboard, "LIVE_JS", live)
    d = _get(srv + "/api/live")
    assert d["paused"] is False and d["file_age_s"] is not None
    a = _get(srv + "/api/aurum")
    assert "error" in a or "ledger" in a
    q = _get(srv + "/api/queue")
    assert set(q) == {"queue", "gaps"}
    assert "rows" in _get(srv + "/api/usage")
    monkeypatch.setattr(dashboard, "LIVE_JS", tmp_path / "gone.js")
    assert "error" in _get(srv + "/api/live")


def test_new_routes_are_read_only(srv):
    for p in ("/api/live", "/api/aurum", "/api/queue", "/api/usage"):
        req = urllib.request.Request(srv + p, data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(req, timeout=10)


def test_command_center_build_patches_every_page():
    import base64, gzip
    from desk import command_center as cc
    live = {"generated_iso": "2026-11-01T03:10:00", "budget": {"week_start": "2026-10-26"},
            "roles": {"judge": {"state": {"reason": "j19 judged as diagnostic only"}}},
            "steps": {"relay": ["2026-11-01 03:10:00  judge j19 diagnostic only, next tester"]}}
    usage = [{"ts": "2026-11-01T03:10:00", "role": "judge", "input": 1000, "output": 500}]
    pos = [{"symbol": "XAUUSD", "type": 0, "volume": 0.1, "price_open": 2650.5, "profit": -12.3, "comment": "grz"}]
    out = cc.build(dashboard.BUNDLE, live, usage, pos).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    order = json.loads(cc._ORDER.search(out).group(1))
    pages = []
    for uid in order:
        e = man[uid]
        raw = base64.b64decode(e["data"])
        inner = (gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")
        pages.append(json.loads(cc._TEMPLATE.search(inner).group(2)))
    assert len(pages) == 7
    for src in pages:
        assert "Sample Data" not in src and "Live Snapshot · Sun 01 Nov 03:10" in src
        assert "this.advance(), 1000" not in src
    main = pages[0]
    assert main.count("/api/kill") == 1 and "'X-Desk': 'kill'" in main
    assert "XAUUSD" in main and "−12.30" in main
    assert "Last Run: J19 Judged As Diagnostic Only" in main
