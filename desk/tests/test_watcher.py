import datetime as dt

import pandas as pd
import pytest

from desk import broker, edges, jobs, journal, market_model as mm, phase, watcher
from desk.edges import base

T0 = dt.datetime(2026, 10, 20, 0, tzinfo=dt.timezone.utc)


class FakeBroker:
    """40 rising H1 bars in server time (TR 1.5 each), and a mid the test moves."""

    def __init__(self, n=40, missing=()):
        closes = [100 + i for i in range(n)]
        self.df = pd.DataFrame({"time": [broker.utc_to_server_epoch(T0 + dt.timedelta(hours=i)) for i in range(n)],
                                "open": closes, "high": [c + 0.5 for c in closes], "low": [c - 0.5 for c in closes],
                                "close": closes})
        self.missing, self.mid = set(missing), 140.0

    def resolve(self, sym):
        return None if sym in self.missing else sym

    def tick(self, sym):
        return {"bid": self.mid - 0.05, "ask": self.mid + 0.05, "time": 0}

    def bars(self, sym, tf, n):
        return self.df


@pytest.fixture
def every_k(monkeypatch):
    def fn(df, p, ctx):
        return [base.sig(i, "long", df["low"].iloc[i] - 1, f"bar {i}") for i in range(0, len(df), p["k"])]

    monkeypatch.setattr(edges, "EDGES", {})
    monkeypatch.setattr(base, "EDGES", edges.EDGES)
    base.edge("everyk", ["XAUUSD"], "H1", bars=40, defaults={"k": 13}, card="test")(fn)
    monkeypatch.setattr(edges, "load_new", lambda: None)


def wakes(pod):
    return [j for j in jobs.fold().values() if j["kind"] == "wake" and j["pod"] == pod]


def test_watcher_wakes_on_levels_edges_and_shocks_once_each(cfg, every_k):
    pod = phase.pods_active(cfg)[0]
    mm.set_market(pod, "XAUUSD", bias="up", levels="150,160", edges="everyk")
    b = FakeBroker()

    out = watcher.run(b, cfg)  # first pass: no last mid yet; everyk fires on bar 39
    assert [r["kind"] for r in out[pod]] == ["edge"] and out[pod][0]["signals"][0]["side"] == "long"
    w = wakes(pod)
    assert len(w) == 1 and w[0]["watch"][0]["edge"] == "everyk" and w[0]["triggers"] == []
    jobs.mark(w[0]["id"], "done")

    b.mid = 151.0  # crosses 150 up; the same bar, so the edge stays quiet
    out = watcher.run(b, cfg)
    assert out[pod] == [{"kind": "level", "market": "XAUUSD", "level": 150.0, "from": 140.0, "price": 151.0,
                         "dir": "up"}]
    assert len(wakes(pod)) == 2

    b.mid = 149.0  # back through 150: that level already fired today
    assert watcher.run(b, cfg) == {}

    b.df.loc[b.df.index[-1], "high"] += 10  # a range of 11 against an ATR of 1.5
    out = watcher.run(b, cfg)
    assert out[pod][0]["kind"] == "shock" and out[pod][0]["range_atr"] > 2.5
    assert len(wakes(pod)) == 2  # the level wake still waits: no second job, the journal keeps what fired
    assert journal.recent(["watch_fired"], 1)[-1]["watch"][0]["kind"] == "shock"
    assert watcher.run(b, cfg) == {}


def test_watcher_skips_what_does_not_resolve_and_paused_pods(cfg, every_k):
    pods = phase.pods_active(cfg)
    mm.set_market(pods[0], "XAUUSD", bias="up", edges="everyk")
    assert watcher.run(FakeBroker(missing={"XAUUSD"}), cfg) == {}
    from desk import paths
    paths.write_json(phase.ALLOC, {"paused": [pods[0]]})
    assert watcher.run(FakeBroker(), cfg) == {}
