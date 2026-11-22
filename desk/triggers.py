"""Triggers a pod sets for itself (STATE/triggers.json). The clock checks them every minute; one that fires queues a
wake of its pod, at most wakes_per_pod_day a day (DESIGN.md section 6).

Kinds:
  above / below   instrument, level        the bid crosses the level
  time            at (ISO, UTC)            the time passes
  event           ccy, title (substring)   delay_min after a matching calendar event (default 1)
  ticket          ticket, on (open|closed) the ticket reaches that status (a stop or target hit closes it)
  spread          instrument, mult         the spread is wider than mult x normal
Every trigger fires once and lapses at expires (default 24 hours after it was set).
"""
import datetime as dt
import uuid

from desk import clocks, journal, news, paths, spreads

FILE = paths.STATE / "triggers.json"
WAKES = paths.STATE / "wakes.json"
KINDS = ("above", "below", "time", "event", "ticket", "spread")
MAX_PER_POD = 12


def _all():
    return paths.read_json(FILE, [])


def active(pod=None):
    return [g for g in _all() if not g.get("fired") and not g.get("lapsed") and (pod is None or g["pod"] == pod)]


def add(pod, kind, why, cfg=None, **f):
    """Set a trigger. Returns (id, errors)."""
    cfg = cfg or paths.config()
    errs = []
    if pod not in cfg.get("pods", {}):
        errs.append(f"unknown pod {pod}")
    if kind not in KINDS:
        errs.append(f"kind must be one of {', '.join(KINDS)}")
    need = {"above": ("instrument", "level"), "below": ("instrument", "level"), "time": ("at",),
            "event": ("ccy",), "ticket": ("ticket", "on"), "spread": ("instrument", "mult")}.get(kind, ())
    errs += [f"missing {k}" for k in need if f.get(k) in (None, "")]
    if f.get("instrument") and f["instrument"] not in cfg.get("instruments", {}):
        errs.append(f"unknown instrument {f['instrument']}")
    if kind == "ticket" and f.get("on") not in ("open", "closed"):
        errs.append("on must be open or closed")
    if not why:
        errs.append("missing why")
    if len(active(pod)) >= MAX_PER_POD:
        errs.append(f"{pod} already has {MAX_PER_POD} active triggers")
    for k in ("at", "expires"):
        if f.get(k):
            try:
                f[k] = _iso(f[k])
            except ValueError:
                errs.append(f"{k} is not an ISO time")
    if errs:
        return None, errs
    t = clocks.now()
    g = {"id": "g" + uuid.uuid4().hex[:6], "pod": pod, "kind": kind, "why": why,
         "set": t.isoformat(timespec="seconds"),
         "expires": f.pop("expires", None) or (t + dt.timedelta(hours=24)).isoformat(timespec="seconds")}
    g.update({k: v for k, v in f.items() if v not in (None, "")})
    rows = _all()
    rows.append(g)
    paths.write_json(FILE, rows)
    journal.log("trigger_set", **g)
    return g["id"], []


def _iso(s):
    t = dt.datetime.fromisoformat(str(s))
    if t.tzinfo is None:
        t = t.replace(tzinfo=clocks.UTC)
    return t.astimezone(clocks.UTC).isoformat(timespec="seconds")


def remove(gid, pod=None):
    rows = _all()
    hit = False
    for g in rows:
        if g["id"] == gid and (pod is None or g["pod"] == pod) and not g.get("fired"):
            g["lapsed"] = "removed"
            hit = True
    paths.write_json(FILE, rows)
    return hit


def _fires(g, b, cfg, state, t):
    k = g["kind"]
    if k == "time":
        return t >= dt.datetime.fromisoformat(g["at"])
    if k == "ticket":
        tk = state.get(g["ticket"])
        return bool(tk) and (tk.get("status") == g["on"] or g["on"] == "open" and tk.get("status") == "closed")
    if k == "event":
        d = dt.timedelta(minutes=float(g.get("delay_min", 1)))
        for e in news.events(t - d - dt.timedelta(minutes=60), t - d):
            if e["ccy"] == g["ccy"] and g.get("title", "").lower() in (e["title"] or "").lower():
                return True
        return False
    sym = b.resolve(g["instrument"])
    tick = b.tick(sym) if sym else None
    if not tick:
        return False
    if k == "above":
        return tick["bid"] >= float(g["level"])
    if k == "below":
        return tick["bid"] <= float(g["level"])
    if k == "spread":
        spec = b.spec(sym)
        norm = spreads.normal(b, sym, spec, t) if spec else None
        return bool(norm) and tick["ask"] - tick["bid"] > float(g["mult"]) * norm
    return False


def check(b, cfg, state, t=None):
    """Fire what is due, lapse what expired. Returns the fired triggers."""
    t = t or clocks.now()
    rows = _all()
    fired = []
    changed = False
    for g in rows:
        if g.get("fired") or g.get("lapsed"):
            continue
        if t >= dt.datetime.fromisoformat(g["expires"]):
            g["lapsed"] = "expired"
            changed = True
            continue
        try:
            hit = _fires(g, b, cfg, state, t)
        except Exception as e:  # a bad trigger must not stop the clock
            g["lapsed"] = f"error: {e}"
            changed = True
            continue
        if hit:
            g["fired"] = t.isoformat(timespec="seconds")
            fired.append(g)
            changed = True
            journal.log("trigger_fired", id=g["id"], pod=g["pod"], kind=g["kind"], why=g["why"])
    if changed:
        cutoff = (t - dt.timedelta(days=7)).isoformat()
        rows = [g for g in rows if not (g.get("fired") or g.get("lapsed")) or g.get("expires", "") >= cutoff]
        paths.write_json(FILE, rows)
    return fired


def wakes_today(pod, t=None):
    w = paths.read_json(WAKES, {})
    return w.get(clocks.trading_day(t).isoformat(), {}).get(pod, 0)


def count_wake(pod, t=None):
    w = paths.read_json(WAKES, {})
    day = clocks.trading_day(t).isoformat()
    w = {k: v for k, v in w.items() if k >= (clocks.trading_day(t) - dt.timedelta(days=7)).isoformat()}
    w.setdefault(day, {})[pod] = w.get(day, {}).get(pod, 0) + 1
    paths.write_json(WAKES, w)
