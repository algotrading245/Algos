"""The weekend cutoff stops wakes and briefs (no ticket can pass then), and a calendar fetch replaces moved events."""
import json

from conftest import set_now

from desk import jobs, journal, news, paths, tick, triggers

SATURDAY = "2026-10-31T12:00:00+00:00"


def use_profile(name):
    paths.write_json(paths.RISK, {**paths.risk(), "active": name})


def test_wake_refused_past_the_weekend_cutoff(cfg, monkeypatch):
    use_profile("prop_10k")  # flat_before_weekend
    set_now(monkeypatch, SATURDAY)
    assert jobs.weekend_closed()
    assert jobs.wake("fxmacro", ["g1"], cfg) is None and triggers.wakes_today("fxmacro") == 0
    assert "weekend cutoff" in journal.recent(["wake_refused"], 1)[-1]["why"]


def test_weekday_or_no_weekend_rule_still_wakes(cfg, monkeypatch):
    use_profile("prop_10k")
    assert not jobs.weekend_closed()  # the pinned Wednesday
    assert jobs.wake("fxmacro", ["g1"], cfg)
    use_profile("demo_10k")  # no flat_before_weekend: weekends are open
    set_now(monkeypatch, SATURDAY)
    assert not jobs.weekend_closed() and jobs.wake("systematic", ["g2"], cfg)


def test_brief_skipped_past_the_cutoff_and_marked_ran(cfg, monkeypatch):
    import datetime as dt
    cfg = dict(cfg, schedule=[{"name": "test_brief", "kind": "brief", "every_min": 60}])
    use_profile("prop_10k")
    sat = dt.datetime.fromisoformat(SATURDAY)
    assert tick.schedule(None, cfg, {}, sat) == ["test_brief"]
    assert not jobs.has_pending("brief")
    assert journal.recent(["brief_skipped"], 1)[-1]["event"] == "test_brief"
    assert paths.read_json(tick.SCHEDULE, {})["test_brief"]["ran"] == SATURDAY
    mon = dt.datetime.fromisoformat("2026-11-02T14:00:00+00:00")  # the cutoff is over: the brief is queued again
    assert tick.schedule(None, cfg, {}, mon) == ["test_brief"] and jobs.has_pending("brief", name="test_brief")


class _Resp:
    def __init__(self, rows):
        self.body = json.dumps(rows).encode()

    def read(self):
        return self.body


def test_fetch_replaces_a_moved_event_inside_the_feed_span(cfg, monkeypatch):
    paths.write_json(news.FILE, {"events": [
        {"t": "2026-10-15T12:30:00+00:00", "ccy": "USD", "title": "CPI"},          # last week: outside the span, kept
        {"t": "2026-10-21T02:30:00+00:00", "ccy": "JPY", "title": "BOJ Policy"},   # moved to 03:02 by the feed
        {"t": "2026-09-01T12:30:00+00:00", "ccy": "USD", "title": "Old"},          # past the 14-day cutoff
    ]})
    feed = [{"date": "2026-10-19T00:00:00-04:00", "impact": "Low", "country": "EUR", "title": "Span start"},
            {"date": "2026-10-21T03:02:00+00:00", "impact": "High", "country": "JPY", "title": "BOJ Policy"},
            {"date": "2026-10-23T12:30:00+00:00", "impact": "High", "country": "USD", "title": "PMI"}]
    monkeypatch.setattr(news.urllib.request, "urlopen", lambda req, timeout=30: _Resp(feed))
    got = news.fetch(cfg)
    assert [r["title"] for r in got] == ["BOJ Policy", "PMI"]
    stored = [(e["t"][:16], e["title"]) for e in paths.read_json(news.FILE, {})["events"]]
    assert stored == [("2026-10-15T12:30", "CPI"), ("2026-10-21T03:02", "BOJ Policy"), ("2026-10-23T12:30", "PMI")]
