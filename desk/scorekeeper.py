"""The scorekeeper (DESIGN.md sections 5 and 9): scores, the pod competition and the research bridge, all in code.

daily()   scores every pod over the last 4 weeks into state/scores.json and reports/scores_<date>.md, and follows each
          rejected ticket on paper (state/rejected_shadow.json) so the head trader's vetoes are scored too.
weekly()  daily(), then the allocation (state/alloc.json): a pod with fewer than 20 trades keeps its base share; the
          rest move toward base x max(0.25, 1 + R per trade), at most 10 points a week, inside 10-30%. A pod below the
          shadow benchmark 6 weeks running is paused until its playbook is rewritten. Then playbooks.check() for each
          pod, and the research bridge: an (edge, instrument) with 30+ closed trades and positive R goes once to
          docs/ideas/queue.jsonl with source "desk".

Credit: a winner that cites board posts gives 0.25 of its R to the pods that wrote them (split evenly); the owner
keeps 0.75. A loser's R stays with its owner.
"""
import datetime as dt
from collections import defaultdict

from desk import clocks, journal, memory, paths, playbooks, systematic, tickets

WINDOW = dt.timedelta(weeks=4)
MIN_TRADES = 20       # below this a pod keeps its base share and is not judged against the shadow
FLOOR, CAP, STEP = 0.10, 0.30, 0.10
PAUSE_WEEKS = 6
CITE_SHARE = 0.25
BRIDGE_TRADES = 30
SHADOW_DAYS = 5       # a rejected ticket still open after this many days is marked to market
SHADOW_GIVE_UP = 10   # and one that could not be resolved by this age is dropped

SCORES = paths.STATE / "scores.json"
ALLOC = paths.STATE / "alloc.json"
REJECTED = paths.STATE / "rejected_shadow.json"
BRIDGED = paths.STATE / "bridged.json"
QUEUE = paths.ROOT / "docs" / "ideas" / "queue.jsonl"


# ---- scores ----------------------------------------------------------------------------------------------------------

def _closed(state, start=None, end=None):
    return [v for v in tickets.by_status("closed", state) if v.get("R") is not None
            and (start is None or v.get("updated", "") >= start) and (end is None or v.get("updated", "") < end)]


def credited(rows, board=None):
    """pod -> list of (R, ticket id) after splitting cited winners."""
    owner = {r["id"]: r.get("pod") for r in (memory.board(10 ** 9) if board is None else board)}
    out = defaultdict(list)
    for v in rows:
        R, pod = float(v["R"]), v.get("pod")
        others = sorted({owner[c] for c in v.get("cites") or [] if owner.get(c) and owner[c] != pod})
        if R > 0 and others:
            out[pod].append((R * (1 - CITE_SHARE), v["id"]))
            for o in others:
                out[o].append((R * CITE_SHARE / len(others), v["id"]))
        else:
            out[pod].append((R, v["id"]))
    return out


def _stats(rs, own=None):
    """rs: credited R values in time order; own: the pod's own tickets (trade count, hit rate, P&L)."""
    own = own if own is not None else []
    wins, losses = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    n = len(own)
    return {"trades": n, "total_R": round(sum(rs), 3), "R_per_trade": round(sum(rs) / n, 3) if n else 0.0,
            "pf": round(wins / losses, 2) if losses else (None if not wins else 99.0),
            "hit": round(sum(1 for v in own if float(v["R"]) > 0) / n, 3) if n else None,
            "max_dd_R": round(dd, 3), "pnl": round(sum(float(v.get("pnl") or 0) for v in own), 2)}


def stats(pod, start, end, state=None, board=None):
    state = tickets.fold() if state is None else state
    rows = sorted(_closed(state, start, end), key=lambda v: v.get("updated", ""))
    rs = [r for r, _ in credited(rows, board).get(pod, [])]
    return _stats(rs, [v for v in rows if v.get("pod") == pod])


def shadow_r_per_trade(s=None):
    s = paths.read_json(systematic.SHADOW, {}) if s is None else s
    n = r = 0
    for ms in (s.get("edges") or {}).values():
        for v in ms.values():
            n += int(v.get("trades") or 0)
            r += float(v.get("total_r") or 0)
    return round(r / n, 3) if n else None


def scores(t=None, state=None):
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    start, end = (t - WINDOW).isoformat(), t.isoformat()
    board = memory.board(10 ** 9)
    pods = {p: stats(p, start, end, state, board) for p in paths.config().get("pods", {})}
    desk = _stats([float(v["R"]) for v in sorted(_closed(state, start, end), key=lambda v: v.get("updated", ""))],
                  _closed(state, start, end))
    return {"t": t.isoformat(timespec="seconds"), "window": [start[:10], end[:10]], "pods": pods, "desk": desk,
            "shadow_r_per_trade": shadow_r_per_trade(),
            "rejected": _rejected_summary(paths.read_json(REJECTED, {}))}


def _rejected_summary(rej):
    done = [v for v in rej.values() if v.get("R") is not None]
    return {"followed": len(done), "would_have_made_R": round(sum(v["R"] for v in done), 2),
            "pending": sum(1 for v in rej.values() if v.get("R") is None and not v.get("dropped"))}


def _report(sc):
    lines = [f"# Desk scores, {sc['window'][0]} to {sc['window'][1]}", "",
             f"Shadow benchmark: {sc['shadow_r_per_trade']} R a trade.", "",
             "| pod | trades | total R | R/trade | PF | hit | max DD R | P&L |", "|---|---|---|---|---|---|---|---|"]
    for p, s in list(sc["pods"].items()) + [("desk", sc["desk"])]:
        lines.append(f"| {p} | {s['trades']} | {s['total_R']} | {s['R_per_trade']} | {s['pf']} | {s['hit']} | "
                     f"{s['max_dd_R']} | {s['pnl']} |")
    r = sc["rejected"]
    lines += ["", f"Rejected tickets followed on paper: {r['followed']}, which would have made {r['would_have_made_R']} R "
                  f"({r['pending']} still open)."]
    return "\n".join(lines) + "\n"


# ---- rejected tickets on paper ---------------------------------------------------------------------------------------

def _follow(tk, df, t0, t):
    """Walk M15 bars after the rejection. Returns {R, how} or None while it is still undecided."""
    from desk import broker as bk
    side, stop = tk["side"], float(tk["stop"])
    e = tk.get("entry") or {"type": "market"}
    targets = tk.get("targets") or []
    t0_epoch = bk.utc_to_server_epoch(t0)
    bars = [r for r in df.itertuples() if int(r.time) >= t0_epoch]
    if not bars:
        return None
    entry, filled_at = (None, None)
    if e.get("type") == "market":
        entry, filled_at = float(bars[0].open), 0
    for i, r in enumerate(bars):
        if entry is None:
            px = float(e["price"])
            hit = (r.low <= px if (side == "buy") == (e["type"] == "limit") else r.high >= px)
            if not hit:
                if bk.server_epoch_to_utc(int(r.time)) - t0 > dt.timedelta(days=SHADOW_DAYS):
                    return {"R": 0.0, "how": "never filled"}
                continue
            entry, filled_at = px, i
        risk = abs(entry - stop)
        if risk <= 0:
            return {"R": 0.0, "how": "no risk"}
        sign = 1 if side == "buy" else -1
        if (r.low <= stop) if side == "buy" else (r.high >= stop):
            return {"R": -1.0, "how": "stop", "entry": entry}
        if targets:
            tp = float(targets[0][0])
            if (r.high >= tp) if side == "buy" else (r.low <= tp):
                return {"R": round(sign * (tp - entry) / risk, 3), "how": "target", "entry": entry}
        if bk.server_epoch_to_utc(int(r.time)) - bk.server_epoch_to_utc(int(bars[filled_at].time)) >= \
                dt.timedelta(days=SHADOW_DAYS):
            return {"R": round(sign * (float(r.close) - entry) / risk, 3), "how": f"marked after {SHADOW_DAYS}d",
                    "entry": entry}
    return None


def follow_rejected(b=None, t=None, state=None):
    """Score rejected tickets on paper. Returns how many were resolved this pass."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    rej = paths.read_json(REJECTED, {})
    todo = [v for v in tickets.by_status("rejected", state) if v["id"] not in rej
            or (rej[v["id"]].get("R") is None and not rej[v["id"]].get("dropped"))]
    if not todo:
        return 0
    own = b is None
    if own:
        from desk import broker
        b = broker.connect(paths.config())
    try:
        if not b.connected():
            return 0
        n = 0
        for tk in todo:
            t0 = dt.datetime.fromisoformat(tk["updated"])
            row = {"pod": tk.get("pod"), "instrument": tk.get("instrument"), "rejected": tk["updated"],
                   "why": tk.get("why")}
            sym = b.resolve(tk["instrument"])
            df = b.bars(sym, "M15", 1000) if sym else None
            res = _follow(tk, df, t0, t) if df is not None and len(df) else None
            if res is None and t - t0 > dt.timedelta(days=SHADOW_GIVE_UP):
                row["dropped"] = "too old to resolve"
            elif res is not None:
                row.update(res)
                n += 1
            rej[tk["id"]] = row
        paths.write_json(REJECTED, rej)
        return n
    finally:
        if own:
            b.shutdown()


# ---- daily and weekly ------------------------------------------------------------------------------------------------

def daily(t=None, b=None):
    t = t or clocks.now()
    state = tickets.fold()
    try:
        follow_rejected(b, t, state)
    except Exception as e:  # a broker hiccup must not cost the day's scores
        journal.log("scorekeeper_error", step="rejected", error=f"{type(e).__name__}: {e}")
    sc = scores(t, state)
    paths.write_json(SCORES, sc)
    paths.REPORTS.mkdir(parents=True, exist_ok=True)
    (paths.REPORTS / f"scores_{t.date().isoformat()}.md").write_text(_report(sc), encoding="utf-8")
    journal.log("scores", desk=sc["desk"], shadow=sc["shadow_r_per_trade"])
    from desk import live_gate  # live_gate imports this module
    live_gate.write(t)
    return sc


def _normalise(shares, fixed=()):
    """Clip to [FLOOR, CAP] and rescale to sum 1, a few rounds (clipping and scaling fight each other)."""
    live = {p: s for p, s in shares.items() if p not in fixed}
    for _ in range(20):
        tot = sum(live.values())
        if tot <= 0:
            break
        live = {p: min(CAP, max(FLOOR, s / tot)) for p, s in live.items()}
        if abs(sum(live.values()) - 1) < 1e-6:
            break
    return {p: round(live.get(p, 0.0), 4) for p in shares}


def allocate(sc, prev, cfg):
    pods = cfg.get("pods", {})
    base = {p: float(v.get("base_share", 0)) for p, v in pods.items()}
    tot = sum(base.values()) or 1
    base = {p: s / tot for p, s in base.items()}
    paused = set(prev.get("paused") or [])
    below = dict(prev.get("weeks_below_shadow") or {})
    shadow = sc.get("shadow_r_per_trade")
    for p in pods:
        s = sc["pods"].get(p) or {}
        if p == systematic.POD or s.get("trades", 0) < MIN_TRADES or shadow is None:
            continue
        below[p] = below.get(p, 0) + 1 if s["R_per_trade"] < shadow else 0
        if below[p] >= PAUSE_WEEKS and p not in paused:
            paused.add(p)
            journal.log("pod_paused", pod=p, weeks=below[p], r_per_trade=s["R_per_trade"], shadow=shadow)
            paths.INBOX.mkdir(parents=True, exist_ok=True)
            (paths.INBOX / f"pod_paused_{p}.md").write_text(
                f"# {p} paused\n\n{p} made {s['R_per_trade']} R a trade, below the shadow benchmark's {shadow}, "
                f"{below[p]} weeks running. Its playbook must be rewritten before it trades again; then remove it "
                f"from `paused` in logs/desk/state/alloc.json.\n", encoding="utf-8")
    last = prev.get("shares") or base
    target = {}
    for p in pods:
        s = sc["pods"].get(p) or {}
        b = base[p]
        want = b if s.get("trades", 0) < MIN_TRADES else b * max(0.25, 1 + s["R_per_trade"])
        was = last.get(p, b)
        target[p] = min(was + STEP, max(was - STEP, want))
    for p in paused:
        target[p] = 0.0
    return {"week": clocks.week_key(), "shares": _normalise(target, fixed=paused), "base": {p: round(s, 4) for p, s
            in base.items()}, "paused": sorted(paused), "weeks_below_shadow": below}


def bridge(state=None, t=None):
    """Send (edge, instrument) groups with 30+ closed trades and positive R to the research queue, once each."""
    t = t or clocks.now()
    state = tickets.fold() if state is None else state
    done = set(paths.read_json(BRIDGED, []))
    groups = defaultdict(list)
    for v in _closed(state):
        if v.get("edge"):
            groups[(v["edge"], v["instrument"])].append(v)
    sent = []
    for (edge, ins), rows in sorted(groups.items()):
        key = f"desk-{edge}-{ins}"
        rs = [float(v["R"]) for v in rows]
        if key in done or len(rs) < BRIDGE_TRADES or sum(rs) / len(rs) <= 0:
            continue
        s = _stats(rs, rows)
        pods = sorted({v.get("pod") for v in rows})
        paths.append_jsonl(QUEUE, {
            "id": key, "source": "desk", "title": f"Desk edge {edge} on {ins}", "link": "",
            "why": f"{s['trades']} desk trades at {s['R_per_trade']} R a trade, PF {s['pf']}, by {', '.join(pods)}",
            "evidence": {"trades": s["trades"], "R_per_trade": s["R_per_trade"], "pf": s["pf"], "hit": s["hit"],
                         "max_dd_R": s["max_dd_R"], "first": min(v.get("created", "") for v in rows)[:10],
                         "last": max(v.get("updated", "") for v in rows)[:10],
                         "theses": [v.get("thesis") for v in rows[-3:]]},
            "status": "new", "added": t.date().isoformat()})
        done.add(key)
        sent.append(key)
        journal.log("bridged", id=key, trades=s["trades"], r_per_trade=s["R_per_trade"])
    if sent:
        paths.write_json(BRIDGED, sorted(done))
    return sent


def weekly(t=None, b=None):
    t = t or clocks.now()
    sc = daily(t, b)
    cfg = paths.config()
    alloc = allocate(sc, paths.read_json(ALLOC, {}), cfg)
    paths.write_json(ALLOC, alloc)
    journal.log("allocation", shares=alloc["shares"], paused=alloc["paused"])
    state = tickets.fold()
    rolled = {p: v for p in cfg.get("pods", {}) if (v := playbooks.check(p, state, t))}
    return {"scores": sc, "alloc": alloc, "rolled_back": rolled, "bridged": bridge(state, t)}


def main():
    import json
    import sys
    out = weekly() if sys.argv[1:2] == ["weekly"] else daily()
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
