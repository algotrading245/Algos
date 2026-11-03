"""Where price is likely to go over a leg's holding period, and where its stop sits in that noise (owner 2026-10-31).

    python tools/range_sim.py EDGE MARKET [paths=10000] [block=5] [horizon=N] [to=YYYY-MM-DD] [seed=1] [key=value ...]

Not a forecast: a map of the noise. It answers "if I enter now, how far does price usually wander before the exit,
and how often does noise alone reach my stop?"
1. Paths: block bootstrap of the market's own bars (close-to-close, open, high and low as log moves from the previous
   close), so fat tails, gaps and short-run clustering stay in. Blocks are drawn only from bars in the same volatility
   regime as the last bar (terciles of the 20-bar realised volatility).
2. Bands: the 50% and 90% range of the price at the exit horizon (and at shorter steps), in ATR and in price.
3. Noise excursion: the adverse and favourable excursion of the random paths; the share of paths a fixed stop of the
   leg's size is hit by; P(target before stop) at 1R, 2R and 3R against the random-walk baseline 1/(1+R); and, when
   the leg trails, the exit R of the trailing stop.
4. The leg's own trades (desk.sandbox at real cost): MAE and MFE of winners and losers in ATR at entry, and how many
   winners came close to the stop.
The leg's stop, trail and horizon are read from its own signals (stop distance / ATR, trail_atr, exit_t), unless
given. Data stops before the holdout (base.hist_bars cuts 2025-10-13 off; `to` cannot pass it).
Writes desk/reports/range_<edge>_<market>.md.
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desk import edges, paths, sandbox  # noqa: E402
from desk.edges import base  # noqa: E402

REPORTS = ROOT / "desk" / "reports"
VOL_N = 20


def parse(argv):
    opts, params = {"paths": 10000, "block": 5, "seed": 1}, {}
    for a in argv:
        k, v = a.split("=", 1)
        if k in ("paths", "block", "horizon", "seed"):
            opts[k] = int(v)
        elif k in ("to", "stop", "trail"):
            opts[k] = v
        else:
            params[k] = float(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v
    return opts, params


def bar_moves(df):
    """Per bar, log moves from the previous close: open, high, low, close."""
    o, h, l, c = (np.log(df[k].values.astype(float)) for k in ("open", "high", "low", "close"))
    pc = c[:-1]
    return np.stack([o[1:] - pc, h[1:] - pc, l[1:] - pc, c[1:] - pc], axis=1)


def regimes(r):
    """Tercile (0 low, 1 mid, 2 high) of the trailing 20-bar volatility of close moves, per bar."""
    vol = np.full(len(r), np.nan)
    for i in range(VOL_N, len(r) + 1):
        vol[i - 1] = r[i - VOL_N:i].std()
    ok = np.isfinite(vol)
    q = np.nanquantile(vol, [1 / 3, 2 / 3])
    reg = np.where(~ok, -1, np.digitize(vol, q))
    return reg, vol, q


def bootstrap(moves, starts, horizon, block, n, rng):
    """n paths of `horizon` bars, each a chain of contiguous blocks that start at a bar in `starts`."""
    k = -(-horizon // block)
    s = rng.choice(starts, size=(n, k))
    idx = (s[:, :, None] + np.arange(block)[None, None, :]).reshape(n, -1)[:, :horizon]
    return moves[idx]  # (n, horizon, 4)


def first_passage(hi, lo, up, dn):
    """Share of paths reaching +up before -dn (a bar touching both counts as the stop, as in the sandbox)."""
    hit_up = hi >= up
    hit_dn = lo <= -dn
    big = hi.shape[1] + 1
    t_up = np.where(hit_up.any(1), hit_up.argmax(1), big)
    t_dn = np.where(hit_dn.any(1), hit_dn.argmax(1), big)
    return float((t_up < t_dn).mean()), float(((t_up == big) & (t_dn == big)).mean())


def trail_exit(P, stop, trail):
    """Exit R of a long with a fixed stop that trails `trail` below the highest close (moved on the close, used from
    the next bar); a gap through it fills at the open. Out at the horizon's close otherwise. P in ATR units."""
    o, h, l, c = (P[:, :, i] for i in range(4))
    n, H = c.shape
    cl = np.cumsum(c, axis=1)
    prev = np.concatenate([np.zeros((n, 1)), cl[:, :-1]], axis=1)
    level = np.maximum(-stop, np.maximum.accumulate(prev, axis=1) - trail)
    hit = (prev + l) <= level
    j = np.where(hit.any(1), hit.argmax(1), H)
    rows = np.arange(n)
    jj = np.minimum(j, H - 1)
    fill = np.minimum(level[rows, jj], prev[rows, jj] + o[rows, jj])
    exit_x = np.where(j < H, fill, cl[:, -1])
    return exit_x / stop, j < H


def leg_shape(name, df, params, ctx):
    """The leg's own stop (in ATR at the signal), trail and holding period (bars), from its signals."""
    sigs = edges.run(name, df, params, ctx)
    a = base.atr(df, 14).values
    c = df["close"].values
    tf = base.tf_secs(df)
    t = df["time"].values
    stops = [abs(c[s["i"]] - s["stop"]) / a[s["i"]] for s in sigs if np.isfinite(a[s["i"]]) and a[s["i"]] > 0]
    hold = [(s["exit_t"] - t[s["i"]]) / tf - 1 for s in sigs if s["exit_t"]]
    trail = [s["trail_atr"] for s in sigs if s["trail_atr"]]
    return sigs, (float(np.median(stops)) if stops else None), (float(np.median(trail)) if trail else None), \
        (int(round(np.median(hold))) if hold else None)


def excursions(df, trades):
    """MAE / MFE of each trade in ATR at entry (the ATR of the bar before the entry bar)."""
    t = df["time"].values
    o, h, l = (df[k].values.astype(float) for k in ("open", "high", "low"))
    a = base.atr(df, 14).values
    rows = []
    for x in trades:
        j, k = np.searchsorted(t, x["t"]), np.searchsorted(t, x["out"])
        if j < 1 or k >= len(t) or not np.isfinite(a[j - 1]):
            continue
        e, hi, lo = o[j], h[j:k + 1].max(), l[j:k + 1].min()
        mae, mfe = ((e - lo), (hi - e)) if x["side"] == "buy" else ((hi - e), (e - lo))
        rows.append((mae / a[j - 1], mfe / a[j - 1], x["r"], k - j + 1))
    return np.array(rows) if rows else np.zeros((0, 4))


def q(x, ps=(50, 75, 90)):
    return " / ".join(f"{np.percentile(x, p):.2f}" for p in ps) if len(x) else "-"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0].startswith("-"):
        sys.exit(__doc__)
    name, market = argv[0], argv[1]
    opts, params = parse(argv[2:])
    cfg = paths.config()
    e = edges.get(name)
    spec = cfg["instruments"].get(market, {})
    df = base.hist_bars(market, e["tf"], cfg)
    if "to" in opts:
        if dt.date.fromisoformat(opts["to"]) >= base.HOLDOUT:
            sys.exit(f"to={opts['to']} is in the holdout (from {base.HOLDOUT})")
        df = sandbox._cut(df, None, opts["to"])
    ctx = sandbox.context(e, market, cfg)
    sigs, stop, trail, hold = leg_shape(name, df, params, ctx)
    stop = float(opts.get("stop", stop or 2.0))
    trail = float(opts["trail"]) if "trail" in opts else trail
    H = int(opts.get("horizon", hold or 20))
    rng = np.random.default_rng(opts["seed"])

    moves = bar_moves(df)
    reg, vol, cuts = regimes(moves[:, 3])
    now = int(reg[-1])
    starts_all = np.arange(VOL_N, len(moves) - opts["block"])
    starts = starts_all[reg[starts_all - 1] == now]
    a_now = float(base.atr(df, 14).values[-1])
    c_now = float(df["close"].values[-1])
    unit = np.log1p(a_now / c_now)  # one ATR as a log move from the last close
    last = base.date_of(int(df["time"].values[-1]) // base.DAY)
    tf = base.tf_secs(df)

    # "flat": the regime's bars with their mean close move taken out of every price, the no-edge baseline at the
    # same horizon and tails (1/(1+R) only holds with no time limit)
    flat = moves - moves[starts, 3].mean()
    res = {}
    for tag, mv, st in (("regime", moves, starts), ("all", moves, starts_all), ("flat", flat, starts)):
        P = bootstrap(mv, st, H, opts["block"], opts["paths"], rng) / unit
        cl = np.cumsum(P[:, :, 3], axis=1)
        prev = np.concatenate([np.zeros((len(P), 1)), cl[:, :-1]], axis=1)
        hi, lo = prev + P[:, :, 1], prev + P[:, :, 2]
        res[tag] = {"P": P, "cl": cl, "hi": hi, "lo": lo}

    R = res["regime"]
    steps = sorted({s for s in (1, 5, 20, H) if s <= H})
    band = [(s, np.percentile(R["cl"][:, s - 1], [5, 25, 50, 75, 95])) for s in steps]
    mae_l, mfe_l = -R["lo"].min(1), R["hi"].max(1)
    mae_s, mfe_s = R["hi"].max(1), -R["lo"].min(1)
    ftp = {m: {tag: first_passage(res[tag]["hi"], res[tag]["lo"], m * stop, stop) for tag in res} for m in (1, 2, 3)}
    ftp_s = {m: first_passage(-R["lo"], -R["hi"], m * stop, stop) for m in (1, 2, 3)}
    tr = trail_exit(R["P"], stop, trail) if trail else None
    tr0 = trail_exit(res["flat"]["P"], stop, trail) if trail else None

    trades = sandbox.simulate(df, sigs, sandbox.costs(df, spec["cost"], spec.get("class"))) if spec.get("cost") else []
    ex = excursions(df, trades)
    win, lose = ex[ex[:, 2] > 0] if len(ex) else ex, ex[ex[:, 2] <= 0] if len(ex) else ex
    why = {}
    for x in trades:
        why[x["why"]] = why.get(x["why"], 0) + 1

    price = lambda x: c_now * np.exp(x * unit)  # noqa: E731
    L = [f"# Range of {name} on {market} ({e['tf']}), data to {last}", "",
         f"Last close {c_now:.2f}, ATR(14) {a_now:.2f} ({a_now / c_now:.2%}). Volatility regime now: "
         f"{['low', 'mid', 'high'][now]} (20-bar vol {vol[-1]:.3%}; tercile cuts {cuts[0]:.3%} / {cuts[1]:.3%}). "
         f"{opts['paths']} paths of {H} bars ({H * tf / 86400:.0f} days), {opts['block']}-bar blocks from the "
         f"{len(starts)} {['low', 'mid', 'high'][now]}-regime bars of {len(starts_all)}.", "",
         f"Leg: stop {stop:.2f} ATR (= {stop * a_now:.2f} away at today's ATR), "
         + (f"trail {trail:.2f} ATR, " if trail else "no trail, ") + f"out after {H} bars. Costs not in the paths.", "",
         "## Bands (price from the last close; ATR in brackets)", "",
         "| after | 90% low | 50% low | median | 50% high | 90% high |", "|---|---|---|---|---|---|"]
    for s, p in band:
        L.append(f"| {s} bars | " + " | ".join(f"{price(x):.2f} ({x:+.1f})" for x in p) + " |")
    L += ["", "## Noise excursion over the holding period (ATR; median / 75% / 90% of paths)", "",
          f"- Long: adverse {q(mae_l)}, favourable {q(mfe_l)}",
          f"- Short: adverse {q(mae_s)}, favourable {q(mfe_s)}",
          f"- A {stop:.2f} ATR stop is hit by noise alone in {np.mean(mae_l >= stop):.0%} of long paths and "
          f"{np.mean(mae_s >= stop):.0%} of short paths; it sits at the {np.mean(mae_l < stop):.0%} point of the long "
          f"adverse excursion.", "",
          "## Target before stop (fixed stop, no trail)", "",
          "| target | long, this regime | long, all regimes | short, this regime | no drift (baseline) | "
          "neither by the horizon |", "|---|---|---|---|---|---|"]
    for m in (1, 2, 3):
        L.append(f"| {m}R ({m * stop:.1f} ATR) | {ftp[m]['regime'][0]:.0%} | {ftp[m]['all'][0]:.0%} | "
                 f"{ftp_s[m][0]:.0%} | {ftp[m]['flat'][0]:.0%} | {ftp[m]['regime'][1]:.0%} |")
    L += ["", "The baseline is the same bootstrap with the drift taken out (same tails, same horizon); the gap to it is "
          "the market's drift, not the leg's skill. 1/(1+R) is the baseline only with no time limit."]
    if tr is not None:
        xr, out = tr
        L += ["", f"Trailing stop ({trail:.2f} ATR below the highest close), random long entries in this regime: "
              f"exit R median {np.median(xr):+.2f}, mean {xr.mean():+.2f}, P(>0) {np.mean(xr > 0):.0%}; "
              f"{np.mean(out):.0%} stopped or trailed out before the horizon. With no drift: mean "
              f"{tr0[0].mean():+.2f}, P(>0) {np.mean(tr0[0] > 0):.0%}."]
    L += ["", f"## The leg's own trades ({len(trades)} at real cost, {len(ex)} with excursions)", ""]
    if len(ex):
        L += [f"- Exits: " + ", ".join(f"{k} {v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1])),
              f"- Winners {len(win)}: MAE {q(win[:, 0])}, MFE {q(win[:, 1])}, bars held median {np.median(win[:, 3]):.0f}"
              if len(win) else "- Winners: none",
              f"- Losers {len(lose)}: MAE {q(lose[:, 0])}, MFE {q(lose[:, 1])}" if len(lose) else "- Losers: none",
              f"- Winners whose MAE came within half the stop ({stop / 2:.1f} ATR): {np.mean(win[:, 0] >= stop / 2):.0%}; "
              f"within 80% ({0.8 * stop:.1f} ATR): {np.mean(win[:, 0] >= 0.8 * stop):.0%}" if len(win) else "",
              f"- Losers that were {stop:.1f} ATR (1R) in profit first: {np.mean(lose[:, 1] >= stop):.0%}"
              if len(lose) else ""]
    L += ["", "Read it: a stop inside the 50-75% adverse band is mostly hit by noise; one beyond the 90% point mostly "
          "by a real move. A leg whose P(target before stop) is no better than the no-drift baseline has no edge at "
          "that target; this tool does not change the leg."]
    text = "\n".join(x for x in L if x is not None) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"range_{name}_{market}.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
