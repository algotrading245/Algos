"""The live watcher (owner 2026-11-01): each tick, it reads every pod's market model against the live market and wakes
the pod when something in its own view happens. Nothing here trades; the pod decides what to do once awake.

  level   the mid crossed a price level the pod wrote in its model (once per level per trading day)
  edge    an edge the pod listed for that market fires on the newest closed bar (once per bar)
  shock   the newest closed bar's range is over shock_atr x ATR(14) of the bars before it (once per bar)

What fired goes into the wake job (`watch`), so the brief says why the pod was woken; the wake cap and the token slice
still apply (jobs.wake). State, so a thing fires once: STATE/watcher.json.
"""
from desk import clocks, jobs, journal, market_model, paths, phase

FILE = paths.STATE / "watcher.json"
DEFAULTS = {"shock_atr": 2.5, "shock_tf": "H1", "atr_n": 14}


def _mid(b, sym):
    q = b.tick(sym)
    if not q or not q.get("bid") or not q.get("ask"):
        return None
    return (float(q["bid"]) + float(q["ask"])) / 2


def _shock(b, sym, c, cache):
    """(bar time, range / ATR) of the newest closed bar, or None."""
    from desk.edges import base
    key = (sym, c["shock_tf"], 60)
    df = cache.get(key)
    if df is None:
        df = cache[key] = b.bars(sym, c["shock_tf"], 60)
    if df is None or len(df) < c["atr_n"] + 2:
        return None
    a = base.atr(df.iloc[:-1], c["atr_n"]).iloc[-1]
    rng = float(df["high"].iloc[-1] - df["low"].iloc[-1])
    if not a or a != a:  # 0 or NaN
        return None
    return base.to_utc(df["time"].iloc[-1]).isoformat(timespec="minutes"), rng / float(a)


def run(b, cfg, t=None):
    """One pass. Returns {pod: [watch rows]} for the pods it tried to wake."""
    from desk import extras
    t = t or clocks.now()
    c = DEFAULTS | cfg.get("watcher", {})
    st = paths.read_json(FILE, {})
    mids, fired_lv, bars = st.get("mid", {}), st.get("levels", {}), st.get("bars", {})
    day = clocks.trading_day(t).isoformat()
    fired_lv = {k: v for k, v in fired_lv.items() if v == day}
    cache, now_mid, out = {}, {}, {}

    for pod in phase.pods_active(cfg):
        rows = []
        for market, entry in market_model.get(pod).get("markets", {}).items():
            sym = b.resolve(market)
            if not sym:
                continue
            if market not in now_mid:
                now_mid[market] = _mid(b, sym)
            mid, prev = now_mid[market], mids.get(market)
            if mid is not None and prev is not None:
                lo, hi = sorted((prev, mid))
                for lv in entry.get("levels") or []:
                    k = f"{pod}|{market}|{lv}"
                    if lo < lv <= hi and k not in fired_lv:
                        fired_lv[k] = day
                        rows.append({"kind": "level", "market": market, "level": lv, "from": round(prev, 5),
                                     "price": round(mid, 5), "dir": "up" if mid > prev else "down"})
            for name in entry.get("edges") or []:
                try:
                    s = extras.signal(b, name, market, lookback=0, armed=[], cache=cache)
                except Exception as e:
                    journal.log("watch_error", pod=pod, market=market, edge=name, why=f"{type(e).__name__}: {e}")
                    continue
                k = f"{pod}|{market}|edge|{name}"
                if s["now"] and bars.get(k) != s["last_bar"]:
                    bars[k] = s["last_bar"]
                    rows.append({"kind": "edge", "market": market, "edge": name, "bar": s["last_bar"],
                                 "price": s["price"], "signals": s["now"]})
            try:
                sh = _shock(b, sym, c, cache)
            except Exception as e:
                journal.log("watch_error", pod=pod, market=market, why=f"shock: {type(e).__name__}: {e}")
                sh = None
            k = f"{pod}|{market}|shock"
            if sh and sh[1] >= c["shock_atr"] and bars.get(k) != sh[0]:
                bars[k] = sh[0]
                rows.append({"kind": "shock", "market": market, "bar": sh[0], "range_atr": round(sh[1], 2)})
        if rows:
            journal.log("watch_fired", pod=pod, watch=rows)
            out[pod] = rows
            if not jobs.has_pending("wake", pod=pod):
                jobs.wake(pod, [], cfg, t, watch=rows)

    mids.update({m: round(v, 6) for m, v in now_mid.items() if v is not None})
    paths.write_json(FILE, {"t": t.isoformat(timespec="seconds"), "mid": mids, "levels": fired_lv, "bars": bars})
    return out
