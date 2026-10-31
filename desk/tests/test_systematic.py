import numpy as np
import pandas as pd
import pytest

import datetime as dt

from conftest import backdate_phase, ticket

from desk import broker, clocks, paths, risk_gate, sandbox, systematic, tickets
from desk.edges import base


def frame(n=40, start=1_790_000_000, step=3600, px=1.10):
    t = start + np.arange(n) * step
    c = px + np.zeros(n)
    return pd.DataFrame({"time": t, "open": c, "high": c + 0.001, "low": c - 0.001, "close": c, "spread": 10})


@pytest.fixture
def leg(monkeypatch):
    """A test leg that emits out["sigs"] on the last bar."""
    out = {"sigs": []}

    def fn(df, p, ctx):
        n = len(df) - 1
        return [dict(s, i=n) for s in out["sigs"]]
    monkeypatch.setitem(base.EDGES, "t_leg", {"name": "t_leg", "markets": ["EURUSD"], "tf": "H1", "pod": "systematic",
                                              "kind": "leg", "bars": 40, "needs": [], "defaults": {}, "card": "",
                                              "fn": fn})
    paths.write_json(systematic.FILE, {"armed": [{"edge": "t_leg", "market": "EURUSD", "params": {},
                                                  "risk_pct": 0.25}]})
    return out


def test_entry_becomes_an_armed_ticket_once(b, cfg, leg):
    b.bar_frames[("EURUSD", "H1")] = frame()
    leg["sigs"] = [base.sig(0, "buy", 1.095, "test long", targets=[[1.11, 1.0]], exit_t=1_790_200_000,
                            trail_atr=2.0, slot=0, weight=0.5)]
    t = clocks.now()
    out = systematic.run(b, cfg, t)
    assert list(out) == ["t_leg EURUSD"]
    tk = list(tickets.live().values())[0]
    assert tk["status"] == "approved" and tk["pod"] == "systematic" and tk["edge"] == "t_leg" and tk["slot"] == 0
    assert tk["risk_pct"] == 0.125 and tk["trail"] == {"atr": 2.0, "tf": "H1", "n": 14}
    assert tk["time_stop"] == broker.server_epoch_to_utc(1_790_200_000).isoformat(timespec="seconds")
    assert systematic.run(b, cfg, t) == {}  # same bar: not read twice
    b.bar_frames[("EURUSD", "H1")] = frame(41)
    assert systematic.run(b, cfg, t) == {}  # new bar, same signal: the slot is taken
    assert len(tickets.live()) == 1


def test_a_leg_trades_as_the_pod_that_armed_it(b, cfg, leg):
    paths.write_json(systematic.FILE, {"armed": [{"edge": "t_leg", "market": "EURUSD", "params": {},
                                                  "risk_pct": 0.25, "pod": "fxmacro"}]})
    b.bar_frames[("EURUSD", "H1")] = frame()
    leg["sigs"] = [base.sig(0, "buy", 1.095, "test long", slot=0)]
    systematic.run(b, cfg, clocks.now())
    tk = list(tickets.live().values())[0]
    assert tk["pod"] == "fxmacro" and tk["arm"] and tk["status"] == "approved"
    leg["sigs"] = [base.close_sig(0, "out", slot=0)]
    b.bar_frames[("EURUSD", "H1")] = frame(41)
    systematic.run(b, cfg, clocks.now())
    assert tickets.fold()[tk["id"]]["status"] == "cancelled"


def test_needs_reads_any_market(b, cfg, monkeypatch):
    assert base.need("spx_d1") == ("US500", "D1") and base.need("XAUUSD_H4") == ("XAUUSD", "H4")
    with pytest.raises(ValueError):
        base.need("XAUUSD_D2")
    e = {"needs": ["XAUUSD_D1"], "bars": 40}
    monkeypatch.setattr(b, "resolve", lambda s: s)
    b.bar_frames[("XAUUSD", "D1")] = frame(5, px=2000.0)
    assert len(systematic.context(b, e, "EURUSD")["XAUUSD_D1"]) == 5
    monkeypatch.setattr(base, "hist_bars", lambda sym, tf, cfg=None: (sym, tf))
    assert sandbox.context(e, "EURUSD")["XAUUSD_D1"] == ("XAUUSD", "D1")


def test_exit_rule_closes_open_and_cancels_unplaced(b, cfg, leg):
    t = clocks.now()
    b.bar_frames[("EURUSD", "H1")] = frame()
    leg["sigs"] = [base.sig(0, "buy", 1.095, "a", slot=0), base.sig(0, "buy", 1.095, "b", slot=1)]
    systematic.run(b, cfg, t)
    ids = {v["slot"]: v["id"] for v in tickets.live().values()}
    tickets.placed(ids[0], order=1, volume=0.01)
    tickets.opened(ids[0], position=2)
    b.bar_frames[("EURUSD", "H1")] = frame(41)
    leg["sigs"] = [base.close_sig(0, "band cross", slot=0), base.close_sig(0, "band cross", slot=1)]
    systematic.run(b, cfg, t)
    st = tickets.fold()
    assert st[ids[0]]["close_request"] == "band cross" and st[ids[0]]["status"] == "open"
    assert st[ids[1]]["status"] == "cancelled"


def test_inactive_before_an_account(b, cfg, leg):
    paths.write_json(systematic.phase.FILE, {})
    b.bar_frames[("EURUSD", "H1")] = frame()
    leg["sigs"] = [base.sig(0, "buy", 1.095, "x")]
    assert systematic.run(b, cfg, clocks.now()) == {}
    assert not tickets.live()


def test_benchmarks_cannot_be_armed():
    with pytest.raises(ValueError):
        systematic.arm("donchian_trend", "EURUSD")
    armed = systematic.arm("grid", "AUDCAD", {"step": 1.2})
    assert {"edge": "grid", "market": "AUDCAD", "params": {"step": 1.2}, "risk_pct": 0.25, "pod": "systematic"} in armed
    assert all(a["edge"] != "grid" for a in systematic.disarm("grid"))


def test_default_armed_legs_exist_and_are_legs():
    for name, m in systematic.DEFAULT_ARMED:
        e = base.EDGES[name]
        assert e["kind"] == "leg" and m in e["markets"]


def gate_tk(**over):
    t = ticket(pod="systematic", edge="grid", arm=True, **over)
    t.setdefault("entry", {"type": "market"})
    t.setdefault("targets", [])
    return t


def held(slot, edge="grid"):
    tid, errs = tickets.new(**ticket(pod="systematic", edge=edge, slot=slot))
    assert not errs, errs
    tickets.approve(tid)
    tickets.placed(tid, order=1, volume=0.01, risk_used=0.05)
    tickets.opened(tid, position=2, risk_now=0.05)
    return tid


def test_gate_allows_a_grid_level_per_slot(b, cfg):
    held(0)
    assert risk_gate.check(gate_tk(slot=1), b, cfg)["ok"]
    g = risk_gate.check(gate_tk(slot=0), b, cfg)
    assert not g["ok"] and "already holds" in g["why"]


def test_gate_keeps_one_position_per_pod_across_edges(b, cfg):
    held(0, edge="fix")
    g = risk_gate.check(gate_tk(slot=1), b, cfg)
    assert not g["ok"] and "already holds" in g["why"]


def test_shadow_benchmark_counts_only_since_day0(b, cfg):
    n = 400
    t = clocks.now()
    t0 = broker.utc_to_server_epoch(t) // 86400 * 86400 - n * 86400
    rng = np.random.default_rng(1)
    c = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    b.bar_frames[("EURUSD", "D1")] = pd.DataFrame({"time": t0 + np.arange(n) * 86400, "open": c, "high": c * 1.004,
                                                   "low": c * 0.996, "close": c, "spread": 10})
    s = systematic.shadow(b, cfg, t, force=True)  # day 0 is today: nothing yet
    assert s["since"] and all(v["EURUSD"]["trades"] == 0 for v in s["edges"].values())
    backdate_phase(300)
    s = systematic.shadow(b, cfg, t, force=True)
    assert sum(v["EURUSD"]["trades"] for v in s["edges"].values()) > 0
    assert systematic.shadow(b, cfg, t + dt.timedelta(hours=1))["t"] == s["t"]  # not rebuilt within 6 hours


def test_index_costs_scale_with_price():
    df = pd.DataFrame({"close": [1000.0, 2000.0, 4000.0]})
    assert list(sandbox.costs(df, 2.0, "index")) == [0.5, 1.0, 2.0]
    assert list(sandbox.costs(df, 2.0, "fx")) == [2.0, 2.0, 2.0]


def test_sandbox_close_signal_and_weight():
    df = frame(10, step=3600)
    df.loc[5:, ["open", "high", "low", "close"]] = 1.11
    df.loc[5:, "high"] = 1.111
    sigs = [base.sig(1, "buy", 1.09, "in", weight=0.5), base.close_sig(5, "out")]
    tr = sandbox.simulate(df, sigs, 0.0)
    assert len(tr) == 1 and tr[0]["why"] == "rule"
    assert tr[0]["r"] == pytest.approx(0.5 * (1.11 - 1.10) / (1.10 - 1.09))
