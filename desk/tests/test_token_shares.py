import pytest

from desk import paths, phase, runner, scorekeeper
from desk.brief import build

START = "2026-09-01"


def _sc(**pods):
    """A scores dict: pods given as name=(trades, score, forecast_skill); the rest of the config's pods idle."""
    out = {p: {"trades": 0, "R_per_trade": 0.0, "score": 0.0} for p in paths.config()["pods"]}
    fc = {}
    for p, (n, s, f) in pods.items():
        out[p] = {"trades": n, "R_per_trade": s, "score": s, "forecast_skill": f}
        fc[p] = {"skill": f}
    return {"window": [START, "2026-10-27"], "pods": out, "forecasts": fc, "shadow_r_per_trade": None}


def test_contribution_counts_only_what_others_got():
    know = [{"t": "2026-10-01", "id": "k1", "pod": "metals", "text": "x"},
            {"t": "2026-10-02", "kind": "endorse", "id": "k1", "pod": "fxmacro"},
            {"t": "2026-10-02", "kind": "endorse", "id": "k1", "pod": "crypto"},
            {"t": "2026-10-02", "kind": "endorse", "id": "k1", "pod": "metals"},     # self-endorse: no
            {"t": "2026-08-01", "kind": "endorse", "id": "k1", "pod": "indices"}]    # before the window: no
    board = [{"t": "2026-10-03", "kind": "reply", "pod": "metals"},
             {"t": "2026-10-03", "kind": "review", "pod": "metals"},
             {"t": "2026-10-03", "kind": "ask", "pod": "metals"}]                     # asking is not giving
    c = scorekeeper.contribution("metals", START, board, know)
    assert c == {"endorsed": 2, "replies_reviews": 2, "points": 0.25}
    assert scorekeeper.contribution("fxmacro", START, board, know)["points"] == 0


def test_token_score_needs_trades_before_trading_counts():
    sc = _sc(metals=(5, 0.8, 0.2), fxmacro=(30, 0.5, -2.0))
    tok = scorekeeper.token_scores(sc, board=[], know=[])
    assert tok["metals"]["trading"] == 0 and tok["metals"]["forecast"] == 0.2 and tok["metals"]["score"] == 0.2
    assert tok["fxmacro"]["trading"] == 0.5 and tok["fxmacro"]["forecast"] == -1.0  # clipped
    assert tok["fxmacro"]["score"] == -0.5


def test_token_shares_move_slowly_inside_floor_and_cap(monkeypatch):
    monkeypatch.setattr(scorekeeper, "token_scores", lambda sc: {
        p: {"score": 3.0 if p == "metals" else -1.0} for p in paths.config()["pods"]})
    cfg = paths.config()
    a = scorekeeper.allocate(_sc(), {}, cfg)
    ts = a["token_shares"]
    assert sum(ts.values()) == pytest.approx(1, abs=1e-3)  # shares are rounded to 4 places
    assert all(scorekeeper.TOKEN_FLOOR - 1e-9 <= s <= scorekeeper.TOKEN_CAP + 1e-9 for s in ts.values())
    base = a["base"]
    assert base["metals"] < ts["metals"] < 0.35  # up, but one week's step does not reach the cap
    # a week later it climbs again, from last week's share
    b = scorekeeper.allocate(_sc(), a, cfg)
    assert b["token_shares"]["metals"] > ts["metals"]
    assert "token_scores" in a and a["shares"]  # the risk shares are still there beside them


def test_paused_pod_gets_no_tokens(monkeypatch):
    monkeypatch.setattr(scorekeeper, "token_scores", lambda sc: {p: {"score": 0} for p in paths.config()["pods"]})
    a = scorekeeper.allocate(_sc(), {"paused": ["crypto"]}, paths.config())
    assert a["token_shares"]["crypto"] == 0


def test_pod_budget_follows_token_shares(monkeypatch):
    cfg = dict(paths.config())
    cfg["budgets"] = {"pod": 1000}
    monkeypatch.setattr(phase, "pods_active", lambda c, *a: list(c["pods"]))
    shares = {p: 0.1 for p in cfg["pods"]}
    shares["metals"] = 0.35
    tot = sum(shares.values())
    paths.write_json(phase.ALLOC, {"shares": {p: 1 / len(shares) for p in shares}, "token_shares": shares,
                                   "token_scores": {"metals": {"score": 0.9}}})
    assert runner.pod_budget("metals", cfg) == int(1000 * 0.35 / tot)
    text = build("metals")
    assert "## Your token share this week" in text and "0.35" in text
