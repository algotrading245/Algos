"""Owner 2026-11-02: the weekend build job, edge signals in the brief, the halves arm bar and the prebuilt edges."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from desk import allowance, cli, edges, extras, jobs, journal, paths, runner, sandbox, systematic, tick
from desk.edges import base
from desk.tests.test_allowance import ap  # noqa: F401  (fixture)
from desk.tests.test_extras import arm, armable  # noqa: F401  (fixture)

SECS = {"D1": 86400, "H4": 14400, "H1": 3600, "M15": 900, "M5": 300}
START = 1609459200  # 2021-01-01


def frame(tf, n, seed=1, px=1.1):
    """A random walk with independent wicks (symmetric wicks never make a pin bar)."""
    s = SECS[tf]
    t = np.arange(START, START + s * int(n * 1.5), s)
    t = t[base.weekday(t) < 5][:n]
    r = np.random.default_rng(seed)
    c = px * np.exp(np.cumsum(r.normal(0, 0.004 * np.sqrt(s / 86400), len(t))))
    o = np.r_[c[0], c[:-1]] * (1 + r.normal(0, 0.0003, len(t)))
    sc = 0.003 * np.sqrt(s / 86400) * c
    wu, wl = r.exponential(1, len(t)) * sc, r.exponential(1, len(t)) * sc
    return pd.DataFrame({"time": t, "open": o, "high": np.maximum(o, c) + wu, "low": np.minimum(o, c) - wl,
                         "close": c, "tick_volume": 100, "spread": 10})


# --- halves and the arm bar -------------------------------------------------------------------------------------

def test_halves_split_at_the_midpoint_in_time():
    tr = [{"t": 0, "r": 1.0}, {"t": 10, "r": -2.0}, {"t": 60, "r": 3.0}, {"t": 100, "r": 0.5}]
    h = sandbox.halves(tr)
    assert h == [-1.0, 3.5] and all(type(x) is float for x in h)
    assert sandbox.halves([]) == [0.0, 0.0]
    assert sandbox.stats([{"t": 0, "out": 1, "r": np.float64(1.0)}])["halves"] == [1.0, 0.0]


def test_arm_needs_both_halves_positive(armable):  # noqa: F811
    armable(halves=[-1.0, 5.0])
    with pytest.raises(cli.Refused, match="both halves positive"):
        arm()
    armable(halves=None)
    with pytest.raises(cli.Refused, match="no halves"):
        arm()
    armable(halves=[0.5, 5.0])
    assert arm()["armed"][0]["edge"] == "t_leg"


# --- the build budget -------------------------------------------------------------------------------------------

def test_build_status_has_its_own_weekly_dollars(cfg, ap, monkeypatch):  # noqa: F811
    cfg["budgets"]["build_weekly_usd"] = 0
    assert allowance.build_status(cfg)["over"] and "no build_weekly_usd" in allowance.build_status(cfg)["why"]
    cfg["budgets"]["build_weekly_usd"] = 8
    journal.log("agent_run", role="fxmacro", kind="build", tokens=100, usd=3.0)
    journal.log("agent_run", role="fxmacro", kind="brief", tokens=100, usd=50.0)  # pod runs do not count here
    st = allowance.build_status(cfg)
    assert st["used_usd"] == 3.0 and not st["over"]
    journal.log("agent_run", role="metals", kind="build", tokens=100, usd=5.5)
    st = allowance.build_status(cfg)
    assert st["over"] and "build dollars spent" in st["why"]


def test_build_runs_stay_out_of_the_pods_week(cfg, ap, monkeypatch):  # noqa: F811
    cfg["budgets"]["pod_weekly_usd"] = 15
    monkeypatch.setenv("AURUM_DESK_NOW", "2026-10-19T14:00:00")  # Monday
    journal.log("agent_run", role="fxmacro", kind="brief", tokens=100, usd=12.0)
    journal.log("agent_run", role="fxmacro", kind="build", tokens=100, usd=7.0)
    monkeypatch.setenv("AURUM_DESK_NOW", "2026-10-21T14:00:00")
    assert allowance.fit(cfg)["used_usd"] == 12.0


# --- the build job ----------------------------------------------------------------------------------------------

def test_build_job_runs_each_pod_and_stops_on_budget(cfg, monkeypatch):
    calls = []
    answers = iter(["ok", "budget", "ok"])

    def fake(role, job, cfg_):
        calls.append(role)
        return next(answers)
    monkeypatch.setattr(runner, "run_agent", fake)
    monkeypatch.setattr(runner, "refresh_intel", lambda cfg_: None)
    jid = jobs.queue("build", name="build", pods=["fxmacro", "metals", "indices"])
    runner.run_job(jobs.fold()[jid], cfg)
    assert calls == ["fxmacro", "metals"] and jobs.fold()[jid]["status"] == "done"

    monkeypatch.setattr(runner, "run_agent", lambda role, job, cfg_: "budget")
    jid = jobs.queue("build", name="build", pods=["fxmacro", "metals"])
    assert runner.run_job(jobs.fold()[jid], cfg) == "skipped" and jobs.fold()[jid]["why"] == "budget"


def test_build_run_refused_when_its_dollars_are_spent(cfg, monkeypatch):
    monkeypatch.setattr(allowance, "build_status", lambda cfg_, t=None: {"over": True, "why": "build dollars spent"})
    monkeypatch.setattr(runner, "call", lambda *a, **k: pytest.fail("a spent build budget must not call claude"))
    assert runner.run_agent("fxmacro", {"id": "j1", "kind": "build"}, cfg) == "budget"
    row = journal.recent(["agent_skipped"], 1)[-1]
    assert row["why"] == "budget" and row["detail"] == "build dollars spent"


def test_build_queued_saturday_morning(cfg):
    ev = next(e for e in cfg["schedule"] if e["kind"] == "build")
    assert ev["days"] == [5] and cfg["budgets"]["build_weekly_usd"] > 0
    cfg = dict(cfg, schedule=[ev])
    sat = dt.datetime.fromisoformat("2026-10-24T08:05:00+00:00")
    assert tick.schedule(None, cfg, {}, sat) == ["build"]
    job = next(j for j in jobs.pending() if j["kind"] == "build")
    assert job["pods"] and set(job["pods"]) <= set(cfg["pods"])
    assert tick.schedule(None, cfg, {}, sat + dt.timedelta(minutes=5)) == [] or jobs.has_pending("build")
    assert sum(j["kind"] == "build" for j in jobs.pending()) == 1


# --- edge signals in the brief ----------------------------------------------------------------------------------

class FakeBroker:
    def __init__(self, frames):
        self.frames = frames

    def resolve(self, market):
        return market if market in self.frames else None

    def bars(self, sym, tf, n):
        return self.frames[sym].tail(n).reset_index(drop=True)


def _always(side):
    def fn(df, p, ctx):
        n = len(df) - 1
        px = float(df["close"].iloc[-1])
        return [base.sig(n, side, px * (0.99 if side == "buy" else 1.01), "test")]
    return fn


def test_firing_lists_signals_armed_first_and_respects_reference_markets(monkeypatch):
    spec = {"tf": "H1", "pod": "systematic", "bars": 50, "needs": [], "defaults": {}, "card": ""}
    monkeypatch.setattr(base, "EDGES", {
        "t_ref": dict(spec, name="t_ref", markets=["EURUSD"], kind="reference", fn=_always("buy")),
        "t_leg": dict(spec, name="t_leg", markets=["EURUSD"], kind="leg", fn=_always("sell")),
        "t_bad": dict(spec, name="t_bad", markets=["EURUSD"], kind="leg",
                      fn=lambda df, p, ctx: 1 / 0),
    })
    monkeypatch.setattr(edges, "EDGES", base.EDGES, raising=False)
    monkeypatch.setattr(edges, "load_new", lambda: None)
    monkeypatch.setattr(systematic, "state", lambda: {"armed": [{"edge": "t_leg", "market": "GBPUSD", "pod": "fxmacro"}],
                                                      "seen": {}})
    b = FakeBroker({"EURUSD": frame("H1", 200), "GBPUSD": frame("H1", 200, seed=2, px=1.3)})
    out = extras.firing(b, ["EURUSD", "GBPUSD"])
    got = [(r["market"], r["edge"]) for r in out["rows"]]
    assert ("GBPUSD", "t_ref") not in got  # a reference edge stays on its own markets
    assert got[0] == ("GBPUSD", "t_leg") and out["rows"][0]["armed_by"] == ["fxmacro"]
    assert ("EURUSD", "t_ref") in got and ("EURUSD", "t_leg") in got
    assert all(r["bars_ago"] == 0 and r["side"] in ("buy", "sell") for r in out["rows"])
    assert out["found"] == out["shown"] == 3


# --- the prebuilt reference edges -------------------------------------------------------------------------------

REFS = sorted(n for n, e in edges.EDGES.items() if e.get("kind") == "reference")
BARS = {"D1": 1500, "H4": 3000, "H1": 5000, "M15": 12000, "M5": 25000}


def test_at_least_50_reference_edges_with_cards_and_defaults():
    assert len(REFS) >= 50
    for n in REFS:
        e = edges.EDGES[n]
        assert e["pod"] == "library" and e["card"].strip() and isinstance(e["defaults"], dict), n
        assert e["markets"] and e["tf"] in SECS, n


@pytest.mark.parametrize("name", REFS)
def test_reference_edge_trades_on_synthetic_bars(name):
    e = edges.EDGES[name]
    m = e["markets"][0]
    df = frame(e["tf"], BARS[e["tf"]], px={"US500": 4500.0, "XAUUSD": 1900.0}.get(m, 1.1))
    out = edges.run(name, df, {}, {"market": m})
    opens = [s for s in out if not s.get("close")]
    assert opens, f"{name} gave no signal"
    for s in opens:
        assert s["side"] in ("buy", "sell") and isinstance(s["i"], (int, np.integer)) and np.isfinite(s["stop"])
        assert 0 <= s["i"] < len(df)
    assert sandbox.simulate(df, out, float(df["close"].iloc[-1]) * 0.0001), f"{name} made no trade"
