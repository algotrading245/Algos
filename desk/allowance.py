"""The pods' token allowance (owner 2026-11-01): how much each pod may think with today, and how often it may be woken.

  pool       the pods' daily tokens: budgets.pod in config.json, cut to what the pods' weekly dollars
             (budgets.pod_weekly_usd, the pods' own slice) leave for the weekdays to the plan's weekly reset; cut to a
             quarter only when the whole account has spent its weekly cap (tools/autopilot/budget.json; the account =
             the autopilot + the desk + chat sessions). Chat use below the cap does not cut the slice (A7, 2026-11-02).
  pod slice  the pool split by the token shares (alloc.json token_shares, base shares before the first allocation)
             among the pods trading now.
  wake cap   wakes_per_pod_day scaled by the same share against an equal split, 1 to twice the base; a paused pod 0.

Dollars come from the agent_run rows (usd, from Claude's result event); a row without one is priced at the desk's own
tokens per dollar. Only runs before today's trading day count against the week, so the day's pool does not shrink while
the day spends it; the day's own spend is held by the pod slice and the pool.
"""
import datetime as dt
import json
import os
from pathlib import Path

from desk import clocks, journal, paths, phase

BUDGET = paths.STATE / "budget.json"  # runner.add_spend writes it: {trading day: {"pod" and each role: tokens}}
AP_LOGS = Path(os.environ.get("AURUM_AUTOPILOT_LOGS", paths.ROOT / "logs" / "autopilot"))
AP_BUDGET = paths.ROOT / "tools" / "autopilot" / "budget.json"
AP_DEFAULTS = {"weekly_usd": 100.0, "reset_weekday": 4, "reset_hour": 18, "skip_above": 0.7}
TOKENS_PER_USD = 270_000  # measured on Sonnet pod runs, 2026-10; replaced by the desk's own rows once it has some


def share(pod, cfg):
    alloc = paths.read_json(phase.ALLOC, {})
    shares = alloc.get("token_shares") or alloc.get("shares") or {}
    return shares.get(pod, cfg["pods"].get(pod, {}).get("base_share", 0))


def spent_today(key, t=None):
    return paths.read_json(BUDGET, {}).get(clocks.trading_day(t).isoformat(), {}).get(key, 0)


def _ap_config():
    c = dict(AP_DEFAULTS)
    try:
        c.update(json.loads(AP_BUDGET.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return c


def _local(t):
    t = t or clocks.now()
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def week_start(t, c):
    """The plan's last weekly reset at or before t, in local time (as tools/autopilot/budget.py counts it)."""
    now = _local(t)
    d = now.replace(hour=c["reset_hour"], minute=0, second=0, microsecond=0)
    d -= dt.timedelta(days=(now.weekday() - c["reset_weekday"]) % 7)
    return d if d <= now else d - dt.timedelta(days=7)


def days_left(t, c):
    """Weekdays from today to the next reset, both counted, at least 1."""
    today, end = _local(t).date(), (week_start(t, c) + dt.timedelta(days=7)).date()
    n = sum(1 for i in range((end - today).days + 1) if (today + dt.timedelta(days=i)).weekday() < 5)
    return max(1, n)


def tokens_per_usd(rows):
    priced = [r for r in rows if r.get("usd") and r.get("tokens")]
    usd = sum(r["usd"] for r in priced)
    return sum(r["tokens"] for r in priced) / usd if len(priced) >= 3 and usd > 0 else TOKENS_PER_USD


def _usd(r, tpu):
    return r["usd"] if r.get("usd") is not None else (r.get("tokens") or 0) / tpu


def _build(r):
    """An agent_run row of the weekend build job: journal.log keeps a `kind=` field as data_kind."""
    return r.get("data_kind") == "build"


def _week_rows(t, c):
    start = week_start(t, c)
    return [r for r in journal.recent(["agent_run"], 8) if _local(dt.datetime.fromisoformat(r["t"])) >= start]


def account_fraction(t=None, c=None):
    """The account's weekly use against the plan's cap: the autopilot's runs plus the desk's."""
    c = c or _ap_config()
    start = week_start(t, c)
    ap = 0.0
    for line in _read(AP_LOGS / "usage.jsonl"):
        try:
            r = json.loads(line)
            if dt.datetime.fromisoformat(r["ts"]) >= start:
                ap += float(r.get("cost_usd") or 0)
        except (ValueError, KeyError, TypeError):
            pass
    rows = _week_rows(t, c)
    tpu = tokens_per_usd(rows)
    desk = sum(_usd(r, tpu) for r in rows)
    return (ap + desk + chat_usd(start)) / c["weekly_usd"] if c.get("weekly_usd") else 0.0


def chat_usd(start):
    """Chat sessions' dollars this week, from the autopilot budget's last status (tools/autopilot/budget.py prices
    every Claude transcript; owner 2026-11-02). 0 when that status is missing, older than 2 hours or of another week."""
    p = AP_LOGS / "budget_status.json"
    try:
        if dt.datetime.now().timestamp() - p.stat().st_mtime > 7200:
            return 0.0
        s = json.loads(p.read_text(encoding="utf-8"))
        if dt.datetime.fromisoformat(s["week_start"]) != start:
            return 0.0
        return float((s.get("outside_by") or {}).get("chat") or 0)
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def _read(path):
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def fit(cfg, t=None):
    """The pool and how it was reached."""
    t = t or clocks.now()
    b = cfg.get("budgets", {})
    base = b.get("pod")
    if base is None:
        return {"pool": None}
    out = {"configured": base, "pool": base}
    weekly = b.get("pod_weekly_usd")
    if weekly is None:
        return out
    c = _ap_config()
    rows = _week_rows(t, c)
    tpu = tokens_per_usd(rows)
    today = clocks.trading_day(t)
    pods = cfg.get("pods", {})
    used = sum(_usd(r, tpu) for r in rows if r.get("role") in pods and not _build(r)  # build: own budget
               and clocks.trading_day(dt.datetime.fromisoformat(r["t"])) < today)
    left = days_left(t, c)
    fitted = max(0.0, weekly - used) / left * tpu
    frac = account_fraction(t, c)
    # pod_weekly_usd is the pods' own slice of the week (owner 2026-11-02, gap report A7): chat or the autopilot taking
    # the account past skip_above no longer cuts it; only the whole weekly cap spent does (a quarter, the last guard).
    # tools/autopilot/budget.py keeps the slice's unspent part out of the autopilot's room instead.
    throttle = 0.25 if frac >= 1.0 else 1.0
    out.update(weekly_usd=weekly, used_usd=round(used, 2), days_left=left, tokens_per_usd=int(tpu),
               fitted=int(fitted), account_fraction=round(frac, 3), throttle=throttle,
               pool=int(min(base, fitted) * throttle))
    return out


def pool(cfg, t=None):
    return fit(cfg, t)["pool"]


BUILD_STOP = 0.9  # the account's weekly share at which the weekend build job does not run


def build_status(cfg, t=None):
    """The weekend build job's own weekly dollars (budgets.build_weekly_usd, apart from the pods' brief pool; owner
    2026-11-02): spent this week, the cap, and whether it is spent or the account is too near its weekly cap."""
    t = t or clocks.now()
    c = _ap_config()
    rows = _week_rows(t, c)
    tpu = tokens_per_usd(rows)
    used = sum(_usd(r, tpu) for r in rows if _build(r))
    cap = float(cfg.get("budgets", {}).get("build_weekly_usd", 0) or 0)
    frac = account_fraction(t, c)
    why = ("no build_weekly_usd" if not cap else f"build dollars spent ({used:.2f} of {cap:g})" if used >= cap
           else f"account at {frac:.0%} of its weekly cap" if frac >= BUILD_STOP else "")
    return {"used_usd": round(used, 2), "cap_usd": cap, "account_fraction": round(frac, 3), "over": bool(why),
            "why": why}


def pod_budget(pod, cfg, t=None, pool_=None):
    """A pod's own daily tokens: the pool split by the token shares among the pods trading now."""
    p = pool(cfg, t) if pool_ is None else pool_
    if p is None:
        return None
    total = sum(share(q, cfg) for q in phase.pods_active(cfg)) or share(pod, cfg) or 1
    return int(p * share(pod, cfg) / total)


def wake_cap(pod, cfg):
    """Wakes a day: the base scaled by the pod's share against an equal split, 1 to twice the base; 0 when paused."""
    base = int(cfg.get("wakes_per_pod_day", 6))
    active = phase.pods_active(cfg)
    if pod not in active:
        return 0
    total = sum(share(q, cfg) for q in active)
    if total <= 0:
        return base
    return max(1, min(2 * base, round(base * share(pod, cfg) * len(active) / total)))


def slice_spent(pod, cfg, t=None):
    """True when the pods' pool or this pod's slice of it is used up for today."""
    p = pool(cfg, t)
    if p is None:
        return False
    if spent_today("pod", t) >= p:
        return True
    return spent_today(pod, t) >= pod_budget(pod, cfg, t, pool_=p)


def status(cfg, t=None):
    """The pool, how it was fitted, and each pod's slice, spend, wake cap and wakes today."""
    from desk import triggers
    f = fit(cfg, t)
    pods = {}
    for p in cfg.get("pods", {}):
        pods[p] = {"share": share(p, cfg), "slice": pod_budget(p, cfg, t, pool_=f["pool"]) if f["pool"] is not None
                   else None, "spent": spent_today(p, t), "wake_cap": wake_cap(p, cfg),
                   "wakes": triggers.wakes_today(p, t)}
    return f | {"spent": spent_today("pod", t), "pods": pods}
