"""Owner 2026-11-02: view sim, the 10,000-path ticket simulator and the edge-outcome resampler."""
import numpy as np
import pytest

from desk import cli, sandbox, sim
from desk.edges import base
from desk.tests.test_build_1102 import frame


@pytest.fixture
def hist(monkeypatch):
    df = frame("H1", 6000, seed=3)
    monkeypatch.setattr(base, "hist_bars", lambda sym, tf, cfg=None: df)
    return df


def test_neutral_paths_match_the_random_walk_odds(hist):
    rel = sim.unit_bars(hist)
    assert rel.shape[1] == 3 and np.isfinite(rel).all()
    # symmetric 1R / 1R on a long clock: close to a coin flip, stop a little ahead (same-bar ties go to the stop)
    o = sim.odds(rel, 1.0, 0.99, 1.01, 1500, 0.002, n=4000)
    assert abs(o["target"] + o["stop"] + o["neither"] - 1) < 0.002
    assert 0.4 <= o["target"] <= 0.55 and o["neither"] < 0.05
    # 1.5R target: near 1 / (1 + 1.5) = 40%, and a trade with no edge has an EV near zero before costs
    o = sim.odds(rel, 1.0, 0.99, 1.015, 1500, 0.002, n=4000)
    assert 0.3 <= o["target"] <= 0.45 and abs(o["ev_r"]) < 0.15


def test_a_short_clock_leaves_paths_at_neither(hist):
    rel = sim.unit_bars(hist)
    o = sim.odds(rel, 1.0, 0.98, 1.03, 3, 0.001, n=2000)
    assert o["neither"] > 0.9 and o["r_at_deadline"] is not None


def test_sell_side_and_bad_levels(hist):
    rel = sim.unit_bars(hist)
    o = sim.odds(rel, 1.0, 1.01, 0.985, 1500, 0.002, n=2000)
    assert 0.3 <= o["target"] <= 0.45
    with pytest.raises(ValueError, match="opposite sides"):
        sim.odds(rel, 1.0, 1.01, 1.02, 10, 0.002)


def test_ticket_reports_the_baseline_and_the_atr_source(hist, cfg):
    r = sim.ticket("EURUSD", 1.1, 1.095, 1.1075, 24, cfg=cfg, n=2000)
    assert r["side"] == "buy" and r["rr"] == 1.5 and r["random_walk_no_deadline"] == 0.4
    assert r["tf"] == "H1" and r["bars"] == 24 and "not live" in r["atr_from"]
    assert set(r["neutral"]) >= {"target", "stop", "neither", "ev_r"} and "needs a reason" in r["read"]
    r = sim.ticket("EURUSD", 1.1, 1.095, 1.1075, 24, atr_now=0.002, tf="H1", cfg=cfg, n=1000, atr_from="live terminal")
    assert r["atr"] == 0.002 and r["atr_from"] == "live terminal" and r["stop_atr"] == 2.5


def test_view_sim_through_the_cli(hist, monkeypatch):
    monkeypatch.setattr(cli, "_live_atr", lambda sym, tf: None)
    r = cli.view(["sim", "EURUSD", "1.1", "1.095", "1.1075", "24", "n=1000"])
    assert r["symbol"] == "EURUSD" and r["paths"] == 1000
    r = cli.view(["sim", "EURUSD", "1.1", "1.095", "1.1075", "24", "atr=0.003", "n=1000"])
    assert r["atr_from"] == "given" and r["atr"] == 0.003
    with pytest.raises(cli.Refused, match="view sim"):
        cli.view(["sim", "EURUSD", "1.1"])
    with pytest.raises(cli.Refused, match="opposite sides"):
        cli.view(["sim", "EURUSD", "1.1", "1.11", "1.12", "24", "atr=0.001", "n=100"])


def _trades(rs):
    return [{"t": i * 3600, "out": i * 3600 + 60, "side": "buy", "slot": 0, "r": r, "why": "x"} for i, r in enumerate(rs)]


def test_edge_outcomes_tell_a_losing_run_from_a_broken_edge(monkeypatch):
    rs = [1.6] * 40 + [-1.0] * 60  # a thin edge: 40% winners at 1.6R, +0.04R a trade
    seen = {}

    def fake(name, market, params=None, cfg=None, start=None, end=None):
        seen.update(name=name, market=market, params=params)
        return _trades(rs)
    monkeypatch.setattr(sandbox, "edge_trades", fake)
    r = sim.edge("t_leg", "EURUSD", 20, n=4000, cfg={})
    assert r["history_trades"] == 100 and r["avg_r"] == 0.04
    p = r["total_r"]
    assert p["p5"] < p["p25"] < p["p50"] < p["p75"] < p["p95"] and p["p5"] < 0
    assert 0.2 < r["p_loss"] < 0.8 and r["losing_streak"]["p95"] >= 4 and r["max_dd_r"]["p95"] > 0
    assert sim.edge("t_leg", "EURUSD", 20, live=-3, n=4000, cfg={})["live"]["read"].startswith("inside")
    assert "broken" in sim.edge("t_leg", "EURUSD", 20, live=-15, n=4000, cfg={})["live"]["read"]
    r = cli.view(["sim", "edge", "t_leg", "EURUSD", "n=50", "live=-2", "fast=10"])
    assert r["next"] == 50 and seen["params"] == {"fast": 10} and "live" in r
    monkeypatch.setattr(sandbox, "edge_trades", lambda *a, **k: _trades([1.0] * 5))
    with pytest.raises(cli.Refused, match="too few"):
        cli.view(["sim", "edge", "t_leg", "EURUSD"])


def test_edge_trades_matches_run_edge(cfg, monkeypatch):
    from desk import edges
    df = frame("D1", 1500, seed=5)
    monkeypatch.setattr(base, "hist_bars", lambda sym, tf, cfg=None: df)
    name = next(n for n, e in edges.EDGES.items() if e.get("kind") == "reference" and e["tf"] == "D1"
                and not e["needs"])
    tr = sandbox.edge_trades(name, "EURUSD", cfg=cfg)
    st = sandbox.run_edge(name, "EURUSD", cfg=cfg, save=False)["EURUSD"]
    assert st["trades"] == len(tr) and st["total_r"] == round(sum(x["r"] for x in tr), 2)


def test_tweak_changes_one_numeric_default():
    d = {"n": 20, "k": 2.0, "on": True, "mode": "x"}
    seen = [sandbox._tweak(d, i) for i in range(4)]
    assert all(len(x) == 1 and next(iter(x)) in ("n", "k") for x in seen)
    assert all(d[p] != v for x in seen for p, v in x.items())
    assert sandbox._tweak({"mode": "x"}, 0) == {}


def test_weekly_task_is_fixed_for_the_week_prefers_fresh_and_tracks_done(cfg, monkeypatch):
    import datetime as dt
    from desk import clocks, journal
    owns = [m for m in cfg["instruments"] if cfg["instruments"][m].get("cost") is not None
            and cfg["instruments"][m].get("hist")][:2]
    assert owns
    t = clocks.now()
    a = sandbox.weekly_task("metals", owns, t, cfg)
    b = sandbox.weekly_task("metals", owns, t + dt.timedelta(days=1), cfg)
    assert (a["edge"], a["market"], a["tweak"]) == (b["edge"], b["market"], b["tweak"]) and a["market"] in owns
    assert a["steps"][0] == f"edge sandbox {a['edge']} {a['market']}" and not a["done"]
    card = sandbox.CARDS / f"{a['edge']}.json"
    if card.exists():
        assert a["market"] not in (sandbox.paths.read_json(card, {}).get("backtest") or {})
    assert sandbox.weekly_task("metals", [], t, cfg) is None
    # a sandbox run by another pod, or of another edge, does not count; the pod's own run does
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    journal.log("sandbox", edge=a["edge"], market=a["market"])
    monkeypatch.setenv("AURUM_DESK_ROLE", "metals")
    journal.log("sandbox", edge="not_" + a["edge"], market=a["market"])
    assert not sandbox.weekly_task("metals", owns, t, cfg)["done"]
    journal.log("sandbox", edge=a["edge"], market=a["market"])
    r = sandbox.weekly_task("metals", owns, t, cfg)
    assert r["done"] and r["runs"] == 1


def test_the_brief_carries_the_sandbox_task():
    from desk import brief
    text = brief.build("metals")
    assert "Your sandbox task this week" in text and "edge sandbox" in text
