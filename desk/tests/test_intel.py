"""Pods talk (asks, replies), share knowledge (learn, endorse) and get a profile computed from their real record."""
import pytest

from conftest import ticket
from desk import cli, extras, intel, journal, memory, paths, runner, tickets


def closed(R, **over):
    tid, errs = tickets.new(**ticket(**over)); assert not errs, errs
    tickets.closed(tid, R=R, pnl=R * 10, reason="target" if R > 0 else "stop"); return tid


def test_ask_reply_and_open_asks():
    q = memory.ask("metals", "fxmacro", "Is the USD move a trend?", "EURUSD")
    assert [r["id"] for r in memory.open_asks("fxmacro")] == [q["id"]]
    assert memory.open_asks("metals") == [] and memory.open_asks("indices") == []
    r = memory.reply("fxmacro", q["id"], "Trend while yields rise")
    assert r["reply_to"] == q["id"] and r["to"] == "metals" and r["instrument"] == "EURUSD"
    assert memory.open_asks("fxmacro") == []
    got = memory.replies_for("metals")
    assert got[0]["from"] == "fxmacro" and got[0]["ask"] == "Is the USD move a trend?"
    assert [t["kind"] for t in memory.talk()] == ["ask", "reply"]


def test_ask_to_all_closes_after_one_reply():
    q = memory.ask("metals", "all", "Risk mood?")
    assert memory.open_asks("indices") and memory.open_asks("crypto")
    memory.reply("indices", q["id"], "Risk on")
    assert memory.open_asks("crypto") == []


def test_ask_and_reply_refusals():
    with pytest.raises(ValueError, match="itself"):
        memory.ask("metals", "metals", "?")
    q = memory.ask("metals", "fxmacro", "?")
    with pytest.raises(ValueError, match="own ask"):
        memory.reply("metals", q["id"], "!")
    with pytest.raises(ValueError, match="no ask"):
        memory.reply("fxmacro", "bnope", "!")


def test_learn_endorse_and_shared_with():
    a = memory.learn("fxmacro", "USDJPY fades 1% spikes", "USDJPY")
    b = memory.learn("indices", "Gold leads US500 on risk-off", "XAUUSD")
    c = memory.learn("crypto", "BTC weekend gaps fill")
    memory.learn("event", "private note", share="pod")
    memory.endorse("metals", a["id"])
    memory.endorse("crypto", a["id"])
    with pytest.raises(ValueError, match="own entry"):
        memory.endorse("fxmacro", a["id"])
    with pytest.raises(ValueError, match="already endorsed"):
        memory.endorse("metals", a["id"])
    with pytest.raises(ValueError, match="no knowledge"):
        memory.endorse("metals", "knope")
    assert memory.knowledge("fxmacro")[0]["endorsed_by"] == ["crypto", "metals"]
    ids = [e["id"] for e in memory.shared_with("metals", ["XAUUSD"])]
    assert ids == [b["id"], a["id"], c["id"]]  # own market first, then most endorsed; pod-only notes never shared
    with pytest.raises(ValueError, match="desk or pod"):
        memory.learn("metals", "x", share="world")


def test_level():
    assert intel.level(0)["name"] == "Rookie" and intel.level(99)["next"] == 100
    assert intel.level(100) == {"n": 2, "name": "Analyst", "floor": 100, "next": 250}
    assert intel.level(10 ** 6)["name"] == "Legend" and intel.level(10 ** 6)["next"] is None


def test_profile_counts_real_work():
    note = memory.post("fxmacro", "EURUSD: bias down", "EURUSD")
    memory.post("metals", "XAUUSD: bid", "XAUUSD", cites=[note["id"]])
    tickets.new(**ticket(pod="metals", instrument="XAUUSD", stop=2300.0, cites=[note["id"]]))
    q = memory.ask("metals", "fxmacro", "USD?")
    memory.reply("fxmacro", q["id"], "Down")
    k = memory.learn("fxmacro", "ECB minutes move EURUSD less than they did")
    memory.endorse("metals", k["id"])
    journal.log("agent_run", role="fxmacro", ok=True)
    journal.log("agent_run", role="fxmacro", ok=False)
    journal.log("missing_notes", pod="fxmacro", markets=["GBPUSD"])
    p = intel.profile("fxmacro")
    assert p["work"] == {"runs": 1, "notes": 1, "missed_notes": 1, "coverage": 0.5}
    assert p["talk"]["answered"] == 1 and p["share"] == {"shared": 1, "endorsed": 1, "cited": 2}
    assert p["xp"] == 10 + 2 + 6 + 5 + 8 + 2 * 15
    assert intel.profile("metals")["talk"]["asked"] == 1


def test_profile_trading_strengths_and_weaknesses():
    for _ in range(4):
        closed(2.0, instrument="EURUSD", confidence=4)
    for _ in range(4):
        closed(-1.0, instrument="GBPUSD", stop=1.2, edge="breakout", confidence=2)
    p = intel.profile("fxmacro")
    t = p["trading"]
    assert t["trades"] == 8 and t["hit"] == 0.5 and t["avg_R"] == 0.5 and t["calibration"] == 1.0
    assert p["strengths"][0]["what"] == "instrument EURUSD"
    assert {w["what"] for w in p["weaknesses"]} == {"instrument GBPUSD", "edge breakout"}
    assert p["iq"] > 100 and p["xp"] >= 8 * 5 + 20 * 4


def test_write_journals_level_up():
    intel.write()
    assert not journal.recent(["level_up"], 1)
    for _ in range(3):
        closed(2.0)  # 3 trades and +6R: 15 + 120 xp, Rookie to Analyst
    out = intel.write()
    ups = journal.recent(["level_up"], 1)
    assert [(u["pod"], u["name"]) for u in ups] == [("fxmacro", "Analyst")]
    assert paths.read_json(intel.FILE, {})["pods"]["fxmacro"]["level"]["name"] == "Analyst"
    assert set(out) >= {"pods", "talk", "knowledge"}


def test_brief_shows_talk_knowledge_and_profile(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_DRY", "1")
    from desk import brief
    q = memory.ask("fxmacro", "metals", "Gold and real yields?")
    memory.learn("indices", "US500 drifts up into month end", "US500")
    text = brief.build("metals")
    for s in ("Questions for you from other pods", "Replies to your questions", "Knowledge other pods shared",
              "Your intelligence profile"):
        assert s in text
    assert q["id"] in text and "month end" in text


def test_cli_board_ask_reply_asks(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "metals")
    q = extras.board(["ask", "fxmacro", "USD", "trend?", "instrument=EURUSD"])
    assert q["to"] == "fxmacro" and q["text"] == "USD trend?"
    with pytest.raises(cli.Refused, match="no pod"):
        extras.board(["ask", "nobody", "?"])
    with pytest.raises(cli.Refused, match="itself"):
        extras.board(["ask", "metals", "?"])
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    assert [r["id"] for r in extras.board(["asks"])] == [q["id"]]
    extras.board(["reply", q["id"], "Trend"])
    assert extras.board(["asks"]) == []
    with pytest.raises(cli.Refused, match="no ask"):
        extras.board(["reply", "bnope", "x"])


def test_cli_memory_learn_endorse_knowledge_and_intel(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_ROLE", "fxmacro")
    k = extras.memory_cmd(["learn", "BoJ", "risk", "caps", "USDJPY", "instrument=USDJPY"])
    with pytest.raises(cli.Refused, match="own entry"):
        extras.memory_cmd(["endorse", k["id"]])
    monkeypatch.setenv("AURUM_DESK_ROLE", "metals")
    extras.memory_cmd(["endorse", k["id"]])
    with pytest.raises(cli.Refused, match="already"):
        extras.memory_cmd(["endorse", k["id"]])
    assert extras.memory_cmd(["knowledge", "fxmacro"])[0]["endorsed_by"] == ["metals"]
    assert extras.intel_cmd(["fxmacro"])["share"]["endorsed"] == 1
    assert set(extras.intel_cmd([])) == set(paths.config()["pods"])


def test_dashboard_shows_intel_talk_and_knowledge():
    from desk import dashboard
    memory.ask("metals", "fxmacro", "USD?")
    memory.learn("fxmacro", "CPI days fade by NY close")
    got = dashboard._intel(paths.config())
    assert got["pods"]["fxmacro"]["share"]["shared"] == 1 and got["talk"][0]["kind"] == "ask"
    intel.write()
    pods = dashboard._pods(paths.config(), {}, dashboard._intel(paths.config())["pods"])
    assert next(p for p in pods if p["name"] == "metals")["intel"]["talk"]["asked"] == 1


def test_review_a_ticket_and_cli(monkeypatch):
    tid, errs = tickets.new(**ticket()); assert not errs, errs
    with pytest.raises(ValueError, match="own ticket"):
        memory.review("fxmacro", tid, "fine")
    with pytest.raises(ValueError, match="no ticket"):
        memory.review("metals", "tnope", "fine")
    r = memory.review("metals", tid, "Clashes with my USD long")
    assert r["to"] == "fxmacro" and r["instrument"] == "EURUSD"
    monkeypatch.setenv("AURUM_DESK_ROLE", "indices")
    extras.board(["review", tid, "No", "objection"])
    assert [(v["pod"], v["text"]) for v in memory.reviews(tid)] == [("metals", "Clashes with my USD long"),
                                                                     ("indices", "No objection")]


def test_runner_picks_a_reviewer_that_did_not_propose():
    from conftest import backdate_phase
    backdate_phase(20)
    cfg = paths.config()
    tid, _ = tickets.new(**ticket())
    pod, ids = runner.reviewer(cfg)
    assert pod not in ("fxmacro", "systematic") and ids == [tid]
    memory.review(pod, tid, "ok")
    assert runner.reviewer(cfg) is None


def test_brief_review_list_idle_and_quiet(monkeypatch):
    monkeypatch.setenv("AURUM_DESK_DRY", "1")
    from desk import brief
    tid, _ = tickets.new(**ticket())
    text = brief.build("metals")
    assert "Tickets for you to review" in text and tid in text and "You have no closed trades yet" in text
    assert "Quiet for" not in text
    for _ in range(brief.QUIET_RUNS):
        journal.log("agent_run", role="metals", ok=True, seconds=30)
    assert brief.quiet("metals") and "Quiet for" in brief.build("metals")
    memory.review("metals", tid, "ok")
    assert not brief.quiet("metals")
    assert tid not in brief.build("metals").split("Tickets for you to review")[1].split("##")[0]
    head = brief.build(cli.HEAD)
    assert '"pod_closed_trades": 0' in head and "\"text\": \"ok\"" in head
    closed(1.0, pod="metals", instrument="XAUUSD")
    assert "You have no closed trades yet" not in brief.build("metals")


def test_runner_journals_unanswered_asks():
    q = memory.ask("metals", "fxmacro", "?")
    memory.ask("metals", "all", "anyone?")
    assert runner.unanswered_asks({"id": "j1"}, ["fxmacro", "indices"]) == {"fxmacro": [q["id"]]}
    assert journal.recent(["unanswered_asks"], 1)[0]["asks"] == [q["id"]]
