"""The forecast ledger (owner 2026-11-01): each pod writes down its calls on markets, the scorekeeper grades them
against the real price, and the skill feeds the pod's score and its token share.

A forecast is "SYM closes above (up) or below (down) a level HOURS from now, with probability PROB". The level is
the mid price when the forecast is made, unless the pod names one. At the due time the scorekeeper takes the close of
the first M15 bar at or after it: 1 if the call came true, 0 if not.

Skill is the Brier score against a coin flip: 1 - mean((p - outcome)^2) / 0.25, so 0 is no better than 0.5 on every
call, 1 is perfect, and a confident wrong call costs far more than a confident right one earns. It is shrunk by
n/(n+SHRINK) so a handful of lucky calls is not skill.

Two append-only files in logs/desk/state (pods write one while the scorekeeper writes the other, so no write is lost):
forecasts.jsonl (the calls) and forecast_grades.jsonl (the outcomes).
"""
import datetime as dt
import uuid

from desk import clocks, journal, paths

FILE = paths.STATE / "forecasts.jsonl"
GRADES = paths.STATE / "forecast_grades.jsonl"
PROB_MIN, PROB_MAX = 0.5, 0.99
HOURS_MIN, HOURS_MAX = 1, 120  # 120 hours of M15 bars still fit in the 1000 the grader fetches
MAX_OPEN = 12                  # open calls a pod may hold at once
SHRINK = 20
WINDOW = dt.timedelta(weeks=8)  # the scorekeeper's window
GIVE_UP = dt.timedelta(days=10)  # a call the bars still cannot settle by then is void
BASELINE = 0.25                 # the Brier score of always saying 0.5


def _grades():
    return {g["id"]: g for g in paths.read_jsonl(GRADES)}


def all_rows():
    """Every forecast, newest last, with its grade folded in (status open, graded or void)."""
    gr = _grades()
    out = []
    for f in paths.read_jsonl(FILE):
        g = gr.get(f["id"])
        out.append(f | ({"status": "void" if g.get("void") else "graded"} | g if g else {"status": "open"}))
    return out


def open_for(pod=None):
    return [f for f in all_rows() if f["status"] == "open" and (pod is None or f["pod"] == pod)]


def new(pod, instrument, direction, prob, hours, why, level=None, t=None):
    """Record one call. level None takes the mid price from the broker. Raises ValueError on a bad call."""
    t = t or clocks.now()
    direction = str(direction).lower()
    if pod not in paths.config().get("pods", {}):
        raise ValueError(f"unknown pod {pod}")
    if direction not in ("up", "down"):
        raise ValueError("direction is up or down")
    prob, hours = float(prob), float(hours)
    if not PROB_MIN <= prob <= PROB_MAX:
        raise ValueError(f"prob is the chance the call comes true, {PROB_MIN} to {PROB_MAX}")
    if not HOURS_MIN <= hours <= HOURS_MAX:
        raise ValueError(f"hours is {HOURS_MIN} to {HOURS_MAX}")
    if not str(why).strip():
        raise ValueError("say why: the reason is graded with the call in the pod's own review")
    if len(open_for(pod)) >= MAX_OPEN:
        raise ValueError(f"{pod} already has {MAX_OPEN} open calls; let some settle first")
    if level is None:
        level = _mid(instrument)
    row = {"id": "f" + uuid.uuid4().hex[:8], "pod": pod, "instrument": instrument, "direction": direction,
           "prob": round(prob, 3), "hours": hours, "level": float(level),
           "t": t.isoformat(timespec="seconds"), "due": (t + dt.timedelta(hours=hours)).isoformat(timespec="seconds"),
           "why": str(why).strip()}
    paths.append_jsonl(FILE, row)
    journal.log("forecast", **{k: row[k] for k in ("id", "pod", "instrument", "direction", "prob", "hours", "level")})
    return row


def _mid(instrument):
    from desk import broker
    b = broker.connect(paths.config())
    try:
        if not b.connected():
            raise ValueError(f"desk terminal not connected ({getattr(b, 'why', '')}); give level=PRICE")
        sym = b.resolve(instrument)
        tk = b.tick(sym) if sym else None
        if not tk:
            raise ValueError(f"no quote for {instrument}; give level=PRICE")
        return round((tk["bid"] + tk["ask"]) / 2, 6)
    finally:
        b.shutdown()


def _settle(f, df):
    """The close of the first bar at or after the due time, or None while there is none yet."""
    from desk import broker as bk
    due = bk.utc_to_server_epoch(dt.datetime.fromisoformat(f["due"]))
    for r in df.itertuples():
        if int(r.time) >= due:
            return float(r.close), bk.server_epoch_to_utc(int(r.time)).isoformat(timespec="minutes")
    return None


def grade(b=None, t=None):
    """Grade every call that is due. Returns how many were settled this pass."""
    t = t or clocks.now()
    todo = [f for f in open_for() if dt.datetime.fromisoformat(f["due"]) <= t]
    if not todo:
        return 0
    own = b is None
    if own:
        from desk import broker
        b = broker.connect(paths.config())
    try:
        if not b.connected():
            return 0
        bars, n = {}, 0
        for f in todo:
            if f["instrument"] not in bars:
                sym = b.resolve(f["instrument"])
                bars[f["instrument"]] = b.bars(sym, "M15", 1000) if sym else None
            df = bars[f["instrument"]]
            res = _settle(f, df) if df is not None and len(df) else None
            row = {"id": f["id"], "graded": t.isoformat(timespec="seconds")}
            if res is None:
                if t - dt.datetime.fromisoformat(f["due"]) <= GIVE_UP:
                    continue
                row["void"] = "no bars to settle it"
            else:
                close, bar_t = res
                if close == f["level"]:
                    row["void"] = "closed exactly on the level"
                else:
                    hit = close > f["level"] if f["direction"] == "up" else close < f["level"]
                    row |= {"close": close, "bar": bar_t, "outcome": int(hit),
                            "brier": round((f["prob"] - int(hit)) ** 2, 4)}
            paths.append_jsonl(GRADES, row)
            journal.log("forecast_graded", pod=f["pod"], **row)
            n += 1
        return n
    finally:
        if own:
            b.shutdown()


def skill(pod, t=None, rows=None):
    """A pod's record over the window: graded calls, hit rate, mean Brier, raw and shrunk skill, open calls."""
    t = t or clocks.now()
    rows = all_rows() if rows is None else rows
    start = (t - WINDOW).isoformat()
    mine = [f for f in rows if f["pod"] == pod]
    done = [f for f in mine if f["status"] == "graded" and f.get("graded", "") >= start]
    n = len(done)
    out = {"graded": n, "open": sum(1 for f in mine if f["status"] == "open"), "hit": None, "brier": None,
           "skill_raw": None, "skill": 0.0}
    if n:
        brier = sum(f["brier"] for f in done) / n
        raw = 1 - brier / BASELINE
        out |= {"hit": round(sum(f["outcome"] for f in done) / n, 2), "brier": round(brier, 4),
                "skill_raw": round(raw, 3), "skill": round(raw * n / (n + SHRINK), 3)}
    return out


def skills(t=None):
    rows = all_rows()
    return {p: skill(p, t, rows) for p in paths.config().get("pods", {})}


def brief(pod, t=None):
    """What a pod sees in its brief: its own record and calls, and the other pods' open calls."""
    rows = all_rows()
    mine = [f for f in rows if f["pod"] == pod]
    keep = ("id", "instrument", "direction", "prob", "level", "due", "why")
    return {"your_skill": skill(pod, t, rows),
            "your_open": [{k: f[k] for k in keep} for f in mine if f["status"] == "open"],
            "your_last_graded": [{k: f.get(k) for k in ("id", "instrument", "direction", "prob", "level", "close",
                                                        "outcome", "why")}
                                 for f in mine if f["status"] == "graded"][-5:],
            "other_pods_open": [{"pod": f["pod"]} | {k: f[k] for k in keep}
                                for f in rows if f["status"] == "open" and f["pod"] != pod][-15:]}
