"""The 11-02 upgrades: the breakout's Friday cut and margin, the equity history, the dashboard restart on code change."""
import datetime as dt
import json

import pandas as pd

from desk import dashboard, edges, tick, watchdog
from desk.edges.base import DAY

FRIDAY = 20000  # server day number of Friday 2024-10-04
THURSDAY = FRIDAY - 1


def _day(day, break_at_min, close):
    """M15 bars for one day: a 150.00-150.20 Tokyo range, then flat at 150.10 until one bar closes at `close`."""
    rows = []
    for m in range(0, 24 * 60, 15):
        c = 150.1
        h, l = (150.2, 150.0) if 60 <= m < 540 else (150.15, 150.05)
        if m == break_at_min:
            c, h = close, max(close, 150.15)
            l = min(close, 150.05)
        rows.append({"time": day * DAY + m * 60, "open": 150.1, "high": h, "low": l, "close": c})
    return pd.DataFrame(rows)


def test_breakout_friday_cut_skips_afternoon_entries():
    assert edges.run("breakout", _day(FRIDAY, 900, 150.3)) == []          # 15:00 server on a Friday: skipped
    assert len(edges.run("breakout", _day(THURSDAY, 900, 150.3))) == 1    # the same bar on Thursday trades
    assert len(edges.run("breakout", _day(FRIDAY, 780, 150.3))) == 1      # 13:00 Friday, before the cut, trades


def test_breakout_margin_needs_a_close_past_the_range():
    df = _day(THURSDAY, 690, 150.21)  # 1 pip past a 20-pip range
    assert len(edges.run("breakout", df)) == 1                             # margin off by default
    assert edges.run("breakout", df, {"margin": 0.1}) == []                # needs 2 pips past
    assert len(edges.run("breakout", _day(THURSDAY, 690, 150.23), {"margin": 0.1})) == 1


def test_record_equity_appends_and_history_reads_it(tmp_path, monkeypatch):
    f = tmp_path / "equity.jsonl"
    monkeypatch.setattr(tick, "EQUITY", f)
    t = dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.timezone.utc)
    tick.record_equity(t, {"ok": False})  # no account read: nothing written
    assert not f.exists()
    for k in range(5):
        tick.record_equity(t + dt.timedelta(minutes=k), {"equity": 10000 + k, "balance": 10000})
    monkeypatch.setattr(dashboard, "_HIST", {"size": -1, "rows": []})
    rows = dashboard.equity_history(f, points=2)
    assert rows[0] == ["2026-11-02T09:00:00+00:00", 10000] and rows[-1][1] == 10004 and len(rows) <= 4
    assert json.loads(f.read_text().splitlines()[-1])["balance"] == 10000


def test_dashboard_restarts_only_after_a_code_change():
    calls = []
    run = lambda a, **k: calls.append(a) or type("R", (), {"returncode": 0})()  # noqa: E731
    assert watchdog.check_dashboard(proc=(0, 2000.0), newest=1000.0, run=run) is None and not calls
    killed = []
    orig = watchdog._kill_tree
    watchdog._kill_tree = killed.append
    try:
        assert watchdog.check_dashboard(proc=(4242, 1000.0), newest=2000.0, run=run)
    finally:
        watchdog._kill_tree = orig
    assert [c[1] for c in calls] == ["/End", "/Run"] and killed == [4242]
