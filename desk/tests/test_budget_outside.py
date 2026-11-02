"""The weekly throttle sees chat and desk sessions, not only the autopilot (owner 2026-11-02, item 6)."""
import json
import os
import sys
from datetime import datetime

from desk import allowance, paths

sys.path.insert(0, str(paths.ROOT / "tools" / "autopilot"))
import budget  # noqa: E402


def line(mid, sid, model, ts, out=100, entry="cli"):
    return json.dumps({"type": "assistant", "sessionId": sid, "timestamp": ts, "entrypoint": entry,
                       "message": {"id": mid, "model": model,
                                   "usage": {"input_tokens": 1000, "output_tokens": out,
                                             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}})


def test_outside_prices_dedupes_and_skips_autopilot(tmp_path):
    proj = tmp_path / "projects" / "C--algo"
    (proj / "s1" / "subagents").mkdir(parents=True)
    t = "2026-11-01T10:00:00Z"
    chat = proj / "s1.jsonl"
    # the same message twice (streaming): the later usage counts once
    chat.write_text(line("m1", "s1", "claude-opus-5-5", t, out=10) + "\n"
                    + line("m1", "s1", "claude-opus-5-5", t, out=200) + "\n", encoding="utf-8")
    (proj / "s1" / "subagents" / "a.jsonl").write_text(line("m2", "s1", "claude-haiku-5-5", t) + "\n")
    (proj / "ap.jsonl").write_text(line("m3", "auto1", "claude-sonnet-5-5", t, entry="sdk-cli") + "\n")
    (proj / "desk.jsonl").write_text(line("m4", "d1", "claude-sonnet-5-5", t, entry="sdk-cli") + "\n"
                                     + line("m5", "d1", "claude-sonnet-5-5", "2026-10-20T10:00:00Z") + "\n")
    rows = [{"models": ["claude-opus-5-5"], "cost_usd": 2.0, "input": 1_000_000, "output": 0,
             "cache_read": 0, "cache_create": 0},
            {"models": ["claude-sonnet-5-5"], "cost_usd": 1.0, "input": 1_000_000, "output": 0,
             "cache_read": 0, "cache_create": 0}]
    cache = tmp_path / "cache.json"
    args = dict(projects=tmp_path / "projects", cache_path=cache, skip_sessions={"auto1"})
    o = budget.outside(datetime(2026, 10, 30, 18), rows, **args)
    opus = 2e-6 * (1000 + 5 * 200)
    haiku = 2e-6 * (1000 + 5 * 100)          # no haiku run to fit from: the dearest rate
    sonnet = 1e-6 * (1000 + 5 * 100)         # m5 is last week's
    assert abs(o["by"]["chat"] - (opus + haiku)) < 1e-3
    assert abs(o["by"]["desk/other"] - sonnet) < 1e-3
    assert o["tokens"] == 1200 + 1100 + 1100
    # a second call reads only new bytes and gives the same answer
    with open(chat, "a", encoding="utf-8") as f:
        f.write(line("m6", "s1", "claude-opus-5-5", t) + "\n")
    o2 = budget.outside(datetime(2026, 10, 30, 18), rows, **args)
    assert o2["tokens"] == o["tokens"] + 1100
    assert json.loads(cache.read_text())[str(chat)]["off"] == chat.stat().st_size


def test_allowance_adds_the_chat_share(tmp_path, monkeypatch):
    monkeypatch.setattr(allowance, "AP_LOGS", tmp_path)
    start = datetime(2026, 10, 30, 18)
    p = tmp_path / "budget_status.json"
    p.write_text(json.dumps({"week_start": "2026-10-30T18:00", "outside_by": {"chat": 40.5, "desk/other": 9}}))
    assert allowance.chat_usd(start) == 40.5             # the desk's share is counted from its own journal
    assert allowance.chat_usd(datetime(2026, 11, 6, 18)) == 0.0     # another week
    old = datetime.now().timestamp() - 3 * 3600
    os.utime(p, (old, old))
    assert allowance.chat_usd(start) == 0.0              # stale


def test_status_never_skips_with_enforce_off(tmp_path, monkeypatch):
    cfgf = tmp_path / "budget.json"
    monkeypatch.setattr(budget, "CONFIG", cfgf)
    monkeypatch.setattr(budget, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(budget, "desk_reserve_usd", lambda: 0.0)
    now = datetime(2026, 11, 2, 12)
    monkeypatch.setattr(budget, "load", lambda: [{"ts": "2026-11-02T10:00:00", "role": "finder", "cost_usd": 99.0,
                                                  "input": 1, "output": 1, "cache_read": 0, "cache_create": 0}])
    cfgf.write_text(json.dumps({"weekly_usd": 100, "skip_above": 0.7}))
    assert budget.status(now, with_outside=False)["skip"]
    cfgf.write_text(json.dumps({"weekly_usd": 100, "skip_above": 0.7, "enforce": False}))
    s = budget.status(now, with_outside=False)
    assert not s["skip"] and s["enforce"] is False and s["fraction"] == 0.99
