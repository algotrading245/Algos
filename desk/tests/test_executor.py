from conftest import backdate_phase, set_now, ticket

from desk import executor, paths, risk_gate, tickets


def approved(**over):
    tid, errs = tickets.new(**ticket(**over))
    assert not errs, errs
    tickets.approve(tid)
    return tid


def get(tid):
    return tickets.fold()[tid]


def test_approved_ticket_is_placed_and_opened_in_one_pass(b, cfg):
    tid = approved()
    s = executor.run(b, cfg)
    assert s["ok"] and s["sent"] == 1 and s["phase"] == 1
    tk = get(tid)
    assert tk["status"] == "open" and tk["fill"] == 1.1001 and tk["volume"] == 0.01
    p = b.positions()[0]
    assert p["sl"] == 1.095 and p["magic"] == 730001 and p["comment"] == tid


def test_stop_hit_closes_the_ticket_with_its_pnl(b, cfg):
    tid = approved()
    executor.run(b, cfg)
    b.set_price("EURUSD", 1.0949, 1.0950)
    executor.run(b, cfg)
    tk = get(tid)
    assert tk["status"] == "closed" and tk["reason"] == "stop" and tk["pnl"] < 0
    assert tk["R"] is not None and -1.2 < tk["R"] < 0


def test_partial_target_then_broker_tp(b, cfg):
    backdate_phase(30)
    tid = approved(targets=[[1.1010, 0.5], [1.1050, 0.5]])
    executor.run(b, cfg)
    assert get(tid)["volume"] == 0.04 and b.positions()[0]["tp"] == 1.105
    b.set_price("EURUSD", 1.1011, 1.1012)
    executor.run(b, cfg)
    tk = get(tid)
    assert tk["targets_done"] == 1 and b.positions()[0]["volume"] == 0.02
    b.set_price("EURUSD", 1.1051, 1.1052)
    executor.run(b, cfg)
    tk = get(tid)
    assert tk["status"] == "closed" and tk["reason"] == "target" and tk["pnl"] > 0


def test_breakeven_moves_the_stop_to_the_fill(b, cfg):
    tid = approved(breakeven_at=1.1020)
    executor.run(b, cfg)
    b.set_price("EURUSD", 1.1021, 1.1022)
    executor.run(b, cfg)
    assert b.positions()[0]["sl"] == 1.1001
    tk = get(tid)
    assert tk["risk_now"] == 0 and tk["sl"] == 1.1001


def test_stop_never_loosens(b, cfg):
    tid = approved()
    executor.run(b, cfg)
    tickets.update(tid, move_stop=1.090)
    executor.run(b, cfg)
    assert b.positions()[0]["sl"] == 1.095
    tickets.update(tid, move_stop=1.097)
    executor.run(b, cfg)
    assert b.positions()[0]["sl"] == 1.097


def test_close_request(b, cfg):
    tid = approved()
    executor.run(b, cfg)
    tickets.update(tid, close_request="thesis broken")
    executor.run(b, cfg)
    tk = get(tid)
    assert not b.positions() and tk["status"] == "closed" and tk["reason"] == "thesis broken"


def test_time_stop(b, cfg, monkeypatch):
    tid = approved(time_stop="2026-10-21T15:00:00")
    executor.run(b, cfg)
    set_now(monkeypatch, "2026-10-21T15:01:00")
    b.set_price("EURUSD", 1.1000, 1.1001)
    executor.run(b, cfg)
    assert get(tid)["status"] == "closed" and get(tid)["reason"] == "time stop"


def test_kill_flattens_and_blocks_new_orders(b, cfg):
    a = approved()
    executor.run(b, cfg)
    risk_gate.kill("owner test", by="owner")
    c = approved(pod="systematic")
    s = executor.run(b, cfg)
    assert s["halt"].startswith("KILL file") and s["sent"] == 0
    assert not b.positions()
    assert get(a)["status"] == "closed" and get(c)["status"] == "cancelled"


def test_loss_past_the_kill_floor_writes_the_kill_file(b, cfg):
    executor.run(b, cfg)
    b.balance = 8700.0
    s = executor.run(b, cfg)
    assert paths.KILL.exists() and s["halt"].startswith("KILL file")


def test_orphan_desk_position_is_closed_and_others_left(b, cfg):
    b.send(symbol="EURUSD", side="buy", volume=0.01, sl=1.09, magic=730001, comment="nobody")
    b.send(symbol="EURUSD", side="buy", volume=0.01, sl=1.09, magic=12345, comment="the owner's")
    executor.run(b, cfg)
    assert [p["magic"] for p in b.positions()] == [12345]


def test_market_ticket_expires_after_its_ttl(b, cfg, monkeypatch):
    tid = approved()
    set_now(monkeypatch, "2026-10-21T14:31:00")
    b.set_price("EURUSD", 1.1000, 1.1001)
    executor.run(b, cfg)
    assert get(tid)["status"] == "expired" and not b.positions()


def test_transient_refusal_waits_and_hard_refusal_blocks(b, cfg, monkeypatch):
    monkeypatch.setattr(risk_gate.spreads, "check", lambda *a, **k: (False, "3x normal"))
    w = approved()
    h = approved(pod="metals", instrument="XAUUSD", stop=1.0)
    executor.run(b, cfg)
    assert get(w)["status"] == "approved" and get(w)["waiting"].startswith("spread:")
    assert get(h)["status"] == "blocked"
    monkeypatch.setattr(risk_gate.spreads, "check", lambda *a, **k: (True, ""))
    executor.run(b, cfg)
    assert get(w)["status"] == "open"


def test_limit_entry_fills_later(b, cfg):
    tid = approved(entry={"type": "limit", "price": 1.0990})
    executor.run(b, cfg)
    assert get(tid)["status"] == "placed" and b.orders()
    b.set_price("EURUSD", 1.0985, 1.0989)
    executor.run(b, cfg)
    tk = get(tid)
    assert tk["status"] == "open" and tk["fill"] == 1.099


def test_no_account():
    from desk import broker
    s = executor.run(broker.DryBroker("terminal closed"))
    assert not s["ok"] and s["why"] == "no account"
