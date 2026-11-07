import datetime as dt

from desk import clocks, monitor, news, paths

BLOCKING = news.blocking  # the real one: conftest stubs it for every test after collection


def fetched(hours_ago, events=()):
    t = clocks.now() - dt.timedelta(hours=hours_ago)
    paths.write_json(news.FILE, {"fetched": t.isoformat(timespec="seconds"), "events": list(events)})


def test_no_calendar_blocks_every_entry():
    assert news.stale() == "no calendar fetched yet"
    assert BLOCKING("EURUSD")["ccy"] == "ALL"


def test_a_stale_calendar_blocks_and_a_fresh_one_does_not():
    fetched(49)
    assert BLOCKING("EURUSD")["title"].startswith("calendar stale")
    fetched(2)
    assert BLOCKING("EURUSD") is None


def test_a_release_blocks_its_currencies_only():
    t = clocks.now() + dt.timedelta(minutes=1)
    fetched(2, [{"t": t.isoformat(timespec="seconds"), "ccy": "USD", "title": "CPI"}])
    assert BLOCKING("EURUSD")["title"] == "CPI" and BLOCKING("XAUUSD")["title"] == "CPI"
    assert BLOCKING("EURGBP") is None


def test_monitor_alerts_on_a_stale_calendar(b, cfg):
    assert any("calendar" in i["what"] and i["level"] == "alert" for i in monitor.check(b, cfg))
    fetched(2)
    assert not any("calendar" in i["what"] for i in monitor.check(b, cfg))
