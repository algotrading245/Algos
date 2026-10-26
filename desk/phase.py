"""Which build phase the desk is trading in, counted from the first tick on a connected demo account.

Phase 1, days 0-13: systematic and FX macro pods, quarter risk.
Phase 2, days 14-27: all pods, half risk.
Phase 3, day 28 on: the full desk, full risk; the 8-week live gate counts from here.
Phase 4: live, only when risk.json allows it (the owner's yes); half risk the first month.
"""
import datetime as dt

from desk import clocks, paths

FILE = paths.STATE / "phase.json"


def state():
    return paths.read_json(FILE, {})


def start(account_kind):
    """Record day 0 the first time the desk sees a connected account. Returns the state."""
    s = state()
    if not s.get("day0") and account_kind == "demo":
        s = {"day0": clocks.now().isoformat(timespec="seconds"), "account": "demo"}
        paths.write_json(FILE, s)
    if account_kind == "live" and not s.get("live_day0"):
        s["live_day0"] = clocks.now().isoformat(timespec="seconds")
        paths.write_json(FILE, s)
    return s


def days_in(s=None, key="day0"):
    s = s if s is not None else state()
    if not s.get(key):
        return None
    return (clocks.now() - dt.datetime.fromisoformat(s[key])).days


def current(account_kind=None):
    """1-4, or 0 before the desk has traded (no account seen yet)."""
    s = state()
    if account_kind == "live" or s.get("live_day0") and account_kind != "demo":
        return 4
    d = days_in(s)
    if d is None:
        return 0
    return 1 if d < 14 else 2 if d < 28 else 3


def risk_scale(prof, ph=None):
    ph = current() if ph is None else ph
    if ph == 0:
        return 0.0
    scale = float(prof.get("risk_scale_by_phase", {}).get(str(ph), 1.0))
    if ph == 4 and (days_in(key="live_day0") or 0) >= 30:
        scale = 1.0
    return scale


ALLOC = paths.STATE / "alloc.json"  # written weekly by the scorekeeper


def pods_active(cfg, ph=None):
    """Pods this phase admits, less any the scorekeeper paused (below the shadow benchmark 6 weeks running)."""
    ph = current() if ph is None else ph
    paused = set(paths.read_json(ALLOC, {}).get("paused") or [])
    return [p for p, v in cfg.get("pods", {}).items() if ph >= v.get("phase", 1) and p not in paused]


def tilt(pod):
    """The competition's risk multiplier for a pod: its share over its base share, held to 0.5-1.5 (1 before the
    first weekly allocation)."""
    a = paths.read_json(ALLOC, {})
    share, base = (a.get("shares") or {}).get(pod), (a.get("base") or {}).get(pod)
    if share is None or not base:
        return 1.0
    return min(1.5, max(0.5, share / base))
