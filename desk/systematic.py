"""The armed legs: plain code that trades every pod's armed edges (DESIGN.md section 5, pod 1). No model.

Every clock tick, for each armed (edge, market): fetch the broker's last closed bars, run the edge, and act on a
signal decided on the last closed bar only, the same function the sandbox backtests. An entry becomes an armed ticket
(the risk gate still checks it); an exit by the edge's own rule asks the executor to close the slot's position.

The shadow benchmark runs here too: the five textbook edges on paper over the broker's live bars since the desk's
day 0, so the pods have a plain rule-based book to beat (DESIGN.md section 13). Nothing of it reaches the broker.

Armed legs live in logs/desk/state/systematic.json {"armed": [{edge, market, params, risk_pct, pod}], "seen": {..}};
without one the defaults below arm every leg on the market where its sandbox run was positive after costs. A leg
trades as the pod that armed it (the systematic pod when none is named), and only while that pod is active.
"""
import datetime as dt

from desk import broker, edges, journal, paths, phase, sandbox, tickets
from desk.edges import base

FILE = paths.STATE / "systematic.json"
SHADOW = paths.STATE / "shadow.json"
POD = "systematic"
RISK_PCT = 0.25  # each leg's base risk per trade; the gate caps it again (new-edge cap, phase scale)
ENTRY_TTL = dt.timedelta(minutes=10)  # a signal not placed within this is stale: the next bar's open has passed
SHADOW_EVERY = dt.timedelta(hours=6)
SHADOW_MAX_BARS = 5000

# sandbox runs before the holdout, after costs (2026-10-26): PF on the market each leg is armed on
DEFAULT_ARMED = [
    ("after", "EURUSD"),     # PF 1.76
    ("breakout", "USDJPY"),  # 1.10
    ("cross", "AUDJPY"),     # 1.86
    ("fall", "EURUSD"),      # 1.34
    ("fix", "EURUSD"),       # 1.36
    ("golddip", "XAUUSD"),   # 1.30
    ("grid", "AUDCAD"),      # 1.59
    ("hold", "XAUUSD"),      # 1.32
    ("morning", "EURJPY"),   # 1.88
    ("noise", "US100"),      # 1.15
]


def state():
    s = paths.read_json(FILE, {})
    if "armed" not in s:
        s["armed"] = [{"edge": e, "market": m, "params": {}, "risk_pct": RISK_PCT} for e, m in DEFAULT_ARMED]
    s.setdefault("seen", {})
    return s


def arm(edge, market, params=None, risk_pct=RISK_PCT, pod=POD):
    """Arm (or re-arm with new params) one leg on one market, traded as `pod`."""
    e = edges.get(edge)
    if e["kind"] == "benchmark":
        raise ValueError(f"{edge} is a benchmark edge: it trades on paper only")
    s = state()
    s["armed"] = [a for a in s["armed"] if (a["edge"], a["market"]) != (edge, market)]
    s["armed"].append({"edge": edge, "market": market, "params": params or {}, "risk_pct": float(risk_pct),
                       "pod": pod})
    paths.write_json(FILE, s)
    journal.log("systematic_arm", edge=edge, market=market, params=params or {}, risk_pct=risk_pct, pod=pod)
    return s["armed"]


def disarm(edge, market=None, pod=None):
    """Disarm a leg on one market or all; with `pod`, only the legs that pod armed."""
    s = state()
    s["armed"] = [a for a in s["armed"] if not (a["edge"] == edge and market in (None, a["market"])
                                                and pod in (None, a.get("pod", POD)))]
    paths.write_json(FILE, s)
    journal.log("systematic_disarm", edge=edge, market=market, pod=pod)
    return s["armed"]


def context(b, e, market):
    ctx = {"market": market}
    for k in e["needs"]:
        sym = b.resolve(base.need(k)[0])
        ctx[k] = b.bars(sym, base.need(k)[1], max(300, e["bars"])) if sym else None
    return ctx


def _mine(live, a, slot):
    return [v for v in live.values() if v.get("pod") == a.get("pod", POD) and v.get("edge") == a["edge"]
            and v.get("instrument") == a["market"] and int(v.get("slot") or 0) == slot]


def _close(live, a, s, t):
    acted = []
    for v in _mine(live, a, s["slot"]):
        if v["status"] in ("placed", "open"):
            tickets.update(v["id"], close_request=s["why"])
        else:
            tickets.cancel(v["id"], f"edge exit before entry: {s['why']}", by=a.get("pod", POD))
        acted.append(v["id"])
    if acted:
        journal.log("systematic_exit", edge=a["edge"], market=a["market"], slot=s["slot"], tickets=acted, why=s["why"])
    return acted


def _enter(live, a, e, s, t):
    if _mine(live, a, s["slot"]):
        return None  # one position per slot, as in the sandbox
    tk = {"pod": a.get("pod", POD), "instrument": a["market"], "side": s["side"], "stop": s["stop"], "targets": s["targets"],
          "risk_pct": round(float(a.get("risk_pct", RISK_PCT)) * s.get("weight", 1.0), 4),
          "thesis": f"{a['edge']}: {s['why']}", "invalidation": f"stop {s['stop']:.5g}", "edge": a["edge"],
          "slot": s["slot"], "arm": True, "expires": (t + ENTRY_TTL).isoformat(timespec="seconds"),
          "evidence": f"sandbox card desk/edges/cards/{a['edge']}.json", "confidence": 3}
    if s.get("exit_t") is not None:
        tk["time_stop"] = broker.server_epoch_to_utc(s["exit_t"]).isoformat(timespec="seconds")
    if s.get("trail_atr"):
        tk["trail"] = {"atr": s["trail_atr"], "tf": e["tf"], "n": 14}
    tid, errs = tickets.new(**tk)
    journal.log("systematic_entry", edge=a["edge"], market=a["market"], slot=s["slot"], side=s["side"], ticket=tid,
                errors=errs or None, why=s["why"])
    return tid


def run(b, cfg, t):
    """One pass over the armed legs. Returns {"edge market": [actions]} for the legs that acted."""
    active = phase.pods_active(cfg, phase.current())
    if not active:
        return {}
    st = state()
    live = tickets.live()
    out = {}
    for a in st["armed"]:
        key = f"{a['edge']} {a['market']}"
        if a.get("pod", POD) not in active:
            continue
        try:
            e = edges.get(a["edge"])
            sym = b.resolve(a["market"])
            df = b.bars(sym, e["tf"], e["bars"]) if sym else None
            if df is None or len(df) < 3:
                continue
            last = int(df["time"].iloc[-1])
            if last <= st["seen"].get(key, 0):
                continue  # this bar was already read
            st["seen"][key] = last
            n = len(df) - 1
            sigs = [s for s in edges.run(a["edge"], df, a.get("params"), context(b, e, a["market"])) if s["i"] == n]
            acts = []
            for s in sigs:
                if s.get("close"):
                    acts += _close(live, a, s, t)
            if acts:
                live = tickets.live()
            for s in sigs:
                if not s.get("close"):
                    tid = _enter(live, a, e, s, t)
                    if tid:
                        acts.append(tid)
                        live = tickets.live()
            if acts:
                out[key] = acts
        except Exception as err:  # noqa: BLE001  one leg's failure must not stop the others
            journal.log("tick_error", where="systematic", leg=key, why=f"{type(err).__name__}: {err}")
    paths.write_json(FILE, st)
    try:
        if POD in active:
            shadow(b, cfg, t)
    except Exception as err:  # noqa: BLE001
        journal.log("tick_error", where="shadow", why=f"{type(err).__name__}: {err}")
    return out


# ---- the shadow benchmark -------------------------------------------------------------------------------------------

def _bars_since(e, day0, t):
    per_day = 1440 // broker.TF_MIN[e["tf"]]
    days = max(1, (t - day0).days + 1) * 7 // 5 + 3
    return min(SHADOW_MAX_BARS, e["bars"] + days * per_day)


def shadow(b, cfg, t, force=False):
    """The benchmark edges on paper since day 0: {edge: {market: {trades, total_r, ...}}, "t": ...}. At most every
    6 hours; trades are rebuilt from the live bars each time, so a restart loses nothing."""
    cur = paths.read_json(SHADOW, {})
    if not force and cur.get("t") and t - dt.datetime.fromisoformat(cur["t"]) < SHADOW_EVERY:
        return cur
    p = paths.read_json(phase.FILE, {})
    if not p.get("day0"):
        return cur
    day0 = dt.datetime.fromisoformat(p["day0"])
    since = broker.utc_to_server_epoch(day0)
    res = {"t": t.isoformat(timespec="seconds"), "since": p["day0"], "edges": {}}
    for name, e in base.EDGES.items():
        if e["kind"] != "benchmark":
            continue
        for m in cfg.get("benchmark_markets", e["markets"]):
            if m not in e["markets"]:
                continue
            sym = b.resolve(m)
            df = b.bars(sym, e["tf"], _bars_since(e, day0, t)) if sym else None
            if df is None or len(df) < 3:
                continue
            ins = cfg["instruments"].get(m, {})
            sigs = [s for s in edges.run(name, df, None, {"market": m}) if int(df["time"].iloc[s["i"]]) >= since]
            trades = sandbox.simulate(df, sigs, sandbox.costs(df, ins.get("cost", 0), ins.get("class")))
            st = sandbox.stats(trades)
            res["edges"].setdefault(name, {})[m] = {k: st.get(k) for k in ("trades", "pf", "win", "total_r",
                                                                           "max_dd_r")}
    res["total_r"] = round(sum(v.get("total_r") or 0 for mk in res["edges"].values() for v in mk.values()), 2)
    paths.write_json(SHADOW, res)
    journal.log("shadow", total_r=res["total_r"], legs=sum(len(v) for v in res["edges"].values()))
    return res
