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


def test_command_center_main_shows_live_state():
    import base64, gzip
    from desk import command_center as cc
    state = {"live_gate": {"checks": {"weeks": {"need": 8, "have": 0.7, "ok": False},
                                      "trades": {"need": 100, "have": 7, "ok": False}}},
             "needs_you": [{"level": "WARN", "what": "Demo heartbeat is stale"}], "pods": []}
    extra = {"state": state, "queue": [{"id": "q-live-1", "status": "new"}]}
    out = cc.build(dashboard.BUNDLE, {}, [], [], extra).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[0]]
    raw = base64.b64decode(e["data"])
    main = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    assert "gv('Trades', '7 Of 100'" in main and "gv('Weeks', '0.7 Of 8.0'" in main
    assert "Demo heartbeat is stale" in main
    assert "q-live-1" in main


def test_command_center_pods_shows_live_state():
    import base64, gzip
    from desk import command_center as cc
    pod = {"name": "systematic", "share": 0.25, "score": {"trades": 6, "pnl": -37.0, "total_R": -1.74, "hit": 0.5},
           "intel": {"work": {"runs": 9, "notes": 9}, "talk": {"asked": 1}, "share": {"cited": 2}, "trading": {"hit": 0.5}}}
    state = {"t": "2026-11-01T10:05:00", "limits": {"equity": 10000}, "pods": [pod],
             "board": [{"t": "2026-11-01T10:00:00", "pod": "head-trader", "kind": None, "text": "It's flat \\ ok"}],
             "tickets": [{"id": "t-1", "pod": "crypto", "status": "blocked", "side": "sell", "instrument": "BTCUSD",
                          "risk_pct": 0.1, "why": "past the weekend cutoff"}]}
    out = cc.build(dashboard.BUNDLE, {}, [], [], {"state": state}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[1]]
    raw = base64.b64decode(e["data"])
    pods = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    assert "alloc: 25, c: { runs: 9, notes: 9, asked: 1," in pods and "closed: 6, followed: '-1.74 R'" in pods
    assert "from: 'head-trader'" in pods and "|| {}).name || String(id)" in pods
    assert "past the weekend cutoff" in pods and "state: 'Blocked'" in pods
    assert "label: 'Messages Today', value: '1'" in pods


def test_command_center_eas_shows_live_state():
    import base64, gzip
    from desk import command_center as cc
    state = {"limits": {"equity": 9962.86, "balance": 9958.4, "floors": {"day": 9562.86, "kill": 9311.2995}},
             "edges": {"armed": [{"edge": "golddip", "market": "XAUUSD", "risk_pct": 0.25},
                                 {"edge": "noise", "market": "US100", "risk_pct": 0.25}]},
             "status": {"halt": "KILL file"}}
    pos = {"symbol": "EURUSD", "type": 0, "volume": 0.05, "price_open": 1.08, "profit": 1.0, "comment": "fix"}
    out = cc.build(dashboard.BUNDLE, {}, [], [pos], {"state": state}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[2]]
    raw = base64.b64decode(e["data"])
    eas = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    assert "KILL = 9311.30;" in eas and "Balance 9,958.40" in eas
    assert "'Max Loss Kill', '9,311.30', 'Halted', 'red'" in eas and "fundedState: 'Halted'" in eas
    assert "name: 'AurumFunded', ver: '" + cc._ea_versions()["AurumFunded"] + "'" in eas
    assert "'/' + e.name + '.mq5'" in eas and "['Bell', 'Hydra']" in eas
    assert "value: '1', sub: 'EURUSD 0.05 · fix'" in eas
    assert "id: 'noise', name: 'Noise', market: 'US100'" in eas and "size: '0.25%'" in eas
    assert "id: 'bellfade'" not in eas and "today.golddip = 0.18" not in eas


def test_command_center_processes_shows_live_state():
    import base64, gzip
    from desk import command_center as cc
    state = {"t": "2026-11-01T11:42:49+00:00",
             "schedule": [{"name": "calendar", "ran": "2026-11-01T00:06:35+00:00"},
                          {"name": "commit", "ran": "2026-10-27T00:00:00+00:00"},
                          {"name": "debrief", "ran": "2026-10-30T17:15:00+00:00"}],
             "runner": {"recent": [
                 {"kind": "brief", "name": "crypto_weekend", "pods": ["crypto"], "status": "done",
                  "started": "2026-11-01T10:00:05+00:00", "done": "2026-11-01T10:01:25+00:00"},
                 {"kind": "debrief", "name": "debrief", "status": "error", "started": "2026-11-01T09:00:00+00:00"}]},
             "status": {"heartbeat": {"t": "2026-11-01T11:40:03+00:00", "ok": True, "broker": "mt5"}}}
    out = cc.build(dashboard.BUNDLE, {}, [], [], {"state": state}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[3]]
    raw = base64.b64decode(e["data"])
    pr = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    assert "const HERE = 'Processes.dc.html'" in pr
    assert "last: 'Sun 00:06 · 11h 36m Ago', state: 'OK'" in pr
    assert "last: 'Tue 00:00 · 5d Ago', state: 'Late'" in pr and "when: '23:30 UTC', utc: 1410" in pr
    assert "last: 'Fri 17:15 · 1d Ago'" not in pr and "state: 'Failed'" in pr
    assert "const runs = LIVE_RUNS.map" in pr and "Brief · Crypto · 1m 20s" in pr and '"Crypto Desk"' in pr
    assert "value: '2', sub: '1 OK · 1 Other'" in pr and "value: '1', sub: 'Last Failure Sun 01 Nov'" in pr
    assert '"mt5": 166' in pr and "dur(a) + ' Ago'" in pr


def test_command_center_research_shows_live_state(tmp_path):
    import base64, gzip
    from desk import command_center as cc
    out = cc.build(dashboard.BUNDLE, {}, [], [], {}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[4]]
    raw = base64.b64decode(e["data"])
    tpl = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    d = tmp_path
    (d / "ideas").mkdir()
    (d / "gates").mkdir()
    jl = lambda rows: "\n".join(json.dumps(r) for r in rows)
    (d / "ideas" / "queue.jsonl").write_text(jl([
        {"id": "a_one", "title": "Idea A", "status": "rejected", "reason": "Halves 0.1/0.2"},
        {"id": "b_two", "title": "Idea B", "status": "queued"}]))
    (d / "ideas" / "backlog.jsonl").write_text(jl([
        {"id": "c_three", "title": "Idea C", "status": "open", "gap": "indices", "kind": "paper", "added": "2026-10-30"}]))
    (d / "ideas" / "results.jsonl").write_text(jl([{"id": "a_one"}, {"id": "d_four"}]))
    (d / "gates" / "d_four.json").write_text(json.dumps({
        "id": "d_four", "verdict": "PASS", "when": "2026-10-31",
        "halves": {"to_2017": 0.5, "from_2018": 0.6}}))
    (d / "gates" / "a_one.json").write_text(json.dumps({"id": "a_one", "verdict": "FAIL"}))
    (d / "candidates.json").write_text(json.dumps({"candidates": []}))
    (d / "gaps.json").write_text(json.dumps({"book_sharpe_2018": 2.5,
                                             "legs": [{"leg": "noise", "book_without": 2.7}]}))
    (d / "ideas" / "steer.md").write_text(
        "# Steer - 2026-10-31\n\n## Top 2 gaps\n\n"
        "1. **US/EU/Asian indices (4%).** Split done: below. The book has one index leg.\n"
        "2. **Weeks+ horizon.** Nothing untried this week.\n", encoding="utf-8")
    pr = cc._patch_research_page(tpl, {}, [], root=d)
    assert 'const FUNNEL = [["Ideas Found", "Finder · Queue, Scans, Gates", 4]' in pr and "found: 4 }" in pr
    assert "Math.log(1 + v)" in pr and "label: 'Ideas Tried'" in pr
    assert '"name": "D Four"' in pr and '"stage": "Gate"' in pr
    assert '"name": "Idea C"' in pr and "sel: 'd_four'" in pr
    assert '"name": "US/EU/Asian Indices", "why": "The book has one index leg."' in pr and "1 Open Idea · Idea C" in pr
    assert '"name": "Idea A", "at": "Gate"' in pr
    assert "label: 'In The Queue', value: '2'" in pr and "value: '50%', sub: '1 Of 2 Gated'" in pr
    assert "label: 'Book Sharpe', value: '2.50'" in pr and "v: '1 · noise'" in pr
    assert "{ k: 'Last Run', v: 'Sat 31 Oct' }" in pr and "Next Run', v: 'Sat 7 Nov" in pr


def test_command_center_controls_shows_live_state(tmp_path, monkeypatch):
    import base64, gzip
    from desk import command_center as cc
    out = cc.build(dashboard.BUNDLE, {}, [], [], {}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[5]]
    raw = base64.b64decode(e["data"])
    tpl = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    (tmp_path / "desk").mkdir()
    (tmp_path / "docs" / "autopilot").mkdir(parents=True)
    (tmp_path / "logs" / "autopilot").mkdir(parents=True)
    (tmp_path / "desk" / "risk.json").write_text(json.dumps({"active": "p1", "profiles": {"p1": {
        "kind": "prop", "per_trade_pct": 0.5, "desk_open_pct": 3.0, "daily_loss_pct": 4.0, "max_loss_pct": 9.0,
        "kill_dd_pct": 7.0, "news_window_min": 2, "allow_live": False}}}))
    (tmp_path / "desk" / "config.json").write_text(json.dumps({"pods": {"metals": {"owns": ["XAUUSD"]}}}))
    (tmp_path / "logs" / "autopilot" / "last-finder.json").write_text(
        json.dumps({"model": "sonnet", "reason": "3 ideas queued", "ended": "2026-11-01T10:00:00", "empty_streak": 2}),
        encoding="utf-8-sig")
    (tmp_path / "docs" / "autopilot" / "approvals.json").write_text(json.dumps(
        {"items": [{"id": "a9", "what": "Step 19: buy a challenge", "status": "pending"}]}))
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    monkeypatch.setattr(cc, "DOCS", tmp_path / "docs")
    state = {"pods": [{"name": "metals", "active": True, "enabled": True, "paused": False,
                       "intel": {"level": {"n": 2, "name": "Analyst"}}}],
             "alloc": {"paused": []}, "status": {"halt": None},
             "tickets": [{"pod": "metals", "created": "2026-11-01T09:30:00", "status": "closed"}],
             "limits": {"account": "Demo Co/demo/p1", "day": "2026-11-01", "day_balance": 10000, "equity": 9900,
                        "record": {"max_dd_pct": 1.5}},
             "journal": [{"t": "2026-11-01T09:31:00", "kind": "ticket_block", "by": "code", "why": "news window"}]}
    pr = cc._patch_controls_page(tpl, state, [])
    assert '"name": "Metals Pod", "what": "Tickets For XAUUSD."' in pr
    assert "Last Ticket 09:30" in pr and "3 ideas queued" in pr and "2 Empty Runs" in pr
    assert '"where": "approvals · a9", "state": "Waiting"' in pr and "allow_live: false" in pr
    assert '["Daily Loss", "Desk Halts At 4%", 1.0, 4.0, "%"]' in pr and "Funded Account · Demo Co Demo" in pr
    assert '"what": "Ticket Block"' in pr and '"state": "Cancelled"' in pr
    assert "sub: 'Funded · Halts At 4%'" in pr and "fivex: { title: '5x EA" in pr


def test_command_center_agents_shows_live_state(tmp_path, monkeypatch):
    import base64, gzip
    import datetime as dt
    from desk import command_center as cc
    out = cc.build(dashboard.BUNDLE, {}, [], [], {}).decode("utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[6]]
    raw = base64.b64decode(e["data"])
    tpl = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    auto = tmp_path / "logs" / "autopilot"
    auto.mkdir(parents=True)
    (tmp_path / "tools" / "autopilot").mkdir(parents=True)
    (tmp_path / "tools" / "autopilot" / "router.json").write_text(json.dumps({
        "provider": "claude", "fallback": {"order": ["claude", "qwen"], "backoff_minutes": 45},
        "providers": {"claude": {"tiers": {"code": "sonnet", "judge": "opus"}}},
        "roles": {"builder": {"tier": "judge", "turns": 99, "minutes": 33}}}))
    today = dt.date.today().isoformat()
    (auto / "last-finder.json").write_text(json.dumps({"reason": "0 ideas queued", "empty_streak": 4,
                                                       "runs_day": today, "runs_today": 7}), encoding="utf-8-sig")
    (auto / "last-judge.json").write_text(json.dumps({"runs_day": today, "runs_today": 3}), encoding="utf-8-sig")
    (auto / "relay.json").write_text(json.dumps({"next": "judge"}))
    (auto / f"{today}_relay.log").write_text(f"{today} 10:01:02  start judge (judge j9)\n"
                                             f"{today} 10:05:00  finder backed off until x: empty\n")
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    live = {"budget": {"week_start": today + "T00:00:00"}}
    usage = [{"ts": today + "T09:00:00", "role": "builder", "input": 1_500_000, "output": 0}]
    pr = cc._patch_agents_page(tpl, live, usage)
    assert "tier: 'Judge', model: 'Opus', turns: 99, minutes: 33" in pr and "tokens: 1.50" in pr
    assert "task: 'Last Run: 0 Ideas Queued'" in pr and "const runsToday = 10;" in pr
    assert "sub: 'Finder 7, Judge 3'" in pr and "Backoff 45 Min" in pr and "value: '45 Min'" in pr
    assert "value: 'Judge'" in pr and "value: 'Ready', sub: '4 Empty Runs In A Row'" in pr
    assert '"who": "Judge", "kind": "Run"' in pr and '"kind": "Backoff"' in pr
    assert "backoff: true" not in pr.split("const ROLES", 1)[1].split("];", 1)[0]


def test_command_center_main_shows_live_logs(tmp_path):
    import base64, gzip, pathlib
    import datetime as dt
    from desk import command_center as cc
    out = pathlib.Path(dashboard.BUNDLE).read_text(encoding="utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[0]]
    raw = base64.b64decode(e["data"])
    tpl = json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))
    (tmp_path / "ideas").mkdir()
    (tmp_path / "gates").mkdir()
    (tmp_path / "ideas" / "queue.jsonl").write_text("\n".join(json.dumps({"id": f"q{n}"}) for n in range(5)))
    for n, gate in enumerate(["halves", "halves", "costs"]):
        (tmp_path / "gates" / f"g{n}.json").write_text(json.dumps(
            {"id": f"g{n}", "verdict": "FAIL", "gates": [{"gate": gate, "pass": False}, {"gate": "dsr", "pass": False}]}))
    today = dt.date(2026, 11, 1)
    usage = [{"ts": "2026-11-01T09:50:05", "role": "finder", "model": "sonnet", "input": 1_000_000, "output": 500_000},
             {"ts": "2026-11-01T08:00:00", "role": "tester", "model": "haiku", "input": 250_000},
             {"ts": "2026-10-31T23:00:00", "role": "judge", "model": "opus", "input": 9}]
    pr = cc._patch_main_live(tpl, {}, usage, root=tmp_path, today=today)
    assert 'const baseTok = {"Finder": 1.5, "Tester Operator": 0.25};' in pr
    assert 'const baseRuns = [["09:50", "Finder", "Sonnet", 1000000, 500000, 0, 0]' in pr
    assert "fmtTok(1750000 + liveTok + doneTok)" in pr and "String(2 + s.done.length)" in pr and "'2 Runs'" in pr
    assert '["Ideas Tried", 8]' in pr and '["Full Backtest", 3]' in pr and "Math.log(9)" in pr
    assert "Both Halves', 2]" in pr and "1.5x Costs', 1]" in pr and "(f / 2 * 100)" in pr


def _main_template():
    import base64, gzip, pathlib
    from desk import command_center as cc
    out = pathlib.Path(dashboard.BUNDLE).read_text(encoding="utf-8")
    man = json.loads(cc._MANIFEST.search(out).group(2))
    e = man[json.loads(cc._ORDER.search(out).group(1))[0]]
    raw = base64.b64decode(e["data"])
    return json.loads(cc._TEMPLATE.search((gzip.decompress(raw) if e.get("compressed") else raw).decode("utf-8")).group(2))


def test_command_center_main_feed_from_usage_journal_and_git():
    import datetime as dt
    from desk import command_center as cc
    src = _main_template()
    day = dt.date(2026, 11, 1)
    usage = [{"ts": "2026-11-01T09:50:05", "role": "finder", "model": "sonnet", "output": 2703},
             {"ts": "2026-10-31T09:50:05", "role": "finder", "model": "sonnet", "output": 1}]
    state = {"journal": [
        {"t": "2026-11-01T11:01:00+00:00", "kind": "ticket_approve", "id": "abc-1", "why": "ok"},
        {"t": "2026-11-01T11:01:00+00:00", "kind": "agent_run", "role": "head-trader", "model": "opus", "tokens": 39616},
        {"t": "2026-10-30T11:00:00+00:00", "kind": "monitor", "issues": 3}]}
    out = cc._patch_main_feed(src, state, usage, [("13:55", "Dashboard it's live")], today=day)
    assert "'Demo Log: AurumFunded 1.19 Deployed On T16'" not in out
    assert '["09:50", "Finder", "Run Done · Sonnet · 2,703 Out"]' in out
    assert '"Ticket", "Ticket Approved · abc-1 · ok"]' in out
    assert "Head Trader Run · Opus · 39,616 Tokens" in out
    assert '["13:55", "Git", "Dashboard it’s live"]' in out
    assert "Monitor: 3 Issues" not in out and "1 Out" not in out
    assert out.index('"13:55"') < out.index('"09:50"')
    assert "\n    ].map(([t, src, text])" in out
    assert cc._patch_main_feed(src, {}, [], [], today=day) == src


def test_command_center_main_shows_live_processes():
    from desk import command_center as cc
    D = r"C:\MetaTrader 5 - Desk\terminal64.exe"
    assert cc._proc_doing("terminal64.exe", D, [D]) == ("Desk Terminal", "'Desk Kill'")
    assert cc._proc_doing("terminal64.exe", r"C:\Program Files\MetaTrader 5 - 16\terminal64.exe", [])[0] == "T16 · AurumFunded"
    assert cc._proc_doing("pythonw.exe", "", ["pythonw", "-m", "desk.dashboard"])[0] == "Desk Dashboard · State API"
    assert cc._proc_doing("python.exe", "", ["python", "-c", "print(1)"]) is None
    assert cc._proc_doing("claude.exe", "", ["claude", "-p", "go"]) is None
    rows = [{"pid": 3324, "name": "Terminal64", "doing": "Desk Terminal", "guard": "'Desk Kill'", "cpu": 1.42, "mb": 13.4},
            {"pid": 14440, "name": "Terminal64", "doing": "T16 · AurumFunded", "guard": cc._T16_GUARD, "cpu": 0.2, "mb": 10}]
    pr = cc._patch_main_procs(_main_template(), rows, {"ram": 15.9, "commit": 9.04, "limit": 31.88})
    assert "{ pid: '3324', name: 'Terminal64', doing: 'Desk Terminal', cpu: '1.4', mb: '13', guard: 'Desk Kill' }" in pr
    assert "guard: s.held ? 'Held' : 'Hold And Release' }\n    ].concat(liveRuns" in pr and "'15740'" not in pr
    assert "const commit = 9.0 +" in pr and "' Of 31.9 GB'" in pr and "(commit / 31.9 * 100)" in pr
    assert "'RAM 15.9 GB · '" in pr


def test_command_center_main_funded_from_t16_log(tmp_path):
    from desk import command_center as cc
    logs = tmp_path / "MQL5" / "Logs"
    logs.mkdir(parents=True)
    t = "AurumFunded (XAUUSD,M15)\tAurumFunded: "
    (logs / "20261029.log").write_text("\n".join([
        f"IH\t0\t23:00:00.696\t{t}firm day 2026.10.30, day start 9993.33 (balance 9993.33, equity 9993.33), day stop",
        f"RN\t0\t23:05:00.129\t{t}account 12345678 leverage 1:100",
    ]), encoding="utf-16")
    (logs / "20261030.log").write_text("\n".join([
        f"JK\t0\t12:30:00.047\t{t}midday leg sold 0.45 EURUSD at 1.11936, stop 1.12140",
        f"QM\t0\t13:59:59.772\t{t}closed EURUSD magic 20261030 0.45 at 1.11762, P/L 68.56 EUR",
        f"HH\t0\t15:29:59.874\t{t}US500.cash sold 0.65 lots at 7602.95, bands 7744.30 / 7611.57",
        f"PQ\t0\t16:00:00.157\t{t}closed US500.cash magic 99 0.65 at 7622.05, P/L -11.38 EUR",
        f"OI\t0\t17:29:59.782\t{t}US500.cash sold 0.63 lots at 7598.20, bands 7751.65 / 7604.30",
    ]), encoding="utf-8")
    t16 = cc._t16_log(tmp_path)
    assert t16["balance"] == pytest.approx(10050.51) and t16["day"] == pytest.approx(57.18)
    assert t16["positions"] == 1 and t16["firm"] == "2026.10.30" and t16["last"] == "Fri 17:29"
    assert cc._t16_log(tmp_path / "none") is None
    out = cc._patch_main_funded(_main_template(), t16, "1.19")
    assert "this.fundedCurve = [9993.33, 10061.89, 10050.51];" in out
    assert "equity: money(10050.51), change: '+57.18 On Firm Day 2026.10.30 · 1 Open, Equity Not In The Log'" in out
    assert "st('Floating P/L', '—'), st('Day P/L', '+57.18'), st('Positions', '1')" in out
    assert "st('Last Log', 'Fri 17:29', '#6E6E73')" in out
    assert "value: '10,050.51', sub: s.held ? 'Held By Owner' : 'AurumFunded v1.19'" in out
    assert "[T16" not in out and "12345678" not in out


def test_command_center_main_rules_from_t16_log_and_preset(tmp_path):
    from desk import command_center as cc
    logs = tmp_path / "MQL5" / "Logs"
    logs.mkdir(parents=True)
    t = "AurumFunded (XAUUSD,M15)\tAurumFunded: "
    (logs / "20261030.log").write_text("\n".join([
        f"IH\t0\t00:00:01.000\t{t}firm day 2026.10.30, day start 10100.00 (balance 10100.00, equity 10100.00), "
        f"day stop at 9800.00, highest day start 10100.00, final stop at 9150.00 (static)",
        f"JK\t0\t12:30:00.047\t{t}US500.cash sold 0.65 lots at 7602.95, bands 7744.30 / 7611.57",
        f"QM\t0\t13:59:59.772\t{t}closed US500.cash magic 99 0.65 at 7622.05, P/L -50.00 EUR",
    ]), encoding="utf-8")
    ini = tmp_path / "t16_attach.ini"
    ini.write_text("[Common]\nAccount=1\n[Experts]\nExpertParameters=p.set\n", encoding="utf-8")
    (tmp_path / "p.set").write_text("InpPropTargetPct=10.0\nInpPropMinDays=4\nInpPropMaxStopPct=8.5\n", encoding="utf-16")
    preset = cc._t16_preset(ini, tmp_path)
    assert preset == {"PropTargetPct": 10.0, "PropMinDays": 4.0, "PropMaxStopPct": 8.5}
    assert cc._t16_preset(tmp_path / "none.ini", tmp_path) == {}
    t16 = cc._t16_log(tmp_path)
    assert t16["final"] == 9150.0 and t16["traded"] == 1
    out = cc._patch_main_rules(_main_template(), t16, preset)
    assert "label: 'Daily Loss Limit', value: '0.50% Of 5%', bar: bar(10.0, '#FF9500')" in out
    assert "label: 'Max Loss', value: '0.00% Of 10%', bar: bar(0.0, '#D70015')" in out
    assert "label: 'Profit Target', value: '0.50% Of 10% · Days 1 Of 4', bar: bar(5.0, '#34C759')" in out
    assert cc._patch_main_rules("x", t16, {}) == "x"


def test_command_center_main_legs_from_t16_log(tmp_path):
    import datetime as dt
    from desk import command_center as cc
    logs = tmp_path / "MQL5" / "Logs"
    logs.mkdir(parents=True)
    t = "AurumFunded (XAUUSD,M15)\tAurumFunded: "
    (logs / "20261030.log").write_text("\n".join([
        f"IH\t0\t00:00:01.000\t{t}firm day 2026.10.29, day start 10000.00 (balance 10000.00)",
        f"JK\t0\t09:00:00.000\t{t}USD/JPY broke its range, bought 0.30 lots at 152.10, stop 151.80",
        f"IH\t0\t23:00:01.000\t{t}firm day 2026.10.30, day start 10000.00 (balance 10000.00)",
        f"JK\t0\t12:30:00.047\t{t}midday leg sold 0.45 EURUSD at 1.11936, stop 1.12140",
        f"JK\t0\t12:45:00.047\t{t}USD/JPY broke its range, sold 0.30 lots at 152.10, stop 152.40",
        f"HH\t0\t15:29:59.874\t{t}US500.cash sold 0.65 lots at 7602.95, bands 7744.30 / 7611.57",
        f"HH\t0\t16:29:59.874\t{t}US100.cash sold 0.07 lots at 25602.95, bands 25744.30 / 25611.57",
        f"HH\t0\t17:00:00.000\t{t}dip unit, leverage 1.20, model weight 0.50, bought 0.10",
        f"HH\t0\t17:30:00.000\t{t}Dual Thrust US500.cash bought 0.20 lots at 7600.00, levels 7610.00 / 7590.00",
    ]), encoding="utf-8")
    t16 = cc._t16_log(tmp_path)
    assert t16["legs"] == {"Midday": 1, "Breakout": 1, "Noise Area": 2, "Dip": 1, "Dual Thrust": 1}
    src = ("Legs · Orders Today\nconst legs = ['Midday', 'Breakout', 'Noise Area', 'Dip', 'VRP']"
           ".map((n) => ({ name: n, orders: '0' }));")
    out = cc._patch_main_legs(src, t16, dt.date(2026, 10, 30))
    assert "Legs · Orders Today" in out and "orders: '0'" not in out
    assert '"Noise Area": 2' in out and "[n] || 0" in out
    assert "Legs · Orders 30 Oct" in cc._patch_main_legs(src, t16, dt.date(2026, 11, 1))
    assert cc._patch_main_legs(src, None) == src
