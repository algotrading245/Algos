from conftest import ticket

from desk import memory, tickets


def closed(R, **over):
    tid, errs = tickets.new(**ticket(**over))
    assert not errs, errs
    tickets.closed(tid, R=R, pnl=R * 10, reason="target" if R > 0 else "stop")
    return tid


def test_board_and_lessons_round_trip():
    memory.post("fxmacro", "USD bid into CPI", instrument="EURUSD")
    memory.add_lesson("fxmacro", "fade the first spike")
    assert memory.board()[-1]["text"] == "USD bid into CPI"
    assert memory.lessons("fxmacro")[-1]["lesson"] == "fade the first spike"
    assert memory.lessons("metals") == []


def test_similar_calibration_and_edge_score():
    closed(1.5, confidence=4, edge="e1")
    closed(-1.0, confidence=4, edge="e1")
    closed(2.0, confidence=5, instrument="USDJPY")
    sim = memory.similar(ticket(edge="e1"))
    assert [s["edge"] for s in sim[:2]] == ["e1", "e1"]
    cal = memory.calibration()
    assert cal[4] == {"trades": 2, "hit": 0.5, "avg_R": 0.25}
    s = memory.edge_score("e1", backtest_r=0.0, prior=2)
    assert s["trades"] == 2 and s["score"] == 0.125
