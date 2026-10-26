"""The desk sandbox: a quick backtest of an edge at real costs on the history before the holdout (DESIGN.md 3a).

It informs a pod; it is not the research gate. Fills: a signal on bar i enters at the open of bar i + 1 with half the
instrument's round-trip cost; each exit pays the other half. On a bar the stop is checked before any target (the
cautious order), a gap through the stop fills at the open, the trail moves on the close, a time stop exits at the
open of the first bar at or after it. One position per slot per edge and market, as live. Index, metal, energy and
crypto costs in config.json are today's points; back in history they scale with the price (a 1.8-point US100 spread
is 0.9 bp now and would be 9 bp at 2010's prices if left in points).

python -m desk.sandbox NAME [MARKET] [key=value ...] [from=YYYY-MM-DD] [to=YYYY-MM-DD]
"""
import datetime as dt
import json
import sys

import numpy as np

from desk import edges, journal, paths
from desk.edges import base

CARDS = paths.DESK / "edges" / "cards"


SCALED = ("index", "metal", "energy", "crypto")


def costs(df, cost, cls):
    """The round-trip cost on each bar: fixed for currencies, in proportion to the price for the rest."""
    if cls not in SCALED:
        return np.full(len(df), float(cost))
    c = df["close"].values.astype(float)
    return float(cost) * c / c[-1]


def simulate(df, signals, cost):
    """Trades of a signal list: [{t, out, side, slot, r, why}], r in units of the edge's risk (R x the weight).
    cost: the round trip in price units, one number or one per bar."""
    o, h, l, c, t = (df[k].values.astype(float) if k != "time" else df[k].values
                     for k in ("open", "high", "low", "close", "time"))
    cost = np.broadcast_to(np.asarray(cost, dtype=float), (len(df),))
    a = base.atr(df, 14).values
    entries, closes = {}, {}
    for s in signals:
        if s.get("close"):
            closes.setdefault(s["i"], set()).add(s.get("slot", 0))
        else:
            entries.setdefault(s["i"], {}).setdefault(s.get("slot", 0), s)
    trades, book = [], {}

    def close(pos, px, share, why, j):
        px -= pos["dir"] * cost[j] / 2
        pos["r"] += share * (px - pos["entry"]) * pos["dir"] / pos["risk"]
        pos["left"] -= share
        if pos["left"] <= 1e-9:
            trades.append({"t": int(pos["t"]), "out": int(t[j]), "side": pos["side"], "slot": pos["slot"],
                           "r": round(pos["r"] * pos["w"], 4), "why": why})
            return None
        return pos

    def manage(pos, j, at_open):
        """Stop, then targets, on bar j. at_open: the position existed before the bar opened (gaps count)."""
        d, st = pos["dir"], pos["stop"]
        if at_open and (o[j] - st) * d <= 0:
            return close(pos, o[j], pos["left"], "stop", j)
        if (l[j] if d > 0 else h[j]) * d <= st * d:
            return close(pos, st, pos["left"], "stop", j)
        while pos and pos["targets"]:
            px, share = pos["targets"][0]
            if (h[j] if d > 0 else l[j]) * d < px * d:
                break
            pos["targets"].pop(0)
            fill = o[j] if at_open and (o[j] - px) * d >= 0 else px
            pos = close(pos, fill, min(share, pos["left"]), "target", j)
        return pos

    for j in range(1, len(df)):
        for k in list(book):
            pos = book[k]
            if k in closes.get(j - 1, ()):
                pos = close(pos, o[j], pos["left"], "rule", j)
            elif pos["exit_t"] is not None and t[j] >= pos["exit_t"]:
                pos = close(pos, o[j], pos["left"], "time", j)
            else:
                pos = manage(pos, j, True)
            if pos is None:
                del book[k]
        for k, s in entries.get(j - 1, {}).items():
            if k in book:
                continue
            d = 1 if s["side"] == "buy" else -1
            entry = o[j] + d * cost[j] / 2
            risk = (entry - s["stop"]) * d
            if risk > 0 and not (s.get("exit_t") is not None and t[j] >= s["exit_t"]):
                pos = {"t": t[j], "side": s["side"], "dir": d, "entry": entry, "stop": s["stop"], "risk": risk,
                       "targets": [list(x) for x in sorted(s.get("targets") or [], key=lambda x: x[0] * d)],
                       "exit_t": s.get("exit_t"), "trail": s.get("trail_atr"), "left": 1.0, "r": 0.0, "slot": k,
                       "w": float(s.get("weight", 1.0))}
                pos = manage(pos, j, False)
                if pos:
                    book[k] = pos
        for pos in book.values():
            if pos["trail"] and np.isfinite(a[j]):
                want = c[j] - pos["dir"] * pos["trail"] * a[j]
                if (want - pos["stop"]) * pos["dir"] > 0:
                    pos["stop"] = want
    for pos in book.values():
        close(pos, c[-1], pos["left"], "end", len(df) - 1)
    trades.sort(key=lambda x: (x["out"], x["t"]))
    return trades


def stats(trades):
    r = np.array([x["r"] for x in trades], dtype=float)
    if not len(r):
        return {"trades": 0}
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.maximum(eq, 0)) - eq).max())
    win, loss = r[r > 0].sum(), -r[r < 0].sum()
    years = {}
    for x in trades:
        y = str(base.date_of(x["t"] // base.DAY).year)
        years.setdefault(y, {"trades": 0, "r": 0.0})
        years[y]["trades"] += 1
        years[y]["r"] = round(years[y]["r"] + x["r"], 2)
    return {"trades": len(r), "pf": round(float(win / loss), 2) if loss else None, "win": round(float((r > 0).mean()), 3),
            "avg_r": round(float(r.mean()), 3), "total_r": round(float(r.sum()), 2), "max_dd_r": round(dd, 2),
            "first": str(base.date_of(trades[0]["t"] // base.DAY)), "last": str(base.date_of(trades[-1]["t"] // base.DAY)),
            "by_year": years}


def _cut(df, start, end):
    if start:
        df = df[df["time"] >= base.day_of(dt.date.fromisoformat(start)) * base.DAY]
    if end:
        df = df[df["time"] < (base.day_of(dt.date.fromisoformat(end)) + 1) * base.DAY]
    return df.reset_index(drop=True)


def context(e, market, cfg=None):
    ctx = {"market": market}
    if "spx_d1" in e["needs"]:
        ctx["spx_d1"] = base.hist_bars("US500", "D1", cfg)
    return ctx


def run_edge(name, market=None, params=None, start=None, end=None, cfg=None, save=True):
    """Backtest one edge on one market (or all its markets); update its card. Returns {market: stats}."""
    cfg = cfg or paths.config()
    e = edges.get(name)
    out = {}
    for m in ([market] if market else e["markets"]):
        spec = cfg["instruments"].get(m, {})
        cost = spec.get("cost")
        if cost is None:
            out[m] = {"error": f"no cost for {m} in config.json"}
            continue
        try:
            df = _cut(base.hist_bars(m, e["tf"], cfg), start, end)
        except (FileNotFoundError, ValueError) as err:
            out[m] = {"error": str(err)}
            continue
        sigs = edges.run(name, df, params, context(e, m, cfg))
        out[m] = stats(simulate(df, sigs, costs(df, cost, spec.get("class"))))
    p = dict(e["defaults"])
    p.update(params or {})
    if save:
        card = paths.read_json(CARDS / f"{name}.json", {})
        card.update({k: v for k, v in base.describe(e).items()})
        bt = card.setdefault("backtest", {})
        for m, s in out.items():
            bt[m] = {"params": p, "from": start, "to": end, **s,
                     "run": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        card.setdefault("live", {})
        paths.write_json(CARDS / f"{name}.json", card)
    journal.log("sandbox", edge=name, params=p, start=start, end=end,
                results={m: {k: s.get(k) for k in ("trades", "pf", "total_r", "max_dd_r", "error") if k in s}
                         for m, s in out.items()})
    return out


def parse(argv):
    """NAME [MARKET] [key=value ...] [from=..] [to=..] -> (name, market, params, start, end)."""
    if not argv:
        raise ValueError("usage: NAME [MARKET] [key=value ...] [from=YYYY-MM-DD] [to=YYYY-MM-DD]")
    name, rest = argv[0], argv[1:]
    market = rest.pop(0) if rest and "=" not in rest[0] else None
    params, start, end = {}, None, None
    for kv in rest:
        k, v = kv.split("=", 1)
        if k == "from":
            start = v
        elif k == "to":
            end = v
        else:
            try:
                params[k] = json.loads(v)
            except json.JSONDecodeError:
                params[k] = v
    return name, market, params, start, end


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        name, market, params, start, end = parse(argv)
        print(json.dumps(run_edge(name, market, params, start, end), indent=1))
        return 0
    except (ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
