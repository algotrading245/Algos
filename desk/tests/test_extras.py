import datetime as dt

import pytest

from desk import cli, clocks, edges, extras, live_gate, paths, playbooks, runner, sandbox, scorekeeper, systematic
from desk.edges import base

GOOD = '''
import numpy as np
from desk.edges.base import edge, sig, atr


@edge("t_new", ["EURUSD"], "H1", pod="fxmacro", defaults={"n": 3})
def t_new(df, p, ctx):
    a = atr(df, 14)
    return [sig(len(df) - 1, "buy", float(df.close.iloc[-1] - 2 * a.iloc[-1]), "test")]
'''


# ---- the source check and load_new -----------------------------------------------------------------------------------

def test_check_allows_plain_computation():
    assert edges.check(GOOD) == []


@pytest.mark.parametrize("src, reason", [
    ("import os", "import os"),
    ("import subprocess as s", "import subprocess"),
    ("from desk import paths", "from desk import"),
    ("from desk.edges.base import paths", "desk.edges.base.paths"),
    ("from . import base", "relative import"),
    ("f = open('x')", "open"),
    ("x = ().__class__", ".__class__"),
    ("import pandas as pd\npd.read_csv('x')", ".read_csv"),
    ("def f(df): df.to_csv('x')", ".to_csv"),
    ("import numpy as np\nnp.save('x', 1)", ".save"),
    ("x = __builtins__", "__builtins__"),
    ("from desk.edges.base import EDGES", "desk.edges.base.EDGES"),
    ("def f():\n    global y", "global"),
    ("def f(", "syntax"),
])
def test_check_refuses(src, reason):
    assert any(r.startswith(reason) for r in edges.check(src)), edges.check(src)


def test_check_allows_safe_to_and_datetime():
    assert edges.check("import pandas as pd\nimport datetime as dt\nx = pd.to_datetime([1]).to_numpy()") == []


@pytest.fixture
def new_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(edges, "NEW", tmp_path)
    monkeypatch.setattr(edges, "BROKEN", {})
    monkeypatch.setattr(edges, "OWNER", {})
    saved = dict(base.EDGES)
    yield tmp_path
    base.EDGES.clear()
    base.EDGES.update(saved)


def test_load_new_registers_a_clean_edge(new_dir):
    (new_dir / "t_new.py").write_text(GOOD, encoding="utf-8")
    assert edges.load_new() == {}
    assert base.EDGES["t_new"]["pod"] == "fxmacro"
    assert edges.OWNER["t_new"] == "t_new.py"
    edges.load_new()  # loading the same file again is not a clash
    assert edges.BROKEN == {}


def test_load_new_refuses_unsafe_source(new_dir):
    (new_dir / "bad.py").write_text("import os\n" + GOOD, encoding="utf-8")
    edges.load_new()
    assert "import os" in edges.BROKEN["bad.py"]
    assert "t_new" not in base.EDGES


def test_load_new_refuses_replacing_a_builtin(new_dir):
    name = sorted(edges.BUILTIN)[0]
    before = base.EDGES[name]
    (new_dir / "steal.py").write_text(GOOD.replace('"t_new"', f'"{name}"'), encoding="utf-8")
    edges.load_new()
    assert "replaces" in edges.BROKEN["steal.py"]
    assert base.EDGES[name] is before


def test_load_new_refuses_another_files_edge_and_benchmarks(new_dir):
    (new_dir / "a.py").write_text(GOOD, encoding="utf-8")
    (new_dir / "b.py").write_text(GOOD, encoding="utf-8")
    (new_dir / "c.py").write_text(GOOD.replace('"t_new"', '"t_bench"').replace('pod="fxmacro"', 'kind="benchmark"'),
                                  encoding="utf-8")
    edges.load_new()
    assert edges.OWNER["t_new"] == "a.py"
    assert "replaces t_new" in edges.BROKEN["b.py"]
    assert "benchmark" in edges.BROKEN["c.py"]
    assert "t_bench" not in base.EDGES


# ---- arming a leg ------------------------------------------------------------------------------------------------------

@pytest.fixture
def armable(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "CARDS", tmp_path)
    monkeypatch.setitem(base.EDGES, "t_leg", {"name": "t_leg", "markets": ["EURUSD"], "tf": "H1", "pod": "systematic",
                                              "kind": "leg", "bars": 40, "needs": [], "defaults": {"n": 3},
                                              "card": "", "fn": lambda df, p, ctx: []})
    monkeypatch.setenv("AURUM_DESK_ROLE", "systematic")
    paths.write_json(systematic.FILE, {"armed": []})

    def card(**run):
        r = {"params": {"n": 3}, "from": None, "to": None, "trades": 40, "pf": 1.3}
        r.update(run)
        paths.write_json(tmp_path / "t_leg.json", {"backtest": {"EURUSD": r}})
    return card


def arm(*args):
    return extras.edge(["arm", "t_leg", "EURUSD", *args])


def test_arm_needs_a_passing_card(armable):
    with pytest.raises(cli.Refused, match="no sandbox run"):
        arm()
    armable(pf=1.05)
    with pytest.raises(cli.Refused, match="arming needs"):
        arm()
    armable(trades=12)
    with pytest.raises(cli.Refused, match="arming needs"):
        arm()
    armable(**{"from": "2020-01-01"})
    with pytest.raises(cli.Refused, match="whole history"):
        arm()
    armable()
    with pytest.raises(cli.Refused, match="not"):
        arm("n=5")
    out = arm("risk=0.1")
    assert out["armed"] == [{"edge": "t_leg", "market": "EURUSD", "params": {}, "risk_pct": 0.1}]


def test_arm_with_params_matching_the_card(armable):
    armable(params={"n": 5})
    assert arm("n=5")["armed"][0]["params"] == {"n": 5}
    assert extras.edge(["disarm", "t_leg"])["armed"] == []


def test_only_systematic_or_owner_arms(armable, monkeypatch):
    armable()
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    with pytest.raises(cli.Refused, match="only the systematic pod"):
        arm()
    monkeypatch.setenv("AURUM_DESK_ROLE", "")
    assert arm()["ok"]


# ---- playbooks ---------------------------------------------------------------------------------------------------------

def closed(pod, R, updated, n=1, **kw):
    """Closed ticket rows straight into the state the folds read."""
    return {f"{pod}{updated}{i}{R}": dict({"id": f"{pod}{updated}{i}{R}", "pod": pod, "status": "closed", "R": R,
                                          "updated": updated, "instrument": "EURUSD", "pnl": R * 10}, **kw)
            for i in range(n)}


def test_playbook_edit_and_rollback_keep_history():
    assert playbooks.edit("fxmacro", "v1 text", "seed") == 1
    assert playbooks.edit("fxmacro", "v2 text", "lessons") == 2
    assert playbooks.rollback("fxmacro", 1, "worse") == 3
    assert playbooks.show("fxmacro") == "v1 text"
    assert [r["v"] for r in playbooks.log("fxmacro")] == [1, 2, 3]
    with pytest.raises(ValueError):
        playbooks.edit("fxmacro", "x", "")
    with pytest.raises(ValueError):
        playbooks.rollback("fxmacro", 9, "no such")


def test_playbook_check_rolls_back_a_worse_version(monkeypatch):
    log = paths.PLAYBOOKS / "versions" / "fxmacro"
    log.mkdir(parents=True, exist_ok=True)
    (log / "v1.md").write_text("old", encoding="utf-8")
    (log / "v2.md").write_text("new", encoding="utf-8")
    paths.append_jsonl(log / "log.jsonl", {"v": 1, "t": "2026-08-01T00:00:00", "by": "x", "why": "seed"})
    paths.append_jsonl(log / "log.jsonl", {"v": 2, "t": "2026-09-01T00:00:00", "by": "x", "why": "edit"})
    state = {**closed("fxmacro", 1.0, "2026-08-10T00:00:00", 10), **closed("fxmacro", -0.5, "2026-09-10T00:00:00", 10)}
    t = dt.datetime(2026, 10, 21, 14)
    assert playbooks.check("fxmacro", state, t) == 3
    assert playbooks.show("fxmacro") == "old"
    assert playbooks.check("fxmacro", state, t) is None  # the rollback is the new current version, too young


def test_playbook_check_waits_for_trades():
    log = paths.PLAYBOOKS / "versions" / "metals"
    log.mkdir(parents=True, exist_ok=True)
    paths.append_jsonl(log / "log.jsonl", {"v": 1, "t": "2026-08-01T00:00:00", "by": "x", "why": "seed"})
    paths.append_jsonl(log / "log.jsonl", {"v": 2, "t": "2026-09-01T00:00:00", "by": "x", "why": "edit"})
    state = closed("metals", -1.0, "2026-09-10T00:00:00", 3)
    assert playbooks.check("metals", state, dt.datetime(2026, 10, 21)) is None


def test_playbook_edit_command_is_head_trader_or_owner(monkeypatch, tmp_path):
    f = tmp_path / "pb.md"
    f.write_text("rules", encoding="utf-8")
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    with pytest.raises(cli.Refused, match="only the head trader"):
        extras.playbook(["edit", "fxmacro", str(f), "why"])
    monkeypatch.setenv("AURUM_DESK_ROLE", "head-trader")
    assert extras.playbook(["edit", "fxmacro", str(f), "fold", "lessons"])["version"] == 1
    assert playbooks.log("fxmacro")[0]["why"] == "fold lessons"


# ---- the scorekeeper ---------------------------------------------------------------------------------------------------

def test_cited_winner_shares_credit():
    rows = [{"id": "T1", "pod": "fxmacro", "R": 2.0, "cites": ["b1", "b2"]},
            {"id": "T2", "pod": "fxmacro", "R": -1.0, "cites": ["b1"]}]
    board = [{"id": "b1", "pod": "metals"}, {"id": "b2", "pod": "indices"}]
    out = scorekeeper.credited(rows, board)
    assert out["fxmacro"] == [(1.5, "T1"), (-1.0, "T2")]
    assert out["metals"] == [(0.25, "T1")]
    assert out["indices"] == [(0.25, "T1")]


def test_own_citation_earns_nothing_extra():
    out = scorekeeper.credited([{"id": "T1", "pod": "fxmacro", "R": 2.0, "cites": ["b1"]}],
                               [{"id": "b1", "pod": "fxmacro"}])
    assert out == {"fxmacro": [(2.0, "T1")]}


def _cfg():
    return {"pods": {"systematic": {"base_share": 0.25}, "fxmacro": {"base_share": 0.2}, "metals": {"base_share": 0.15},
                     "indices": {"base_share": 0.15}, "event": {"base_share": 0.15}, "crypto": {"base_share": 0.1}}}


def _sc(shadow=0.1, **pods):
    return {"shadow_r_per_trade": shadow, "pods": {p: {"trades": n, "R_per_trade": r} for p, (n, r) in pods.items()}}


def test_allocation_keeps_base_for_thin_pods_and_stays_in_bounds():
    a = scorekeeper.allocate(_sc(fxmacro=(5, 3.0)), {}, _cfg())
    assert a["shares"]["fxmacro"] == pytest.approx(0.2, abs=0.01)
    a = scorekeeper.allocate(_sc(fxmacro=(40, 2.0), metals=(40, -1.0)), {}, _cfg())
    s = a["shares"]
    assert sum(s.values()) == pytest.approx(1, abs=1e-3)
    assert all(scorekeeper.FLOOR - 1e-6 <= v <= scorekeeper.CAP + 1e-6 for v in s.values())
    assert s["fxmacro"] > 0.2 and s["metals"] < 0.15


def test_allocation_moves_at_most_a_step():
    prev = {"shares": {"systematic": 0.25, "fxmacro": 0.2, "metals": 0.15, "indices": 0.15, "event": 0.15,
                       "crypto": 0.1}}
    raw = {}
    orig = scorekeeper._normalise
    scorekeeper._normalise = lambda target, fixed=(): raw.update(target) or orig(target, fixed)
    try:
        scorekeeper.allocate(_sc(fxmacro=(40, 5.0)), prev, _cfg())
    finally:
        scorekeeper._normalise = orig
    assert raw["fxmacro"] == pytest.approx(0.2 + scorekeeper.STEP)


def test_pod_below_shadow_six_weeks_is_paused():
    prev = {"weeks_below_shadow": {"metals": scorekeeper.PAUSE_WEEKS - 1}}
    a = scorekeeper.allocate(_sc(shadow=0.2, metals=(30, 0.1), fxmacro=(30, 0.5)), prev, _cfg())
    assert a["paused"] == ["metals"]
    assert a["shares"]["metals"] == 0.0
    assert a["weeks_below_shadow"]["fxmacro"] == 0
    assert sum(a["shares"].values()) == pytest.approx(1, abs=1e-3)
    assert (paths.INBOX / "pod_paused_metals.md").exists()


def test_bridge_sends_each_edge_once(monkeypatch, tmp_path):
    q = tmp_path / "queue.jsonl"
    monkeypatch.setattr(scorekeeper, "QUEUE", q)
    state = closed("fxmacro", 0.4, "2026-10-01T00:00:00", 30, edge="breakout", created="2026-09-01T00:00:00")
    state.update(closed("metals", -0.2, "2026-10-01T00:00:00", 40, edge="fade", created="2026-09-01T00:00:00"))
    assert scorekeeper.bridge(state) == ["desk-breakout-EURUSD"]
    assert scorekeeper.bridge(state) == []
    rows = paths.read_jsonl(q)
    assert len(rows) == 1 and rows[0]["source"] == "desk" and rows[0]["evidence"]["trades"] == 30


# ---- the live gate -----------------------------------------------------------------------------------------------------

def test_live_gate_not_started_before_phase_3():
    g = live_gate.evaluate(state={})
    assert not g["passed"]
    assert g["verdict"].startswith("not started")


def test_live_gate_flags_a_failed_stop(monkeypatch):
    from conftest import backdate_phase
    backdate_phase(90)
    t = clocks.now()
    state = closed("fxmacro", -2.0, (t - dt.timedelta(days=1)).isoformat())
    g = live_gate.evaluate(t, state)
    assert g["checks"]["code_faults"]["have"] == 1
    assert g["checks"]["weeks"]["ok"]
    assert not g["passed"]


# ---- the runner --------------------------------------------------------------------------------------------------------

def test_monitor_alert_lines_reach_the_owner(monkeypatch, cfg):
    monkeypatch.setattr(runner, "call", lambda *a: {"ok": True, "tokens": 10,
                                                    "result": "all fine\nALERT: terminal disconnected\nalert: dd 4%"})
    assert runner.run_agent("monitor", {"id": "j1", "kind": "monitor"}, cfg) == "ok"
    text = (paths.REPORTS / "ALERT.md").read_text(encoding="utf-8")
    assert "terminal disconnected" in text and "dd 4%" in text and "all fine" not in text


def test_prompt_has_guide_pod_and_role(monkeypatch):
    p = runner.prompt_for("fxmacro", {"id": "j1", "kind": "brief", "pods": ["fxmacro"]})
    assert "what every agent on it reads first" in p and "# You are a pod" in p and '"kind": "brief"' in p
    assert "# You are a pod" not in runner.prompt_for("monitor", {"id": "j2", "kind": "monitor"})
