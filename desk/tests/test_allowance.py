import json

import pytest

from desk import allowance, jobs, journal, paths, phase, runner, triggers


@pytest.fixture
def ap(monkeypatch, tmp_path):
    """The autopilot's usage log in a temp dir; the plan's real budget.json (weekly 100, reset Fri 18:00)."""
    monkeypatch.setattr(allowance, "AP_LOGS", tmp_path)
    monkeypatch.setattr(allowance, "AP_BUDGET", tmp_path / "budget.json")
    (tmp_path / "budget.json").write_text(json.dumps(allowance.AP_DEFAULTS))
    return tmp_path


def test_no_weekly_dollars_keeps_the_configured_pool(cfg, ap):
    cfg["budgets"].pop("pod_weekly_usd", None)
    assert allowance.fit(cfg) == {"configured": 800000, "pool": 800000}


def test_pool_fitted_to_the_week_and_throttled_near_the_cap(cfg, ap, monkeypatch):
    cfg["budgets"]["pod_weekly_usd"] = 15
    f = allowance.fit(cfg)  # Wednesday: Wed, Thu, Fri left; $15 / 3 x 270k tokens = 1.35M > 800k
    assert f["days_left"] == 3 and f["fitted"] == 1_350_000 and f["pool"] == 800_000 and f["throttle"] == 1.0
    monkeypatch.setenv("AURUM_DESK_NOW", "2026-10-19T14:00:00")  # Monday: pods spent $12
    journal.log("agent_run", role="fxmacro", tokens=100, usd=12.0)
    journal.log("agent_run", role="head-trader", tokens=100, usd=5.0)  # not a pod: not in the pods' week
    monkeypatch.setenv("AURUM_DESK_NOW", "2026-10-21T14:00:00")
    f = allowance.fit(cfg)
    assert f["used_usd"] == 12.0 and f["pool"] == 270_000  # $3 left / 3 days
    (ap / "usage.jsonl").write_text(json.dumps({"ts": "2026-10-20T10:00:00", "cost_usd": 60}) + "\n"
                                    + json.dumps({"ts": "2026-10-15T10:00:00", "cost_usd": 500}) + "\n")  # last week
    f = allowance.fit(cfg)  # past skip_above: the pods' own slice is not cut (A7, owner 2026-11-02)
    assert f["account_fraction"] == 0.77 and f["throttle"] == 1.0 and f["pool"] == 270_000
    with open(ap / "usage.jsonl", "a") as fh:
        fh.write(json.dumps({"ts": "2026-10-20T11:00:00", "cost_usd": 30}) + "\n")
    f = allowance.fit(cfg)  # the whole weekly cap spent: a quarter
    assert f["account_fraction"] == 1.07 and f["throttle"] == 0.25 and f["pool"] == 67_500


def test_today_spend_does_not_shrink_todays_pool(cfg, ap):
    cfg["budgets"]["pod_weekly_usd"] = 3
    journal.log("agent_run", role="fxmacro", tokens=100, usd=2.0)  # today
    assert allowance.fit(cfg)["used_usd"] == 0 and allowance.pool(cfg) == 270_000


def test_wake_cap_follows_the_token_share(cfg, ap):
    base = cfg["wakes_per_pod_day"]
    active = phase.pods_active(cfg)
    paths.write_json(phase.ALLOC, {"token_shares": {p: 1 / len(active) for p in active}})
    assert {allowance.wake_cap(p, cfg) for p in active} == {base}
    big, small = active[0], active[1]
    shares = {p: 0.1 for p in active} | {big: 0.35, small: 0.01}
    paths.write_json(phase.ALLOC, {"token_shares": shares})
    total = sum(shares.values())
    assert allowance.wake_cap(big, cfg) == min(2 * base, round(base * 0.35 * len(active) / total))
    assert allowance.wake_cap(small, cfg) == 1
    paths.write_json(phase.ALLOC, {"token_shares": shares, "paused": [big]})
    assert allowance.wake_cap(big, cfg) == 0


def test_spent_slice_refuses_the_wake(cfg, ap):
    cfg["budgets"]["pod_weekly_usd"] = 15
    pod = phase.pods_active(cfg)[0]
    slice_ = allowance.pod_budget(pod, cfg)
    assert 0 < slice_ < 800_000 and not allowance.slice_spent(pod, cfg)
    runner.add_spend(pod, slice_, cfg)
    assert allowance.slice_spent(pod, cfg)
    assert jobs.wake(pod, ["g1"], cfg) is None and triggers.wakes_today(pod) == 0
    assert journal.recent(["wake_refused"], 1)[-1]["why"] == "token slice spent for today"
    other = phase.pods_active(cfg)[1]
    assert jobs.wake(other, ["g2"], cfg)
    runner.add_spend(other, 800_000, cfg)  # the whole pool gone: every pod stops
    assert all(allowance.slice_spent(p, cfg) for p in phase.pods_active(cfg))


def test_status_lists_every_pod(cfg, ap):
    s = allowance.status(cfg)
    assert s["pool"] == 800_000 and set(s["pods"]) == set(cfg["pods"])
    assert all({"share", "slice", "spent", "wake_cap", "wakes"} <= set(v) for v in s["pods"].values())
