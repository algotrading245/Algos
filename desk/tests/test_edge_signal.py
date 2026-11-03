import datetime as dt

import pandas as pd
import pytest

from desk import broker, cli, edges, extras, paths, systematic
from desk.edges import base

T0 = dt.datetime(2026, 10, 20, 0, tzinfo=dt.timezone.utc)


class FakeBroker:
    """H1 bars of a rising path, in server time like the real broker. Counts bars() calls."""

    def __init__(self, n=40, missing=()):
        closes = [100 + i for i in range(n)]
        self.df = pd.DataFrame({"time": [broker.utc_to_server_epoch(T0 + dt.timedelta(hours=i)) for i in range(n)],
                                "open": closes, "high": [c + 0.5 for c in closes], "low": [c - 0.5 for c in closes],
                                "close": closes})
        self.missing, self.calls = set(missing), 0

    def connected(self):
        return True

    def resolve(self, sym):
        return None if sym in self.missing else sym

    def bars(self, sym, tf, n):
        self.calls += 1
        return self.df

    def shutdown(self):
        pass


@pytest.fixture
def every_k(monkeypatch):
    """A dummy edge: a long every k bars, a close on the bar after; and one that always fails."""
    def fn(df, p, ctx):
        out = []
        for i in range(0, len(df), p["k"]):
            out.append(base.sig(i, "long", df["low"].iloc[i] - 1, f"bar {i}", targets=[[df["close"].iloc[i] + 3, 1.0]]))
            if i + 1 < len(df):
                out.append(base.close_sig(i + 1, "next bar"))
        return out

    def boom(df, p, ctx):
        raise RuntimeError("bad maths")

    monkeypatch.setattr(edges, "EDGES", {})
    monkeypatch.setattr(base, "EDGES", edges.EDGES)
    base.edge("everyk", ["XAUUSD", "EURUSD"], "H1", bars=40, defaults={"k": 13}, card="test")(fn)
    base.edge("boom", ["XAUUSD"], "H1", bars=40)(boom)
    monkeypatch.setattr(edges, "load_new", lambda: None)


def test_signal_reads_now_and_recent_without_writing(every_k):
    b = FakeBroker()  # last bar index 39: 39 % 13 == 0, so a long fires on it
    before = sorted(p.name for p in paths.STATE.rglob("*")) if paths.STATE.exists() else []
    r = extras.signal(b, "everyk", "xauusd", armed=[{"edge": "everyk", "market": "XAUUSD", "pod": "metals"}])
    assert r["market"] == "XAUUSD" and r["price"] == 139.0 and r["armed_by"] == ["metals"]
    assert r["now"] == [{"bar": "2026-10-21T15:00+00:00", "bars_ago": 0, "side": "long", "stop": 137.5,
                         "targets": [[142.0, 1.0]], "why": "bar 39"}]
    assert [x["bars_ago"] for x in r["recent"]] == [13, 12, 0]  # within 20 bars: the long at 26, its close, 39
    assert r["recent"][1]["close"] is True and "side" not in r["recent"][1]
    assert extras.signal(b, "everyk", "XAUUSD", {"k": 7}, armed=[])["now"] == []  # 39 % 7 != 0; params pass through
    assert extras.signal(b, "everyk", "XAUUSD", {"k": 7}, lookback=2, armed=[])["recent"] == []
    after = sorted(p.name for p in paths.STATE.rglob("*")) if paths.STATE.exists() else []
    assert after == before  # read-only


def test_signal_all_caches_bars_and_reports_errors(every_k):
    b = FakeBroker()
    r = extras.signal_all(b, "XAUUSD")
    assert list(r["now"]) == ["everyk"] and r["errors"]["boom"] == "RuntimeError: bad maths"
    assert b.calls == 1  # both edges read one H1 frame
    with pytest.raises(ValueError, match="does not resolve"):
        extras.signal(FakeBroker(missing={"XAUUSD"}), "everyk", "XAUUSD", armed=[])


def test_cli_signal_defaults_to_the_edge_markets(every_k, monkeypatch):
    b = FakeBroker(missing={"EURUSD"})
    monkeypatch.setattr(cli, "_broker", lambda: b)
    monkeypatch.setenv("AURUM_DESK_ROLE", "crypto")  # any pod may look
    out = cli.COMMANDS["edge"](["signal", "everyk", "k=13"])
    assert out["XAUUSD"]["now"][0]["side"] == "long" and "does not resolve" in out["EURUSD"]["error"]
    assert out["XAUUSD"]["armed_by"] == []  # systematic's default legs are not this edge
    assert set(cli.COMMANDS["edge"](["signal", "all", "XAUUSD", "lookback=5"])) == {"market", "now", "recent", "quiet",
                                                                                    "errors"}
    with pytest.raises(cli.Refused, match="no edge"):
        cli.COMMANDS["edge"](["signal", "nosuch"])
    with pytest.raises(cli.Refused, match="signal all MARKET"):
        cli.COMMANDS["edge"](["signal", "all"])
    assert systematic.state()["armed"]  # untouched defaults
