import json

from conftest import backdate_phase, set_now, ticket

from desk import paths, risk_gate, tickets


def tk(**over):
    t = ticket(**over)
    t.setdefault("entry", {"type": "market"})
    t.setdefault("targets", [])
    return t


def seed(instrument, pod="systematic", side="buy", risk_now=0.5, status="open"):
    tid, errs = tickets.new(**ticket(pod=pod, instrument=instrument, side=side,
                                     stop=1.095 if side == "buy" else 1.2, edge="seed"))
    assert not errs, errs
    tickets.approve(tid)
    tickets.placed(tid, order=1, volume=0.01, risk_used=risk_now)
    if status == "open":
        tickets.opened(tid, position=2, risk_now=risk_now)
    return tid


def use_profile(name):
    r = paths.risk()
    r["active"] = name
    paths.RISK.write_text(json.dumps(r), encoding="utf-8")


def test_phase1_sizes_at_quarter_of_the_new_edge_cap(b, cfg):
    g = risk_gate.check(tk(), b, cfg)
    assert g["ok"], g["why"]
    # min(0.5, 0.25 new edge) x 0.25 phase 1 = 0.0625% of 10k = $6.25 over a 0.0051 stop ($510/lot) -> 0.01
    assert g["volume"] == 0.01 and g["magic"] == 730001 and g["sl"] == 1.095 and g["kind"] == "market"
    assert g["price"] == 1.1001


def test_phase3_full_risk_and_seasoned_edge(b, cfg):
    backdate_phase(30)
    assert risk_gate.check(tk(), b, cfg)["volume"] == 0.04  # 0.25%: $25 / 510
    state = {f"x{i}": {"id": f"x{i}", "status": "closed", "edge": "test_edge", "pod": "fxmacro",
                       "instrument": "EURUSD", "side": "buy"} for i in range(20)}
    g = risk_gate.check(tk(), b, cfg, state=state)
    assert g["volume"] == 0.09  # 0.5%: $50 / 510


def test_asked_risk_never_above_the_profile(b, cfg):
    backdate_phase(30)
    state = {f"x{i}": {"id": f"x{i}", "status": "closed", "edge": "test_edge"} for i in range(20)}
    assert risk_gate.check(tk(risk_pct=3), b, cfg, state=state)["volume"] == 0.09
    assert risk_gate.check(tk(risk_pct=0.1), b, cfg, state=state)["volume"] == 0.01


def test_kill_file_blocks_everything(b, cfg):
    risk_gate.kill("test", by="owner")
    g = risk_gate.check(tk(), b, cfg)
    assert not g["ok"] and g["why"].startswith("KILL file")
    risk_gate.resume("owner")
    assert risk_gate.check(tk(), b, cfg)["ok"]


def test_pod_and_instrument_rules(b, cfg):
    g = risk_gate.check(tk(pod="metals", instrument="XAUUSD", stop=1.0), b, cfg)
    assert "pod metals not active in phase 1" in g["why"]
    g = risk_gate.check(tk(instrument="XAUUSD"), b, cfg)
    assert "fxmacro does not trade XAUUSD" in g["why"]
    g = risk_gate.check(tk(instrument="GBPUSD"), b, cfg)
    assert "not offered by this broker" in g["why"]
    assert risk_gate.check(tk(pod="systematic"), b, cfg)["ok"]  # free roam


def test_invalid_ticket(b, cfg):
    g = risk_gate.check(tk(stop=None), b, cfg)
    assert g["why"].startswith("invalid") and "missing stop" in g["why"]


def test_netting_and_one_position_per_pod(b, cfg):
    seed("EURUSD", side="sell")
    assert "netting" in risk_gate.check(tk(), b, cfg)["why"]


def test_add_only_onto_a_breakeven_ticket(b, cfg):
    base = seed("EURUSD", pod="fxmacro", risk_now=0.06)
    assert "already holds EURUSD" in risk_gate.check(tk(), b, cfg)["why"]
    assert "already holds EURUSD" in risk_gate.check(tk(add_to=base), b, cfg)["why"]
    tickets.update(base, risk_now=0)
    assert risk_gate.check(tk(add_to=base), b, cfg)["ok"]


def test_max_per_instrument(b, cfg):
    for pod in ("systematic", "event", "crypto"):
        seed("EURUSD", pod=pod, risk_now=0)
    assert "already has 3 desk positions" in risk_gate.check(tk(), b, cfg)["why"]


def test_caps(b, cfg):
    backdate_phase(30)
    seed("GBPUSD", pod="fxmacro", risk_now=1.9)
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("pod cap")


def test_desk_cap(b, cfg):
    backdate_phase(30)
    seed("XAUUSD", pod="metals", risk_now=1.9)
    seed("US500", pod="indices", risk_now=1.9)
    seed("BTCUSD", pod="crypto", risk_now=1.0)
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("desk cap")


def test_group_cap(b, cfg):
    backdate_phase(30)
    seed("GBPUSD", pod="systematic", risk_now=1.2)
    seed("USDJPY", pod="event", risk_now=1.2)
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("group USD cap")


def test_placed_tickets_count_as_open(b, cfg):
    backdate_phase(30)
    seed("GBPUSD", pod="fxmacro", risk_now=1.9, status="placed")
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("pod cap")


def test_price_and_stop_checks(b, cfg, monkeypatch):
    assert "closer than the broker allows" in risk_gate.check(tk(stop=1.10005), b, cfg)["why"]
    g = risk_gate.check(tk(entry={"type": "limit", "price": 1.1002}), b, cfg)
    assert "through the market" in g["why"]
    g = risk_gate.check(tk(entry={"type": "stop", "price": 1.1000}), b, cfg)
    assert "already passed" in g["why"]
    assert "stop too wide" in risk_gate.check(tk(stop=1.0), b, cfg)["why"]
    g = risk_gate.check(tk(entry={"type": "limit", "price": 1.0990}), b, cfg)
    assert g["ok"] and g["kind"] == "limit" and g["price"] == 1.099
    set_now(monkeypatch, "2026-10-21T14:10:00")
    assert "price is stale" in risk_gate.check(tk(), b, cfg)["why"]


def test_margin_share(b, cfg):
    b.margin_per_lot = 1e6
    assert "margin" in risk_gate.check(tk(), b, cfg)["why"]


def test_spread_and_news_refusals(b, cfg, monkeypatch):
    monkeypatch.setattr(risk_gate.spreads, "check", lambda *a, **k: (False, "3.0x the normal spread"))
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("spread:")
    monkeypatch.setattr(risk_gate.spreads, "check", lambda *a, **k: (True, ""))
    monkeypatch.setattr(risk_gate.news, "blocking",
                        lambda *a, **k: {"ccy": "USD", "title": "NFP", "t": "2026-10-21T14:01"})
    assert risk_gate.check(tk(), b, cfg)["why"].startswith("news: USD NFP")


def test_live_account_refused(b, cfg):
    b.kind = "live"
    assert "does not allow live" in risk_gate.check(tk(), b, cfg)["why"]


def test_prop_rules(b, cfg, monkeypatch):
    use_profile("prop_10k")
    g = risk_gate.check(tk(pod="systematic", instrument="BTCUSD", stop=1.0), b, cfg)
    assert "crypto not allowed" in g["why"]
    set_now(monkeypatch, "2026-10-23T19:30:00")  # Friday 15:30 New York
    assert "weekend cutoff" in risk_gate.check(tk(), b, cfg)["why"]


def test_prop_worst_case_floor(b, cfg):
    use_profile("prop_10k")
    _, prof = risk_gate.profile()
    risk_gate.update_limits({"balance": 10000.0, "equity": 10000.0}, prof)
    b.balance = 9720.0
    seed("GBPUSD", pod="systematic", risk_now=0.3)
    g = risk_gate.check(tk(), b, cfg)
    assert "would breach the day floor" in g["why"]


def test_halts():
    _, prof = risk_gate.profile()
    s = risk_gate.update_limits({"balance": 10000.0, "equity": 10000.0}, prof)
    assert s["floors"]["day"] == 9700 and abs(s["floors"]["kill"] - 8800) < 1e-6 and "halt" not in s
    s = risk_gate.update_limits({"balance": 10000.0, "equity": 9690.0}, prof)
    assert s["halt"]["level"] == "day" and risk_gate.halted().startswith("day halt")
    s = risk_gate.update_limits({"balance": 10000.0, "equity": 8700.0}, prof)
    assert s["halt"]["level"] == "kill"
    s = risk_gate.update_limits({"balance": 10000.0, "equity": 9990.0}, prof)
    assert s["halt"]["level"] == "kill"  # only the owner clears a kill
    risk_gate.resume("owner")
    assert risk_gate.halted() is None and risk_gate.limits()["peak"] == 9990.0


def test_a_new_account_starts_its_own_lines():
    _, prof = risk_gate.profile()
    risk_gate.update_limits({"balance": 15000.0, "equity": 15000.0, "company": "A", "kind": "demo"}, prof)
    s = risk_gate.update_limits({"balance": 10000.0, "equity": 10000.0, "company": "B", "kind": "demo"}, prof)
    assert "halt" not in s and s["peak"] == 10000.0 and s["floors"]["day"] == 9700
    assert s["record"] == {"account": "B/demo", "peak": 10000.0, "max_dd_pct": 0.0, "since": s["record"]["since"]}


def test_day_halt_clears_next_day(monkeypatch):
    _, prof = risk_gate.profile()
    risk_gate.update_limits({"balance": 10000.0, "equity": 10000.0}, prof)
    risk_gate.update_limits({"balance": 10000.0, "equity": 9690.0}, prof)
    assert risk_gate.halted()
    set_now(monkeypatch, "2026-10-22T14:00:00")
    s = risk_gate.update_limits({"balance": 9690.0, "equity": 9690.0}, prof)
    assert "halt" not in s


def test_prop_floors():
    r = paths.risk()
    prof = r["profiles"]["prop_10k"]
    fl = risk_gate.floors({"day_balance": 10200, "day_equity": 10100, "peak": 10300, "week_equity": 10000}, prof)
    assert fl["day"] == 10200 - 300  # 3% of the initial balance below the day's start
    assert abs(fl["kill"] - max(10300 * 0.93, 9200)) < 1e-6
    assert abs(fl["week"] - 9500) < 1e-6
