import datetime as dt
import json

from conftest import set_now, ticket

from desk import broker, cli, clocks, jobs, monitor, paths, tickets, triggers, watchdog


def run_cli(capsys, *argv):
    code = cli.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


# ---- jobs -----------------------------------------------------------------------------------------------------------

def test_pending_by_priority_then_age():
    t = clocks.now()
    a = jobs.queue("brief", t, name="london")
    m = jobs.queue("monitor", t + dt.timedelta(seconds=1))
    w = jobs.queue("wake", t + dt.timedelta(seconds=2), pod="fxmacro")
    assert [j["id"] for j in jobs.pending()] == [m, w, a]
    jobs.mark(m, "done")
    assert [j["id"] for j in jobs.pending()] == [w, a]
    assert jobs.has_pending("brief", name="london") and not jobs.has_pending("brief", name="ny")


def test_wake_limit_per_pod_day(cfg):
    t = clocks.now()
    got = [jobs.wake("fxmacro", ["g1"], cfg, t) for _ in range(cfg["wakes_per_pod_day"] + 2)]
    assert sum(1 for g in got if g) == cfg["wakes_per_pod_day"] and got[-1] is None
    assert jobs.wake("systematic", ["g2"], cfg, t)


def test_stale_jobs_are_skipped_but_monitor_kept():
    t = clocks.now()
    old = jobs.queue("brief", t - dt.timedelta(hours=7), name="asia")
    mon = jobs.queue("monitor", t - dt.timedelta(hours=7))
    jobs.expire_stale(t)
    f = jobs.fold()
    assert f[old]["status"] == "skipped" and f[mon]["status"] == "pending"


def test_compact_keeps_open_jobs():
    t = clocks.now()
    old = jobs.queue("brief", t - dt.timedelta(days=30), name="old")
    jobs.mark(old, "done")
    keep = jobs.queue("brief", t - dt.timedelta(days=30), name="still open")
    jobs.compact()
    f = jobs.fold()
    assert old not in f and keep in f


# ---- triggers -------------------------------------------------------------------------------------------------------

def test_trigger_validation(cfg):
    gid, errs = triggers.add("fxmacro", "above", "", cfg, instrument="FOO")
    assert gid is None
    assert any("missing level" in e for e in errs) and any("unknown instrument" in e for e in errs)
    assert any("missing why" in e for e in errs)
    gid, errs = triggers.add("fxmacro", "ticket", "x", cfg, ticket="t1", on="filled")
    assert gid is None and any("on must be" in e for e in errs)


def test_price_time_and_ticket_triggers_fire_once(b, cfg, monkeypatch):
    up, _ = triggers.add("fxmacro", "above", "breakout", cfg, instrument="EURUSD", level=1.1005)
    dn, _ = triggers.add("fxmacro", "below", "dip", cfg, instrument="EURUSD", level=1.0950)
    at, _ = triggers.add("fxmacro", "time", "ny open", cfg, at="2026-10-21T14:30:00")
    tid, _ = tickets.new(**ticket())
    tk, _ = triggers.add("fxmacro", "ticket", "watch fill", cfg, ticket=tid, on="open")
    assert triggers.check(b, cfg, tickets.fold()) == []
    b.set_price("EURUSD", 1.1006, 1.1007)
    assert [g["id"] for g in triggers.check(b, cfg, tickets.fold())] == [up]
    assert triggers.check(b, cfg, tickets.fold()) == []  # fired once
    set_now(monkeypatch, "2026-10-21T14:31:00")
    tickets.approve(tid)
    tickets.placed(tid, order=1, volume=0.01)
    tickets.opened(tid, position=2)
    b.set_price("EURUSD", 1.1006, 1.1007)
    assert {g["id"] for g in triggers.check(b, cfg, tickets.fold())} == {at, tk}
    assert [g["id"] for g in triggers.active("fxmacro")] == [dn]


def test_trigger_expiry_and_remove(b, cfg, monkeypatch):
    a, _ = triggers.add("fxmacro", "above", "far", cfg, instrument="EURUSD", level=1.2)
    r, _ = triggers.add("fxmacro", "above", "other", cfg, instrument="EURUSD", level=1.3)
    assert not triggers.remove(r, "systematic") and triggers.remove(r, "fxmacro")
    set_now(monkeypatch, "2026-10-22T14:01:00")
    b.set_price("EURUSD", 1.1000, 1.1001)
    assert triggers.check(b, cfg, {}) == [] and triggers.active() == []
    assert a not in [g["id"] for g in triggers.active()]


# ---- cli role rules -------------------------------------------------------------------------------------------------

def test_pod_proposes_only_its_own_tickets(capsys, monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    code, out = run_cli(capsys, "ticket", "new", json.dumps(ticket(pod="systematic")))
    assert code == 1 and "may only propose fxmacro" in out["refused"]
    t = ticket()
    t.pop("pod")
    code, out = run_cli(capsys, "ticket", "new", json.dumps(t))
    assert code == 0 and out["ok"] and tickets.fold()[out["id"]]["pod"] == "fxmacro"


def test_inactive_pod_refused(capsys, monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "metals")
    code, out = run_cli(capsys, "ticket", "new", json.dumps(ticket(pod="metals", instrument="XAUUSD", stop=1.0)))
    assert code == 1 and "not active" in out["refused"]


def test_only_the_head_trader_approves(capsys, monkeypatch):
    tid, _ = tickets.new(**ticket())
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    code, out = run_cli(capsys, "ticket", "approve", tid, "mine")
    assert code == 1 and "head trader" in out["refused"]
    monkeypatch.setenv("AURUM_DESK_ROLE", "head-trader")
    code, out = run_cli(capsys, "ticket", "approve", tid)
    assert code == 1 and "reason" in out["refused"]
    code, out = run_cli(capsys, "ticket", "approve", tid, "fits the book")
    assert code == 0 and out["status"] == "approved"


def test_other_pod_cannot_touch_a_ticket(capsys, monkeypatch):
    tid, _ = tickets.new(**ticket())
    monkeypatch.setenv("AURUM_DESK_ROLE", "systematic")
    code, out = run_cli(capsys, "ticket", "cancel", tid, "not mine")
    assert code == 1 and "belongs to fxmacro" in out["refused"]


def test_stop_only_tightens(capsys, monkeypatch):
    tid, _ = tickets.new(**ticket())
    tickets.approve(tid)
    tickets.placed(tid, order=1, volume=0.01)
    tickets.opened(tid, position=2, fill=1.1001)
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    code, out = run_cli(capsys, "ticket", "stop", tid, "1.090", "more room")
    assert code == 1 and "only tightens" in out["refused"]
    code, out = run_cli(capsys, "ticket", "stop", tid, "1.097", "lock in")
    assert code == 0 and tickets.fold()[tid]["move_stop"] == 1.097


def test_resume_is_owner_only_and_any_role_can_kill(capsys, monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    code, out = run_cli(capsys, "kill", "something", "is", "wrong")
    assert code == 0 and paths.KILL.exists()
    code, out = run_cli(capsys, "resume")
    assert code == 1 and "only the owner" in out["refused"]
    monkeypatch.delenv("AURUM_DESK_ROLE")
    monkeypatch.setenv("AURUM_AGENT", "1")  # an agent with its role blanked is still not the owner
    code, out = run_cli(capsys, "resume")
    assert code == 1 and "only the owner" in out["refused"]
    monkeypatch.delenv("AURUM_AGENT")
    code, out = run_cli(capsys, "resume")
    assert code == 0 and out["halt"] is None


def test_view_quote_takes_several_markets(capsys, monkeypatch, b):
    b.shutdown = lambda: None
    monkeypatch.setattr(cli, "_broker", lambda: b)
    code, out = run_cli(capsys, "view", "quote", "EURUSD")
    assert code == 0 and out["symbol"] == "EURUSD" and out["bid"] == 1.1
    code, out = run_cli(capsys, "view", "quote", "EURUSD", "XAUUSD")
    assert code == 0 and out["EURUSD"]["ask"] == 1.1001 and "not offered" in out["XAUUSD"]["refused"]
    code, out = run_cli(capsys, "view", "bars", "EURUSD", "XAUUSD")
    assert code == 1 and "TF" in out["refused"]


def test_alert_ack_is_owner_only_and_archives(capsys, monkeypatch):
    f = paths.INBOX / "ALERT.md"
    f.write_text("# Desk alert 2026-10-21 13:00 UTC\n\n- clock stalled\n", encoding="utf-8")
    code, out = run_cli(capsys, "alert", "ack")
    assert code == 1 and "say what was done" in out["refused"]
    monkeypatch.setenv("AURUM_DESK_ROLE", "monitor")
    code, out = run_cli(capsys, "alert", "ack", "fixed")
    assert code == 1 and "only the owner" in out["refused"] and f.exists()
    monkeypatch.delenv("AURUM_DESK_ROLE")
    code, out = run_cli(capsys, "alert", "ack", "clock", "restarted")
    assert code == 0 and out["acknowledged"] == ["Desk alert 2026-10-21 13:00 UTC"] and not f.exists()
    archived = (paths.STATE / "alerts").glob("ALERT_*.md")
    assert "by the owner: clock restarted" in next(archived).read_text(encoding="utf-8")
    code, out = run_cli(capsys, "alert", "ack", "again")
    assert code == 0 and out["archived"] is None


def test_pod_sets_only_its_own_triggers(capsys, monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    code, out = run_cli(capsys, "trigger", "add", "systematic", "above", "x", "instrument=EURUSD", "level=1.2")
    assert code == 1 and "sets only fxmacro" in out["refused"]
    code, out = run_cli(capsys, "trigger", "add", "fxmacro", "above", "x", "instrument=EURUSD", "level=1.2")
    assert code == 0 and out["ok"] and triggers.active("fxmacro")[0]["level"] == 1.2


def test_status_without_a_terminal(capsys):
    code, out = run_cli(capsys, "status")
    assert code == 0 and out["phase"] == 1 and out["profile"] == "demo_10k"


# ---- monitor and watchdog -------------------------------------------------------------------------------------------

def test_monitor_flags_a_position_without_a_stop(b, cfg):
    b.send(symbol="EURUSD", side="buy", volume=0.01, sl=0, magic=730001, comment="x")
    b.send(symbol="EURUSD", side="buy", volume=0.01, sl=0, magic=12345, comment="the owner's")
    issues, queued = monitor.run(b, cfg)
    whats = [i["what"] for i in issues]
    assert sum("no server-side stop" in w for w in whats) == 1  # the owner's own trade is not the desk's business
    assert any("has no open ticket" in w for w in whats)
    assert queued and monitor.ALERT.exists()
    assert monitor.run(b, cfg) == (issues, False)  # the same problems do not queue the agent again


def test_monitor_alerts_when_the_terminal_is_gone(cfg):
    issues = monitor.check(broker.DryBroker("terminal closed"), cfg)
    assert issues and issues[0]["level"] == "alert" and "not connected" in issues[0]["what"]


def test_watchdog_finds_only_the_desk_terminal(cfg):
    exe = cfg["terminal"]["path"]
    others = [(1, "terminal64.exe", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
              (2, "terminal64.exe", r"C:\MetaTrader 5 - Tester\terminal64.exe")]
    assert not watchdog.terminal_running(cfg, others)
    assert watchdog.terminal_running(cfg, others + [(3, "terminal64.exe", exe)])
