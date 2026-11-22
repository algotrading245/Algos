import datetime as dt

import pytest

from desk import cli, forecasts, market_model as mm
from desk.brief import build

T0 = dt.datetime(2026, 10, 21, 14, tzinfo=dt.timezone.utc)


def test_set_merges_fields_and_validates():
    e = mm.set_market("metals", "xauusd", T0, bias="up", regime="trend", levels="2400,2350", conviction="2",
                      edges="donchian_trend", drivers="real yields falling")
    assert e["levels"] == [2350.0, 2400.0] and e["conviction"] == 2 and e["edges"] == ["donchian_trend"]
    e = mm.set_market("metals", "XAUUSD", T0, regime="volatile")  # only the field given changes
    assert e["bias"] == "up" and e["regime"] == "volatile" and e["drivers"] == "real yields falling"
    for bad, msg in (({"bias": "sideways"}, "bias"), ({"regime": "chop"}, "regime"), ({"conviction": "5"}, "conviction"),
                     ({"edges": "magic"}, "no edge"), ({"colour": "x"}, "unknown field")):
        with pytest.raises(ValueError, match=msg):
            mm.set_market("metals", "XAUUSD", T0, **bad)
    with pytest.raises(ValueError, match="not a desk market"):
        mm.set_market("metals", "DOGEUSD", T0, bias="up")
    with pytest.raises(ValueError, match="needs a bias"):
        mm.set_market("metals", "XAGUSD", T0, regime="range")
    assert [r["op"] for r in mm.history("metals")] == ["set", "set"]


def test_any_pod_may_model_any_desk_market():
    assert mm.set_market("crypto", "EURUSD", T0, bias="down")["bias"] == "down"


def test_stale_entries_and_biases_without_forecasts():
    mm.set_market("fxmacro", "EURUSD", T0 - dt.timedelta(days=8), bias="down")
    mm.set_market("fxmacro", "USDJPY", T0, bias="up", conviction=3)
    mm.set_market("fxmacro", "GBPUSD", T0, bias="flat")
    mm.set_market("indices", "USDJPY", T0, bias="down", conviction=1)
    b = mm.brief("fxmacro", T0)
    assert b["stale"] == ["EURUSD"] and b["markets"]["EURUSD"]["stale"]
    assert b["biases_with_no_forecast"] == ["USDJPY"]  # flat and stale ones are not asked for a forecast
    assert b["desk_biases"]["USDJPY"] == {"fxmacro": "up3", "indices": "down1"}
    assert "EURUSD" not in b["desk_biases"]  # a stale view is not part of the desk's map
    forecasts.new("fxmacro", "USDJPY", "up", 0.6, 24, "BoJ on hold", level=150.0, t=T0)
    assert mm.brief("fxmacro", T0)["biases_with_no_forecast"] == []


def test_view_and_drop():
    mm.set_view("event", "NFP Friday dominates", T0)
    mm.set_market("event", "US500", T0, bias="up")
    mm.drop("event", "us500", T0)
    assert mm.get("event") | {} == {"pod": "event", "view": "NFP Friday dominates", "view_updated": T0.isoformat(),
                                    "markets": {}}
    with pytest.raises(ValueError, match="no view"):
        mm.drop("event", "US500", T0)


def test_cli_pod_edits_only_its_own_model(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "crypto")
    out = cli.COMMANDS["model"](["set", "btcusd", "bias=up", "levels=60000,65000", "ETF", "inflows"])
    assert out["BTCUSD"]["drivers"] == "ETF inflows"
    with pytest.raises(cli.Refused, match="as itself"):
        cli.COMMANDS["model"](["set", "BTCUSD", "bias=down", "pod=metals"])
    with pytest.raises(cli.Refused, match="bias"):
        cli.COMMANDS["model"](["set", "ETHUSD", "bias=moon"])
    assert cli.COMMANDS["model"](["show"])["markets"]["BTCUSD"]["bias"] == "up"
    monkeypatch.setenv("AURUM_DESK_ROLE", "head-trader")
    with pytest.raises(cli.Refused, match="only a pod"):
        cli.COMMANDS["model"](["view", "x"])
    assert cli.COMMANDS["model"](["show", "crypto"])["markets"]["BTCUSD"]["levels"] == [60000.0, 65000.0]
    monkeypatch.delenv("AURUM_DESK_ROLE")
    assert cli.COMMANDS["model"](["view", "risk-on", "pod=metals"])["view"] == "risk-on"
    assert cli.COMMANDS["model"](["consensus"]) == {"BTCUSD": {"crypto": "up"}}


def test_brief_shows_the_model():
    mm.set_market("metals", "XAUUSD", mm.clocks.now(), bias="up", conviction=2)
    text = build("metals")
    assert "## Your market model" in text and '"XAUUSD"' in text and "biases_with_no_forecast" in text
