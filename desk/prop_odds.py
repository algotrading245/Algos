"""The truth check (owner 2026-10-27): the odds that today's book passes a FundingPips 10k two-step challenge and then
pays, by edge and size.  Read-only on the research side; writes desk/reports/prop_odds.md.

The book is tools/book_sim.py's: the 10 legs at walk-forward equal risk with its risk layer (vol target 20%, cuts in a
drawdown), weekdays before the owner's holdout only.  Here it is scaled to an annual volatility `vol` and its mean cut
to `edge` of the backtest (a backtest Sharpe near 2.8 from legs picked out of many is not what live trading pays).

A round: phase 1 to +8%, phase 2 to +5% (each at least 3 trading days, then a fresh account), then FUNDED_DAYS on the
funded account, paid each month at SPLIT of the profit above the start.  Breach: a day's loss reaching the daily limit
or equity at the static maximum loss, both on the initial balance.  Day returns are close to close, so a day's loss
counts INTRADAY times bigger against the daily limit.  Two rule sets: the firm's (5% day, 10% total) and the desk's own
stricter prop_10k profile (3% day, 8% total).  Paths are 21-day block bootstraps of the book (vol clusters kept);
every 5th historical start day is a second opinion.

    python desk/prop_odds.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import book_sim  # noqa: E402

TARGETS, MIN_DAYS, GAP, FUNDED_DAYS, SPLIT, INTRADAY = (8.0, 5.0), 3, 2, 126, 0.80, 1.3
RULES = {"firm 5/10": (5.0, 10.0), "desk 3/8": (3.0, 8.0)}
EDGES = (1.0, 0.7, 0.5, 0.3)
VOLS = (4, 6, 8, 10, 12, 15)
CHALLENGE_MAX, N, BLOCK = 252, 4000, 21
REPORT = ROOT / "desk" / "reports" / "prop_odds.md"


def book():
    L = book_sim.legs()
    b, _ = book_sim.combine(L)
    return book_sim.risk_layer(b), list(L.columns)


def bootstrap(r, n, days, rng):
    k = -(-days // BLOCK)
    starts = rng.integers(0, len(r) - BLOCK, size=(n, k))
    return r[starts[:, :, None] + np.arange(BLOCK)].reshape(n, -1)[:, :days]


def run(paths, day_lim, max_lim):
    """paths: rounds x days of daily % returns at the chosen size.  Returns per round: days to pass (nan if not),
    breached in the challenge, breached when funded, payout in % of the account over FUNDED_DAYS."""
    n, days = paths.shape
    idx = np.arange(n)
    stage = np.zeros(n, int)          # 0, 1 the phases; 2 funded; 3 done
    eq, held, wait = np.zeros(n), np.zeros(n, int), np.zeros(n, int)
    passed_at = np.full(n, np.nan)
    c_breach, f_breach = np.zeros(n, bool), np.zeros(n, bool)
    payout = np.zeros(n)
    target = np.array(TARGETS + (np.inf, np.inf))
    for d in range(days):
        go = (stage < 3) & (wait == 0)
        wait[~go & (wait > 0)] -= 1
        if not go.any():
            if (stage == 3).all():
                break
            continue
        r = paths[idx, d] * np.where((stage < 2) & (eq >= target[np.minimum(stage, 3)]), 0.1, 1.0)
        r = np.where(go, r, 0.0)
        eq += r
        held += go
        bad = go & ((-r * INTRADAY >= day_lim) | (eq <= -max_lim))
        c_breach |= bad & (stage < 2)
        f_breach |= bad & (stage == 2)
        stage[bad] = 3
        live = go & ~bad
        # a phase passed: a fresh account after GAP days
        up = live & (stage < 2) & (eq >= target[np.minimum(stage, 3)]) & (held >= MIN_DAYS)
        stage[up] += 1
        eq[up], held[up], wait[up] = 0.0, 0, GAP
        passed_at[up & (stage == 2)] = d + 1 + GAP
        stage[live & (stage < 2) & (d + 1 >= CHALLENGE_MAX)] = 3
        # funded: paid each month on a profit, the account goes back to its start
        f = live & (stage == 2) & ~up
        pay = f & (held % 21 == 0) & (eq > 0)
        payout[pay] += SPLIT * eq[pay]
        eq[pay] = 0.0
        stage[f & (held >= FUNDED_DAYS)] = 3
    return passed_at, c_breach, f_breach, payout


def summary(res):
    t, cb, fb, pay = res
    p = ~np.isnan(t)
    return {"pass_3m": np.mean(p & (t <= 63)), "pass_6m": np.mean(p & (t <= 126)), "pass_12m": np.mean(p),
            "median_days": float(np.nanmedian(t)) if p.any() else None, "breach_challenge": cb.mean(),
            "breach_funded": fb[p].mean() if p.any() else None, "payout_6m": pay[p].mean() if p.any() else None}


def curve(x100, sd, raw):
    """The bar for the edge factory: pass odds under the firm's rules by the Sharpe the book keeps live, each at its best
    size with challenge breach under 5%, and the legs that Sharpe takes at today's average leg."""
    full = x100.mean() / x100.std() * np.sqrt(252)
    dl, ml = RULES["firm 5/10"]
    out = ["## The bar: pass odds by live Sharpe (firm 5/10, best size with breach under 5%)", "",
           f"Legs needed: equal risk, pairs near uncorrelated, so Sharpe grows with the square root of the leg count; "
           f"today's {full:.2f} from 10 legs at 50% edge is {full * 0.5:.2f}.", "",
           "| live Sharpe | vol | pass 6m | pass 12m | median days | breach | payout 6m % | legs at 50% edge |",
           "|---|---|---|---|---|---|---|---|"]
    for target in (1.0, 1.4, 1.8, 2.2, 2.6, 3.0):
        edge = target / full
        best = None
        for v in VOLS:
            s = summary(run((raw - x100.mean() * (1 - edge)) * v / sd, dl, ml))
            if s["breach_challenge"] < 0.05 and (best is None or s["pass_6m"] > best[1]["pass_6m"]):
                best = (v, s)
        legs = 10 * (target / (full * 0.5)) ** 2
        if best is None:
            out.append(f"| {target:.1f} | none | - | - | - | - | - | {legs:.0f} |")
            continue
        v, s = best
        out.append(f"| {target:.1f} | {v}% | {s['pass_6m']:.0%} | {s['pass_12m']:.0%} | {s['median_days'] or '-'} | "
                   f"{s['breach_challenge']:.1%} | {(s['payout_6m'] or 0):.1f}% | {legs:.0f} |")
    return out + [""]


def main():
    x, legs = book()
    x100 = x.to_numpy() * 100
    sd = x100.std() * np.sqrt(252)
    rng = np.random.default_rng(7)
    raw = bootstrap(x100, N, CHALLENGE_MAX + GAP * 2 + FUNDED_DAYS, rng)
    hist_starts = range(0, len(x100) - (CHALLENGE_MAX + 4 + FUNDED_DAYS), 5)
    hist = np.array([x100[s:s + CHALLENGE_MAX + 4 + FUNDED_DAYS] for s in hist_starts])
    lines = ["# Truth check: FundingPips 10k two-step, today's book", "",
             f"Book: {', '.join(legs)}; {x.index[0].date()} to {x.index[-1].date()} ({len(x)} weekdays, before the "
             f"holdout); backtest Sharpe {book_sim.sharpe(x):.2f}.",
             f"Phase 1 +{TARGETS[0]:.0f}%, phase 2 +{TARGETS[1]:.0f}%, min {MIN_DAYS} days each; funded {FUNDED_DAYS} "
             f"days, paid monthly at {SPLIT:.0%}.  Day loss x{INTRADAY} for intraday.  {N} bootstrap rounds.", ""]
    best = {}
    for rule, (dl, ml) in RULES.items():
        for edge in EDGES:
            lines += [f"## Rules {rule}, edge {edge:.0%} (Sharpe ~{book_sim.sharpe(x) * edge:.1f})", "",
                      "| vol | pass 3m | pass 6m | pass 12m | median days | breach challenge | breach funded 6m "
                      "| payout 6m % (10k $) | history pass 12m / breach |", "|---|---|---|---|---|---|---|---|---|"]
            for v in VOLS:
                f = v / sd
                adj = lambda a: (a - x100.mean() * (1 - edge)) * f  # noqa: E731
                s = summary(run(adj(raw), dl, ml))
                h = summary(run(adj(hist), dl, ml))
                pay = s["payout_6m"] or 0.0
                lines.append(f"| {v}% | {s['pass_3m']:.0%} | {s['pass_6m']:.0%} | {s['pass_12m']:.0%} | "
                             f"{s['median_days'] or '-'} | {s['breach_challenge']:.1%} | "
                             f"{(s['breach_funded'] or 0):.1%} | {pay:.1f}% (${pay * 100:,.0f}) | "
                             f"{h['pass_12m']:.0%} / {h['breach_challenge']:.1%} |")
                score = s["pass_6m"] if s["breach_challenge"] < 0.05 else -1
                if score > best.get((rule, edge), (-2,))[0]:
                    best[(rule, edge)] = (score, v, s)
            lines.append("")
    lines += ["## Best size with challenge breach under 5%", "", "| rules | edge | vol | pass 6m | median days | "
              "breach | payout 6m |", "|---|---|---|---|---|---|---|"]
    for (rule, edge), (score, v, s) in best.items():
        lines.append(f"| {rule} | {edge:.0%} | {v}% | {s['pass_6m']:.0%} | {s['median_days']} | "
                     f"{s['breach_challenge']:.1%} | {(s['payout_6m'] or 0):.1f}% |" if score >= 0 else
                     f"| {rule} | {edge:.0%} | none | - | - | - | - |")
    lines += curve(x100, sd, raw)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
