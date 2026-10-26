"""Trade tickets (desk/tickets.jsonl): an append-only event log, folded into the current state of each ticket.

A ticket is what an agent (or an armed edge) wants; it never sends an order. Life of a ticket:
  proposed -> approved | rejected            (head trader; an armed edge's ticket starts approved)
  approved -> placed (order sent) | blocked  (risk gate, at the next clock tick)
  placed   -> open (filled) | expired | cancelled
  open     -> closed                          (stop, target, time stop, invalidation, kill, owner)
"""
import os
import uuid
from pathlib import Path

from desk import clocks, journal, paths

FILE = Path(os.environ.get("AURUM_DESK_TICKETS", paths.DESK / "tickets.jsonl"))
FIELDS = ("pod", "instrument", "side", "entry", "stop", "targets", "risk_pct", "time_stop", "thesis", "invalidation",
          "evidence", "edge", "confidence", "cites", "expires", "trail", "breakeven_at", "arm", "add_to")
LIVE = ("proposed", "approved", "placed", "open")


def _event(tid, event, **data):
    row = {"t": clocks.now().isoformat(timespec="seconds"), "id": tid, "event": event}
    row.update(data)
    paths.append_jsonl(FILE, row)
    journal.log("ticket_" + event, id=tid, **{k: v for k, v in data.items() if k not in ("thesis", "invalidation")})
    return row


def validate(t, cfg=None):
    """Problems with a ticket's fields, or []. Prices are checked against side and stop."""
    cfg = cfg or paths.config()
    errs = []
    for k in ("pod", "instrument", "side", "stop", "thesis", "invalidation"):
        if t.get(k) in (None, ""):
            errs.append(f"missing {k}")
    if t.get("pod") and t["pod"] not in cfg.get("pods", {}):
        errs.append(f"unknown pod {t['pod']}")
    if t.get("instrument") and t["instrument"] not in cfg.get("instruments", {}):
        errs.append(f"unknown instrument {t['instrument']}")
    if t.get("side") not in ("buy", "sell"):
        errs.append("side must be buy or sell")
    e = t.get("entry") or {"type": "market"}
    if e.get("type") not in ("market", "limit", "stop"):
        errs.append("entry.type must be market, limit or stop")
    if e.get("type") in ("limit", "stop") and not e.get("price"):
        errs.append("entry.price needed for limit and stop")
    try:
        stop = float(t.get("stop"))
        if e.get("price"):
            px = float(e["price"])
            if t.get("side") == "buy" and stop >= px or t.get("side") == "sell" and stop <= px:
                errs.append("stop is on the wrong side of the entry")
        ref = float(e["price"]) if e.get("price") else stop  # a market entry has no price yet: targets pass the stop
        for tg in t.get("targets") or []:
            p = float(tg[0])
            if t.get("side") == "buy" and p <= ref or t.get("side") == "sell" and p >= ref:
                errs.append("target on the wrong side of the entry")
    except (TypeError, ValueError):
        errs.append("stop, entry price and targets must be numbers")
    if t.get("targets") and abs(sum(float(x[1]) for x in t["targets"]) - 1.0) > 0.01:
        errs.append("target shares must add up to 1")
    c = t.get("confidence")
    if c is not None and c not in (1, 2, 3, 4, 5):
        errs.append("confidence is 1-5")
    r = t.get("risk_pct")
    if r is not None and not (0 < float(r) <= 5):
        errs.append("risk_pct must be in (0, 5]")
    return errs


def new(**t):
    """Record a proposed ticket. Returns (id, errors); with errors nothing is recorded."""
    t = {k: t.get(k) for k in FIELDS if t.get(k) is not None}
    t.setdefault("entry", {"type": "market"})
    t.setdefault("targets", [])
    t.setdefault("confidence", 3)
    errs = validate(t)
    if errs:
        journal.log("ticket_invalid", ticket=t, errors=errs)
        return None, errs
    tid = clocks.now().strftime("%m%d%H%M") + "-" + uuid.uuid4().hex[:5]
    status = "approved" if t.get("arm") else "proposed"
    _event(tid, "new", status=status, **t)
    return tid, []


def approve(tid, why="", by="head-trader"):
    return _event(tid, "approve", status="approved", why=why, by=by)


def reject(tid, why, by="head-trader"):
    return _event(tid, "reject", status="rejected", why=why, by=by)


def block(tid, why):
    return _event(tid, "block", status="blocked", why=why)


def placed(tid, **data):
    return _event(tid, "placed", status="placed", **data)


def opened(tid, **data):
    return _event(tid, "open", status="open", **data)


def update(tid, **data):
    return _event(tid, "update", **data)


def closed(tid, **data):
    return _event(tid, "close", status="closed", **data)


def cancel(tid, why, by=None):
    return _event(tid, "cancel", status="cancelled", why=why, by=by)


def expire(tid, why="expired"):
    return _event(tid, "expire", status="expired", why=why)


def fold(rows=None):
    """id -> the ticket as it stands now (fields of every event merged, oldest first, plus a history list)."""
    rows = paths.read_jsonl(FILE) if rows is None else rows
    out = {}
    for r in rows:
        tid = r.get("id")
        if not tid:
            continue
        cur = out.setdefault(tid, {"id": tid, "history": []})
        if r["event"] == "new":
            cur["created"] = r["t"]
        cur["history"].append({"t": r["t"], "event": r["event"], "why": r.get("why")})
        for k, v in r.items():
            if k not in ("id", "event", "t"):
                cur[k] = v
        cur["updated"] = r["t"]
    return out


def live(state=None):
    return {k: v for k, v in (state or fold()).items() if v.get("status") in LIVE}


def by_status(status, state=None):
    return [v for v in (state or fold()).values() if v.get("status") == status]
