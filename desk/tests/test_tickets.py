from conftest import ticket

from desk import tickets


def test_valid_ticket_is_proposed():
    tid, errs = tickets.new(**ticket())
    assert errs == [] and tid
    tk = tickets.fold()[tid]
    assert tk["status"] == "proposed"
    assert tk["entry"] == {"type": "market"} and tk["confidence"] == 3


def test_armed_ticket_is_approved():
    tid, _ = tickets.new(**ticket(arm="breakout fired"))
    assert tickets.fold()[tid]["status"] == "approved"


def test_validation_errors():
    cases = [
        (dict(stop=None), "missing stop"),
        (dict(instrument="FOO"), "unknown"),
        (dict(pod="nobody"), "unknown"),
        (dict(side="long"), "side must be buy or sell"),
        (dict(stop=1.2, entry={"type": "limit", "price": 1.1}), "wrong side"),
        (dict(entry={"type": "limit"}), "entry.price"),
        (dict(entry={"type": "iceberg"}), "entry.type"),
        (dict(targets=[[1.09, 1.0]]), "target on the wrong side"),
        (dict(targets=[[1.099, 1.0]], entry={"type": "limit", "price": 1.1}), "target on the wrong side"),
        (dict(targets=[[1.11, 0.5], [1.12, 0.4]]), "add up to 1"),
        (dict(confidence=9), "confidence"),
        (dict(risk_pct=7), "risk_pct"),
    ]
    for over, want in cases:
        tid, errs = tickets.new(**ticket(**over))
        assert tid is None, over
        assert any(want in e for e in errs), (over, errs)


def test_sell_stop_must_be_above():
    tid, errs = tickets.new(**ticket(side="sell", stop=1.095, entry={"type": "limit", "price": 1.1}))
    assert tid is None and any("wrong side" in e for e in errs)
    tid, errs = tickets.new(**ticket(side="sell", stop=1.105, targets=[[1.09, 1.0]]))
    assert tid and not errs


def test_lifecycle_events_fold():
    tid, _ = tickets.new(**ticket())
    tickets.approve(tid, "fits the plan")
    tickets.placed(tid, order=5, volume=0.01)
    tickets.opened(tid, position=7, fill=1.1001)
    tickets.update(tid, risk_now=0.01)
    tickets.closed(tid, pnl=-6.2, reason="stop")
    tk = tickets.fold()[tid]
    assert tk["status"] == "closed" and tk["position"] == 7 and tk["pnl"] == -6.2
    assert [h["event"] for h in tk["history"]] == ["new", "approve", "placed", "open", "update", "close"]
    assert tid not in tickets.live()


def test_live_and_by_status():
    a, _ = tickets.new(**ticket())
    c, _ = tickets.new(**ticket())
    tickets.reject(c, "no edge")
    assert set(tickets.live()) == {a}
    assert [v["id"] for v in tickets.by_status("rejected")] == [c]
