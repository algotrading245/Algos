import datetime as dt
import json

import pandas as pd
import pytest

from desk import broker, cli, extras, forecasts, paths, scorekeeper  # noqa: F401  extras registers the command
from desk.brief import build

T0 = dt.datetime(2026, 10, 21, 14, 0, tzinfo=dt.timezone.utc)  # the desk's clock is aware UTC


class FakeBroker:
    """M15 bars of one price path from T0, in server time like the real broker."""

    def __init__(self, closes, start=T0):
        self.df = pd.DataFrame({"time": [broker.utc_to_server_epoch(start + dt.timedelta(minutes=15 * i))
                                         for i in range(len(closes))], "close": closes})

    def connected(self):
        return True

    def resolve(self, sym):
        return sym

    def bars(self, sym, tf, n):
        return self.df

    def shutdown(self):
        pass


def test_new_validates():
    for bad in [("fxmacro", "EURUSD", "sideways", 0.6, 4), ("fxmacro", "EURUSD", "up", 0.4, 4),
                ("fxmacro", "EURUSD", "up", 1.0, 4), ("fxmacro", "EURUSD", "up", 0.6, 0.5),
                ("fxmacro", "EURUSD", "up", 0.6, 200), ("nopod", "EURUSD", "up", 0.6, 4)]:
        with pytest.raises(ValueError):
            forecasts.new(*bad, why="x", level=1.08, t=T0)
    with pytest.raises(ValueError):
        forecasts.new("fxmacro", "EURUSD", "up", 0.6, 4, "  ", level=1.08, t=T0)


def test_open_cap():
    for _ in range(forecasts.MAX_OPEN):
        forecasts.new("metals", "XAUUSD", "up", 0.6, 4, "why", level=2400, t=T0)
    with pytest.raises(ValueError, match="open calls"):
        forecasts.new("metals", "XAUUSD", "up", 0.6, 4, "why", level=2400, t=T0)


def test_grade_and_skill():
    up = forecasts.new("fxmacro", "EURUSD", "up", 0.8, 2, "dovish Fed", level=1.0800, t=T0)
    down = forecasts.new("fxmacro", "EURUSD", "down", 0.7, 2, "risk off", level=1.0800, t=T0)
    later = forecasts.new("fxmacro", "EURUSD", "up", 0.6, 48, "longer", level=1.0800, t=T0)
    b = FakeBroker([1.0790 + 0.0002 * i for i in range(20)])  # rises through the level
    assert forecasts.grade(b, T0 + dt.timedelta(hours=3)) == 2
    rows = {f["id"]: f for f in forecasts.all_rows()}
    assert rows[up["id"]]["outcome"] == 1 and rows[up["id"]]["brier"] == pytest.approx(0.04)
    assert rows[down["id"]]["outcome"] == 0 and rows[down["id"]]["brier"] == pytest.approx(0.49)
    assert rows[later["id"]]["status"] == "open"
    # the bar taken is the first at or after the due time: T0 + 2h is bar 8
    assert rows[up["id"]]["close"] == pytest.approx(1.0790 + 0.0016)
    s = forecasts.skill("fxmacro", T0 + dt.timedelta(hours=3))
    raw = 1 - (0.04 + 0.49) / 2 / 0.25
    assert s["graded"] == 2 and s["open"] == 1 and s["hit"] == 0.5
    assert s["skill_raw"] == pytest.approx(raw, abs=1e-3) and s["skill"] == pytest.approx(raw * 2 / 22, abs=1e-3)
    assert forecasts.grade(b, T0 + dt.timedelta(hours=3)) == 0  # graded once


def test_unsettled_waits_then_voids():
    f = forecasts.new("indices", "US500", "up", 0.6, 2, "x", level=5000, t=T0)
    short = FakeBroker([5000.0] * 4)  # bars stop before the due time
    assert forecasts.grade(short, T0 + dt.timedelta(hours=3)) == 0
    assert forecasts.open_for("indices")[0]["id"] == f["id"]
    assert forecasts.grade(short, T0 + dt.timedelta(days=11)) == 1
    assert forecasts.all_rows()[0]["status"] == "void"
    assert forecasts.skill("indices", T0 + dt.timedelta(days=11))["graded"] == 0


def test_cli_pod_writes_as_itself(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "crypto")
    out = cli.COMMANDS["forecast"](["new", "btcusd", "up", "0.6", "24", "ETF", "inflows", "level=60000"])
    assert out["forecast"]["pod"] == "crypto" and out["forecast"]["instrument"] == "BTCUSD"
    assert out["forecast"]["why"] == "ETF inflows"
    with pytest.raises(cli.Refused, match="as itself"):
        cli.COMMANDS["forecast"](["new", "BTCUSD", "up", "0.6", "24", "x", "level=60000", "pod=metals"])
    with pytest.raises(cli.Refused, match="prob"):
        cli.COMMANDS["forecast"](["new", "BTCUSD", "up", "0.3", "24", "x", "level=60000"])
    monkeypatch.setenv("AURUM_DESK_ROLE", "head-trader")
    with pytest.raises(cli.Refused, match="only a pod"):
        cli.COMMANDS["forecast"](["new", "BTCUSD", "up", "0.6", "24", "x", "level=60000"])
    monkeypatch.delenv("AURUM_DESK_ROLE")
    assert cli.COMMANDS["forecast"](["new", "XAUUSD", "down", "0.55", "4", "x", "level=2400", "pod=metals"])["ok"]
    assert [f["pod"] for f in cli.COMMANDS["forecast"](["list", "open"])] == ["crypto", "metals"]
    assert cli.COMMANDS["forecast"](["skill", "crypto"])["open"] == 1


def test_daily_scores_carry_skill_and_brief_shows_calls(monkeypatch):
    monkeypatch.setattr(scorekeeper, "follow_rejected", lambda *a, **k: 0)
    forecasts.new("metals", "XAUUSD", "up", 0.9, 1, "gold bid", level=2400, t=T0 - dt.timedelta(hours=3))
    forecasts.new("crypto", "BTCUSD", "down", 0.6, 24, "weekend", level=60000, t=T0)
    sc = scorekeeper.daily(T0, FakeBroker([2401.0] * 40, start=T0 - dt.timedelta(hours=4)))
    assert sc["forecasts"]["metals"]["graded"] == 1 and sc["pods"]["metals"]["forecast_skill"] > 0
    assert json.loads((paths.STATE / "scores.json").read_text())["pods"]["metals"]["forecast_skill"] > 0
    assert "## Forecasts" in (paths.REPORTS / "scores_2026-10-21.md").read_text(encoding="utf-8")
    text = build("metals")
    assert "## Your forecasts" in text and "BTCUSD" in text  # crypto's open call shows to the other pods
