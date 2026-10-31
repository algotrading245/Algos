"""What j14's 13 floating-loss stops (InpPropFloatPct 1.7, Instant Funding PRO preset) cost or saved.

j14 (backtests/2026-10-18_0256_AurumFunded_ifpro) closed everything 13 times because the open positions were 1.7% of
the initial balance in loss together. The preset sets 1.7 to stay 0.3 inside the firm's Account Drawdown, which their
help page's example puts at 2% of the starting balance (the PRO figure is an open owner question). This prices each
stop: the positions it closed are rebuilt from the deal list (each close paired with the last opening deal of the
same symbol, volume and side) and marked forward on histdata M1 bid closes (server clock), as if held with no stop.

Per stop it prints the realised loss at the stop, the basket's mark at +15 min, +1 h, +4 h and at the firm's day end
(server 00:00, InpPropResetHHMM 0), and the worst mark up to that day end, all in % of the initial balance 10,000.

Limits, stated before the run: the positions' own broker stops and time exits are ignored (so the worst mark is an
upper bound on the further loss and the day-end mark is a hold-to-day-end, not the EA's own exit); the entries the EA
skipped for the rest of the day are not priced; histdata is a different feed with no spread, and its bid quotes
spike at the 23:00-01:00 rollover (lesson 9), so stops in that window are flagged and read with care.

Pre-registered reading: the stop protects the account if the held basket goes past -2.0% before the day end in most
stops (the firm would have closed it, the first time at a 50% split, the second time losing the account). It costs
if most baskets stay above -2.0% and end the day above the stop's loss. A looser setting is only worth asking about
if the baskets that stay above -2.0% recover; the preset is not changed here either way (the firm's figure is unknown).

    python research/funded_j14_floatstops.py
"""
import calendar
import gzip
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import parse_report  # noqa: E402

FOLDER = ROOT / "backtests/2026-10-18_0256_AurumFunded_ifpro"
INITIAL = 10000.0
FIRM = -2.0                                   # the firm's line in the help page's example, % of the initial balance
HIST = {"US500.cash": "SPXUSD", "US100.cash": "NSXUSD"}
MARKS = [("+15m", 15 * 60), ("+1h", 3600), ("+4h", 4 * 3600)]


def deals():
    report = max(FOLDER.glob("*.htm"), key=lambda p: p.stat().st_size)
    text = parse_report.read(report)
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text[text.find(">Deals<"):], re.S):
        c = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(c) == 13 and re.match(r"\d{4}\.\d\d\.\d\d", c[0]) and c[3] in ("buy", "sell"):
            out.append({"time": c[0], "symbol": c[2], "type": c[3], "dir": c[4], "volume": parse_report.num(c[5]),
                        "price": parse_report.num(c[6]), "profit": parse_report.num(c[10]) or 0.0,
                        "pl": sum(parse_report.num(x) or 0.0 for x in c[8:11])})
    return out


def stop_times():
    """Times of this job's floating-stop lines (its part of summary.txt starts at its own 'phase 1 started')."""
    text = (FOLDER / "summary.txt").read_text(encoding="utf-8", errors="ignore")
    part = text[text.rfind("phase 1 started, initial balance 10000.00"):]
    return re.findall(r"(\d{4}\.\d\d\.\d\d \d\d:\d\d:\d\d)\s+AurumFunded: open positions are [\d.]+ in loss together",
                      part)


def epoch(stamp):
    return calendar.timegm(datetime.strptime(stamp, "%Y.%m.%d %H:%M:%S").timetuple())


_bars = {}


def bars(symbol):
    name = HIST.get(symbol, symbol)
    if name not in _bars:
        with gzip.open(ROOT / f"marketdata/histdata/{name}_M1.csv.gz", "rt") as fh:
            df = pd.read_csv(fh, usecols=["time", "close"])
        _bars[name] = (df["time"].to_numpy(), df["close"].to_numpy())
    return _bars[name]


def path(symbol, t0, t1):
    """Histdata closes from the last bar at or before t0 through t1; the first value is the reference price."""
    t, c = bars(symbol)
    i, j = max(np.searchsorted(t, t0, "right") - 1, 0), np.searchsorted(t, t1, "right")
    return t[i:j], c[i:j]


def main():
    ds = deals()
    print(f"j14 deals parsed: {len(ds)}")
    rows = []
    for stamp in stop_times():
        t0 = epoch(stamp)
        closes = [d for d in ds if d["dir"] == "out" and 0 <= epoch(d["time"]) - t0 <= 5]
        day_end = (t0 // 86400 + 1) * 86400
        legs, realised = [], 0.0
        for d in closes:
            side = "sell" if d["type"] == "buy" else "buy"          # the position the closing deal ended
            sign = 1 if side == "buy" else -1
            opens = [o for o in ds if o["dir"] == "in" and o["symbol"] == d["symbol"] and o["type"] == side
                     and abs(o["volume"] - d["volume"]) < 1e-9 and epoch(o["time"]) <= t0]
            move = sign * (d["price"] - opens[-1]["price"]) if opens else 0.0
            usd_per_unit = d["profit"] / move if abs(move) > 1e-12 else float("nan")
            realised += d["pl"]
            legs.append((d, sign, usd_per_unit, opens[-1]["time"] if opens else "?"))
        grid = np.arange(t0, day_end + 60, 60)
        held = np.zeros(len(grid))
        missing = []
        for d, sign, k, _ in legs:
            t, c = path(d["symbol"], t0, day_end)
            if len(c) < 2 or not np.isfinite(k):
                missing.append(d["symbol"])
                continue
            idx = np.searchsorted(t, grid, "right") - 1
            held += sign * k * (c[np.clip(idx, 0, len(c) - 1)] - c[0])
        mark = (realised + held) / INITIAL * 100
        hh = int(stamp[11:13])
        rows.append({"stop": stamp, "rollover": hh >= 23 or hh < 1, "realised": realised / INITIAL * 100,
                     **{n: mark[min(s // 60, len(mark) - 1)] for n, s in MARKS},
                     "day_end": mark[-1], "worst": mark.min(), "hours_left": (day_end - t0) / 3600,
                     "legs": " ".join(f"{d['symbol']}:{'L' if s > 0 else 'S'}{d['volume']:.2f}(in {o[11:16]})"
                                      for d, s, _, o in legs), "missing": missing})

    print(f"\nfloating stops found: {len(rows)} (summary.md lists 13)")
    print("% of the initial balance; held = the closed basket marked on histdata M1 with no stop, to server 00:00")
    print(f"{'stop':19s} {'roll':4s} {'at stop':>7s} {'+15m':>6s} {'+1h':>6s} {'+4h':>6s} {'day end':>7s} "
          f"{'worst':>6s} {'h left':>6s}  positions")
    for r in rows:
        print(f"{r['stop']:19s} {'yes' if r['rollover'] else '':4s} {r['realised']:+7.2f} {r['+15m']:+6.2f} "
              f"{r['+1h']:+6.2f} {r['+4h']:+6.2f} {r['day_end']:+7.2f} {r['worst']:+6.2f} {r['hours_left']:6.1f}  "
              f"{r['legs']}{'  MISSING ' + ','.join(r['missing']) if r['missing'] else ''}")

    df = pd.DataFrame(rows)
    for label, sub in (("all", df), ("outside rollover", df[~df.rollover]), ("rollover 23-01", df[df.rollover])):
        if sub.empty:
            continue
        print(f"\n{label}: n={len(sub)}  realised at stop {sub.realised.sum():+.2f}% in total "
              f"(mean {sub.realised.mean():+.2f}%)")
        print(f"  held to day end: total {sub.day_end.sum():+.2f}% (mean {sub.day_end.mean():+.2f}%), "
              f"so the stop {'cost' if sub.day_end.sum() > sub.realised.sum() else 'saved'} "
              f"{abs(sub.day_end.sum() - sub.realised.sum()):.2f}% over these stops")
        print(f"  day end above the stop's loss: {(sub.day_end > sub.realised).sum()} of {len(sub)}; "
              f"worst mark past {FIRM:.1f}%: {(sub.worst <= FIRM).sum()} of {len(sub)}; "
              f"past -2.5%: {(sub.worst <= -2.5).sum()} of {len(sub)}")
        keep = sub[sub.worst > FIRM]
        if len(keep):
            print(f"  stops whose held basket stayed above {FIRM:.1f}% to day end: {len(keep)}, "
                  f"day-end mark minus stop loss {(keep.day_end - keep.realised).sum():+.2f}% in total")
        for lim in (-1.8, -1.9):
            stay = sub[sub.worst > lim]
            print(f"  a {abs(lim):.1f}% stop would not have fired (on these marks) in {len(stay)} of {len(sub)}; "
                  f"those end the day {(stay.day_end - stay.realised).sum():+.2f}% against the 1.7% stop")


if __name__ == "__main__":
    main()
