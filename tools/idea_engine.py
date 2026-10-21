"""Idea engine (owner 2026-10-21: "50-100 ideas tested a day"): tests the researcher's idea specs without an LLM.

The researcher writes each idea as a small JSON spec in docs/ideas/specs/ (format: docs/ideas/specs/README.md).
This script turns every pending spec into its variants (symbols x entry times x holds x sides x event offsets, at
most MAX_VARIANTS), picks the best variant on the days before 2018 only, and hands that one to the fixed gates
(tools/gates.py) with the DSR trial count raised by every variant it looked at. The result goes to
docs/ideas/results.jsonl and docs/ideas/results.md; the spec is marked done. A PASS is recorded in
docs/candidates.json like any gated candidate and raises the scanner flag, so the orchestrator wakes to judge it.

    python tools/idea_engine.py              # the keeper's call (every minute; throttled to one run per MIN_MINUTES)
    python tools/idea_engine.py --dry-run    # test every pending spec, print, write nothing, log no trial
    python tools/idea_engine.py --force      # ignore the throttle

Data: the half-hour bid grid of research/atlas_scan.py. Its value at half-hour k is the last price of that half-hour,
i.e. the price at New York 17:00 + 30(k+1) min (checked: the 08:30 NFP jump lands in k = 31). An entry "HH:MM" New
York therefore uses k = ((HH:MM - 17:00) mod 24h) * 2 - 1, and a hold of L half-hours exits at k + L. Entries before
half-hour 3 or exits after 46 are skipped (the bid-only rollover spread, see tools/edge_scan.py).
The holdout (tools/holdout.py) is cut off before anything is computed.
"""
import ast
import ctypes
import datetime as dt
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tools"))
from atlas_scan import COST, close, half, signals  # noqa: E402
from edge_scan import FIRST, LAST, big_move, vol_regime  # noqa: E402
from holdout import START as HOLDOUT_START  # noqa: E402
import gates  # noqa: E402

SPECS = ROOT / "docs" / "ideas" / "specs"
RESULTS = ROOT / "docs" / "ideas" / "results.jsonl"
RESULTS_MD = ROOT / "docs" / "ideas" / "results.md"
TRIALS = ROOT / "docs" / "trials.jsonl"
CANDIDATES = ROOT / "marketdata" / "candidates"
LOGDIR = ROOT / "logs" / "autopilot"
FLAG = LOGDIR / "scanner-flag.json"
PAUSE = LOGDIR / "PAUSE"
STATE = LOGDIR / "idea-engine-state.json"
CUT = pd.Timestamp("2018-01-01")
MIN_MINUTES = 3
MAX_VARIANTS = 200
MIN_TRADES = 20            # trades needed both before 2018 and from 2018 (to the holdout)
INDEX_COST = {"SPXUSD": 1.0, "GRXEUR": 1.5, "JPXJPY": 2.0, "WTIUSD": 3.0}
DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
NY = ZoneInfo("America/New_York")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateMutexW.restype = ctypes.c_void_p


# ---------- helpers (same as tools/autopilot/scanner_step.py) ----------

def now():
    return dt.datetime.now()


def log(text):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    with open(LOGDIR / f"{now():%Y-%m-%d}_idea-engine.log", "a", encoding="utf-8") as f:
        f.write(f"{now():%Y-%m-%d %H:%M:%S}  {text}\n")
    if DRY:
        print(text)


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def save_json(p, obj):
    if not DRY:
        Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def agent_free():
    """True when no Claude agent run holds Local\\AurumAgent (run-agent.ps1); an abandoned mutex counts as free."""
    h = k32.CreateMutexW(None, False, "Local\\AurumAgent")
    if not h:
        return True
    try:
        return k32.WaitForSingleObject(ctypes.c_void_p(h), 0) in (0, 0x80)
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def commit(paths, message):
    if DRY:
        return
    paths = [p for p in dict.fromkeys(paths) if (ROOT / p).exists()]
    if not paths:
        return
    a = git("add", "--", *paths)
    c = git("commit", "-m", message + "\n\nCommitted by tools/idea_engine.py", "--", *paths)
    if a.returncode or c.returncode:
        log(f"commit failed: {(a.stderr + c.stderr + c.stdout).strip()[:300]}")
        return
    p = git("push", "origin", "HEAD")
    if p.returncode:
        log(f"push failed (left for the next push): {p.stderr.strip()[:200]}")


# ---------- event calendars ----------

def _table(module, name):
    """A {year: "MMDD MMDD"} dict read from a research script's source (importing it would load its data)."""
    tree = ast.parse((ROOT / "research" / module).read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name:
            v = ast.literal_eval(n.value)
            return [pd.Timestamp(f"{y}-{d[:2]}-{d[2:]}") for y, s in v.items() for d in s.split()]
    raise KeyError(f"{name} not in research/{module}")


def _ny(day, hhmm):
    return [(pd.Timestamp(d).normalize(), hhmm) for d in day]


def events(name, days):
    """[(server day, release time 'HH:MM' New York or None)] for one event name."""
    name = name.lower()
    if name == "fomc":
        return _ny(_table("pre_fomc_drift.py", "FOMC"), "14:00")
    if name in ("nfp", "gdp"):
        return _ny(_table("pre_announcement_drift.py", name.upper()), "08:30")
    if name == "ism":
        from pandas.tseries.holiday import USFederalHolidayCalendar
        from pandas.tseries.offsets import CustomBusinessMonthBegin
        first = pd.date_range(days[0], days[-1], freq=CustomBusinessMonthBegin(calendar=USFederalHolidayCalendar()))
        return _ny(first, "10:00")
    if name == "opex":            # US equity options: third Friday of the month
        s = pd.Series(days)
        f = s[(s.dt.dayofweek == 4) & (s.dt.day >= 15) & (s.dt.day <= 21)]
        return _ny(f, None)
    if name == "quarter_end":
        s = pd.Series(days)
        last = s.groupby(s.dt.to_period("M")).max()
        return _ny(last[last.dt.month.isin([3, 6, 9, 12])], None)
    if name.startswith("china_"):
        series = name.split("_", 1)[1].upper()
        c = pd.read_csv(ROOT / "marketdata" / "china_calendar_nbs.csv", dtype=str)
        c = c[c.series == series]
        out = []
        for d, t in zip(c.date, c.time_utc):
            if not isinstance(t, str) or ":" not in t:
                continue
            ts = pd.Timestamp(f"{d} {t}", tz="UTC").tz_convert(NY)
            day = ts.normalize().tz_localize(None) + pd.Timedelta(days=1 if ts.hour >= 17 else 0)
            out.append((day, f"{ts.hour:02d}:{ts.minute:02d}"))
        return out
    raise ValueError(f"unknown event '{name}' (fomc, nfp, gdp, ism, opex, quarter_end, china_cpi, "
                     "china_activity, china_gdp)")


def slot_at(hhmm):
    """Grid column holding the price at New York time HH:MM."""
    h, m = (int(x) for x in hhmm.split(":"))
    return int(((h + m / 60 - 17) % 24) * 2) - 1


# ---------- one spec ----------

class Grid:
    def __init__(self):
        P, days = half()
        keep = days < HOLDOUT_START          # the holdout is never looked at
        self.P = {s: m[keep] for s, m in P.items()}
        self.days = days[keep]
        self.pos = {d: i for i, d in enumerate(self.days)}
        self.n = len(self.days)
        self.pre = np.asarray(self.days < CUT)
        self._sig = None
        self._lp = {}

    def lp(self, s):
        if s not in self._lp:
            self._lp[s] = np.log(self.P[s].astype(np.float64))
        return self._lp[s]

    def drivers(self):
        if self._sig is None:
            self._sig = signals(self.P)
        return self._sig


def sign_move(sig, kind):
    """big: the move's sign on days after a big move; big_up / big_down: 1 on those days only."""
    if kind == "big":
        return sig
    if kind == "big_up":
        return (sig > 0).astype(float)
    if kind == "big_down":
        return (sig < 0).astype(float)
    raise ValueError(f"move must be big, big_up or big_down, not '{kind}'")


def day_filter(G, sym, when):
    """(mask 0/1 per day, sign source or None) for the spec's conditions except the event."""
    m = np.ones(G.n)
    sign = None
    if "weekday" in when:
        want = [WEEKDAYS.index(w.lower()[:3]) for w in when["weekday"]]
        m *= np.isin(G.days.dayofweek, want)
    if "month_day" in when:              # 1, 2 = first trading days of the month; -1, -2 = last ones
        s = pd.Series(G.days)
        g = s.groupby(s.dt.to_period("M"))
        k, n = g.cumcount().to_numpy(), g.transform("size").to_numpy()
        hit = np.zeros(G.n, bool)
        for x in when["month_day"]:
            hit |= (k == x - 1) if x > 0 else (k == n + x)
        m *= hit
    if "vol" in when:
        m *= vol_regime(G.P, sym)[f"vol_{when['vol']}"]
    if "trend" in when:                  # sign of the 20-day return known the day before
        c = pd.Series(np.log(close(G.P[sym])))
        tr = np.sign((c - c.shift(20)).shift(1)).fillna(0).to_numpy()
        if when["trend"] == "sign":
            sign = tr
        else:
            m *= tr == (1 if when["trend"] == "up" else -1)
    if "own_move" in when:
        s = sign_move(big_move(G.P, sym), when["own_move"])
        m *= s != 0
        sign = s if when["own_move"] == "big" else sign
    if "driver" in when:
        d = when["driver"]
        src = G.drivers().get(d["symbol"])
        if src is None:
            src = big_move(G.P, d["symbol"])
        s = sign_move(src, d.get("move", "big"))
        m *= s != 0
        sign = s if d.get("move", "big") == "big" else sign
    return m, sign


def entries(spec_entry, release):
    """Grid start column for one entry token and one event release time (or None)."""
    if isinstance(spec_entry, int):
        return spec_entry
    e = str(spec_entry)
    if e.startswith("event"):
        if release is None:
            return None
        off = int(e[5:] or 0)            # half-hours from the release: event-2 = an hour before
        return slot_at(release) + off
    return slot_at(e)


def variants(spec):
    sides = {"both": ["long", "short"]}.get(spec.get("side", "both"), [spec.get("side", "both")])
    offs = (spec.get("when") or {}).get("event_offset", [0])
    offs = offs if isinstance(offs, list) else [offs]
    entry = spec["entry"] if isinstance(spec["entry"], list) else [spec["entry"]]
    return list(itertools.product(spec["symbols"], entry, spec.get("hold", [2, 4, 8]), sides, offs))


def sharpe(x):
    return float(x.mean() / x.std() * np.sqrt(252)) if x.std() > 0 else 0.0


def test_spec(G, spec):
    """Returns (best variant dict or None, number of variants, note)."""
    when = dict(spec.get("when") or {})
    V = variants(spec)
    if len(V) > MAX_VARIANTS:
        return None, 0, f"{len(V)} variants, more than {MAX_VARIANTS}: narrow the spec"
    ev = events(when["event"], G.days) if "event" in when else None
    best, tried = None, 0
    for sym, ent, L, side, off in V:
        if sym not in G.P:
            return None, 0, f"no data for {sym} (have {', '.join(sorted(G.P))})"
        tried += 1
        lp = G.lp(sym)
        mask, sign = day_filter(G, sym, when)
        start = np.full(G.n, -1)
        if ev is None:
            s = entries(ent, None)
            if s is None:
                return None, 0, "entry 'event' needs an event in 'when'"
            start[:] = s
        else:
            for d, rel in ev:
                i = G.pos.get(d)
                s = entries(ent, rel)
                if i is None or s is None or not 0 <= i + off < G.n:
                    continue
                start[i + off] = s
        ok = (mask != 0) & (start >= FIRST) & (start + L <= LAST)
        if side in ("follow", "fade"):
            if sign is None:
                return None, 0, "side follow/fade needs own_move, driver or trend 'sign' in 'when'"
            ok &= sign != 0
        idx = np.flatnonzero(ok)
        R = lp[idx, start[idx] + L] - lp[idx, start[idx]]
        sg = {"long": 1.0, "short": -1.0}.get(side)
        if sg is None:
            sg = sign[idx] * (1.0 if side == "follow" else -1.0)
        g = np.full(G.n, np.nan)
        g[idx] = sg * R
        on = ~np.isnan(g)
        if (on & G.pre).sum() < MIN_TRADES or (on & ~G.pre).sum() < MIN_TRADES:
            continue
        cost = (COST.get(sym) or INDEX_COST.get(sym, 1.5)) * 1e-4
        net = np.where(on, np.nan_to_num(g) - cost, 0.0)
        s_pre = sharpe(net[G.pre])
        if best is None or s_pre > best["sharpe_pre"]:
            best = {"symbol": sym, "entry": ent, "hold": L, "side": side, "event_offset": off,
                    "sharpe_pre": s_pre, "sharpe_post": sharpe(net[~G.pre]),
                    "trades_pre": int((on & G.pre).sum()), "trades_post": int((on & ~G.pre).sum()),
                    "bp_per_trade": float(1e4 * (np.nanmean(g[on]) - cost)), "g": g, "cost": cost}
    if best is None:
        return None, tried, f"no variant with {MIN_TRADES}+ trades before 2018 and from 2018"
    return best, tried, ""


# ---------- rule specs: daily strategies from papers and open code ----------
# A spec with "rule" holds a daily position from the server-day close (data through yesterday only) and earns the
# next day's close-to-close return. Cost: half the round-trip cost per unit of position change, plus SWAP_BP per day
# held (FTMO charges both sides overnight; 0.5 bp a night is the figure research/grid_crosses.py uses).

SWAP_BP = 0.5
RULES = ("tsmom", "donchian", "meanrev", "ma_cross", "rsi", "reversal", "xsmom")
RULE_PARAMS = {                          # defaults when the spec leaves a parameter out
    "tsmom": {"lookback": [20, 60, 120]},
    "donchian": {"lookback": [20, 55]},
    "meanrev": {"lookback": [10, 20], "z": [1.5, 2.0]},
    "ma_cross": {"fast": [10, 20], "slow": [50, 100]},
    "rsi": {"period": [2, 14], "level": [10, 30]},
    "reversal": {"lookback": [1, 5]},
    "xsmom": {"lookback": [20, 60, 120], "top": [1]},
}


def daily_close(G, s):
    cache = G.__dict__.setdefault("_dc", {})
    if s not in cache:
        cache[s] = np.log(np.asarray(close(G.P[s]), dtype=np.float64))
    return cache[s]


def rule_signal(kind, c, p):
    """-1/0/+1 per day from log closes c, known at the close of the day before (shifted by one)."""
    x = pd.Series(c)
    if kind == "tsmom":
        s = np.sign(x - x.shift(p["lookback"]))
    elif kind == "reversal":
        s = -np.sign(x - x.shift(p["lookback"]))
    elif kind == "donchian":                 # flip on a close above the prior N-day high / below the low, hold until the opposite
        n = p["lookback"]
        up = x > x.shift(1).rolling(n).max()
        dn = x < x.shift(1).rolling(n).min()
        s = pd.Series(np.where(up, 1.0, np.where(dn, -1.0, np.nan))).ffill()
    elif kind == "meanrev":                  # fade a close more than z standard deviations from its N-day mean
        n = p["lookback"]
        z = (x - x.rolling(n).mean()) / x.rolling(n).std()
        s = pd.Series(np.where(z > p["z"], -1.0, np.where(z < -p["z"], 1.0, 0.0)))
    elif kind == "ma_cross":
        if p["fast"] >= p["slow"]:
            return None
        s = np.sign(x.rolling(p["fast"]).mean() - x.rolling(p["slow"]).mean())
    elif kind == "rsi":                      # Wilder RSI; long below level, short above 100 - level
        d = x.diff()
        a = 1 / p["period"]
        up = d.clip(lower=0).ewm(alpha=a, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=a, adjust=False).mean()
        r = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        s = pd.Series(np.where(r < p["level"], 1.0, np.where(r > 100 - p["level"], -1.0, 0.0)))
    else:
        raise ValueError(f"rule must be one of {', '.join(RULES)}, not '{kind}'")
    return pd.Series(s).shift(1).fillna(0.0).to_numpy()


def hold_for(sig, k):
    """Keep each nonzero signal for k days (k = 1 leaves it as it is)."""
    if k <= 1:
        return sig
    s = pd.Series(np.where(sig != 0, sig, np.nan))
    return s.ffill(limit=k - 1).fillna(0.0).to_numpy()


def rule_variants(spec):
    kind = spec["rule"]
    grid = {**RULE_PARAMS.get(kind, {}), **(spec.get("params") or {})}
    grid.setdefault("hold", [1])
    grid.setdefault("flip", [False])
    keys = sorted(grid)
    vals = [v if isinstance(v, list) else [v] for v in (grid[k] for k in keys)]
    sides = spec.get("side", "both")
    sides = sides if isinstance(sides, list) else [sides]
    syms = [tuple(spec["symbols"])] if kind == "xsmom" else spec["symbols"]
    return [(s, dict(zip(keys, v)), side) for s in syms for v in itertools.product(*vals) for side in sides]


def cost_of(sym):
    return (COST.get(sym) or INDEX_COST.get(sym, 1.5)) * 1e-4


def test_rule(G, spec):
    """Daily position rules. Returns (best variant dict or None, number of variants, note)."""
    kind = spec["rule"]
    if kind not in RULES:
        return None, 0, f"rule must be one of {', '.join(RULES)}"
    when = dict(spec.get("when") or {})
    if set(when) - {"weekday", "month_day", "vol", "trend"}:
        return None, 0, "rule specs take only weekday, month_day, vol and trend in 'when'"
    V = rule_variants(spec)
    if len(V) > MAX_VARIANTS:
        return None, 0, f"{len(V)} variants, more than {MAX_VARIANTS}: narrow the spec"
    for s in spec["symbols"]:
        if s not in G.P:
            return None, 0, f"no data for {s} (have {', '.join(sorted(G.P))})"
    best, tried = None, 0
    for sym, p, side in V:
        legs = list(sym) if kind == "xsmom" else [sym]
        C = {s: daily_close(G, s) for s in legs}
        R = {s: np.nan_to_num(np.diff(C[s], prepend=np.nan)) for s in legs}
        W = {}
        if kind == "xsmom":                  # rank the lookback returns known yesterday; long the top, short the bottom
            if len(legs) < 2 * p["top"]:
                return None, 0, f"xsmom needs at least {2 * p['top']} symbols"
            M = pd.DataFrame({s: pd.Series(C[s]) - pd.Series(C[s]).shift(p["lookback"]) for s in legs})
            rk = M.shift(1).rank(axis=1, ascending=False)
            ok = M.shift(1).notna().all(axis=1).to_numpy()
            for s in legs:
                w = np.where(rk[s] <= p["top"], 1.0, np.where(rk[s] > len(legs) - p["top"], -1.0, 0.0)) / p["top"]
                W[s] = np.where(ok, w, 0.0)
        else:
            sig = rule_signal(kind, C[sym], p)
            if sig is None:
                continue
            W[sym] = sig
        tried += 1
        gross, costs, held = np.zeros(G.n), np.zeros(G.n), np.zeros(G.n, bool)
        for s in legs:
            w = hold_for(W[s], p["hold"]) * (-1.0 if p["flip"] else 1.0)
            if side == "long":
                w = np.clip(w, 0, None)
            elif side == "short":
                w = np.clip(w, None, 0)
            if when:
                mask, _ = day_filter(G, s, when)
                w = w * mask
            gross += w * R[s]
            costs += np.abs(np.diff(w, prepend=0.0)) * cost_of(s) / 2 + np.abs(w) * SWAP_BP * 1e-4
            held |= w != 0
        if (held & G.pre).sum() < MIN_TRADES or (held & ~G.pre).sum() < MIN_TRADES:
            continue
        net = gross - costs
        s_pre = sharpe(net[G.pre])
        if best is None or s_pre > best["sharpe_pre"]:
            label = "+".join(legs) if kind == "xsmom" else sym
            best = {"symbol": label, "entry": kind + " " + " ".join(f"{k}={v}" for k, v in p.items()
                                                                 if k not in ("hold", "flip")) + (" flip" if p["flip"] else ""),
                    "hold": p["hold"], "side": side, "event_offset": 0,
                    "sharpe_pre": s_pre, "sharpe_post": sharpe(net[~G.pre]),
                    "trades_pre": int((held & G.pre).sum()), "trades_post": int((held & ~G.pre).sum()),
                    "bp_per_trade": float(1e4 * net[held].mean()), "gross": gross, "costs": costs}
    if best is None:
        return None, tried, f"no variant in position {MIN_TRADES}+ days before 2018 and from 2018"
    return best, tried, ""


def spec_key(spec):
    """The testable content of a spec, for skipping repeats under another id."""
    keep = ("rule", "params", "symbols", "entry", "hold", "side", "when")
    return json.dumps({k: spec.get(k) for k in keep}, sort_keys=True)


def write_candidate(cid, G, best, folder):
    g, on = best.get("g"), None if best.get("g") is None else ~np.isnan(best["g"])
    for suffix, k in (("", 1.0), ("_stress", 1.5)):
        if "gross" in best:                  # rule specs: the cost is already a daily series
            r = best["gross"] - k * best["costs"]
        else:
            r = np.where(on, np.nan_to_num(g) - k * best["cost"], 0.0)
        pd.DataFrame({"day": G.days.strftime("%Y-%m-%d"), "r": r}).to_csv(folder / f"{cid}{suffix}.csv", index=False)


def run_spec(G, path, spec):
    sid = spec.get("id") or path.stem
    cid = f"idea_{sid}"
    best, tried, note = (test_rule if "rule" in spec else test_spec)(G, spec)
    row = {"id": sid, "title": spec.get("title", ""), "read": spec.get("read", "unverified"),
           "when": now().isoformat(timespec="seconds"), "variants": tried}
    if best is None:
        row.update(verdict="SKIPPED" if not tried else "NO TRADES", note=note)
        return row, None
    folder = Path(tempfile.mkdtemp()) if DRY else CANDIDATES
    folder.mkdir(parents=True, exist_ok=True)
    old = gates.CANDIDATES
    gates.CANDIDATES = folder
    try:
        write_candidate(cid, G, best, folder)
        res = gates.judge(cid, n_extra=tried)
    finally:
        gates.CANDIDATES = old
    row.update(verdict=res["verdict"], best={k: v for k, v in best.items() if k not in ("g", "cost", "gross", "costs")},
               gates={x["gate"]: x["figure"] for x in res["gates"]})
    if res["verdict"] != "PASS" and not DRY:
        for suffix in ("", "_stress"):
            (folder / f"{cid}{suffix}.csv").unlink(missing_ok=True)
    return row, res


# ---------- main ----------

def pending():
    out = []
    for p in sorted(SPECS.glob("*.json")):
        s = read_json(p)
        if isinstance(s, dict) and s.get("status", "pending") == "pending":
            # Owner's rule: an idea from a paper is tested only after the paper was read in full. "n/a" is a
            # market-structure idea with no paper behind it. Anything else waits as "unread" (not counted as pending).
            if s.get("read") not in ("in full", "n/a"):
                log(f"{p.name}: read={s.get('read')!r}, not tested until the source is read in full")
                if not DRY:
                    s["status"] = "unread"
                    save_json(p, s)
                continue
            out.append((p, s))
        elif not isinstance(s, dict):
            log(f"{p.name}: not a JSON object, skipped")
    return out


def main():
    if PAUSE.exists() and not DRY:
        return
    todo = pending()
    if not todo:
        return
    st = read_json(STATE, {}) or {}
    try:
        last = dt.datetime.fromisoformat(st.get("last", ""))
    except ValueError:
        last = None
    if not (FORCE or DRY) and last and (now() - last).total_seconds() < MIN_MINUTES * 60:
        return
    if not DRY and not agent_free():
        return                            # shares trials.jsonl, candidates.json and git with the agents
    h = k32.CreateMutexW(None, False, "Local\\AurumIdeas")
    if not h or k32.WaitForSingleObject(ctypes.c_void_p(h), 0) not in (0, 0x80):
        return
    try:
        save_json(STATE, {"last": now().isoformat(timespec="seconds")})
        G = Grid()
        touched, passed = [], []
        seen = {}                                 # testable content -> id of the spec already tested with it
        for p in sorted(SPECS.glob("*.json")):
            s = read_json(p)
            if isinstance(s, dict) and s.get("status") == "done" and not str(s.get("verdict", "")).startswith("DUP"):
                seen.setdefault(spec_key(s), s.get("id") or p.stem)
        for path, spec in todo:
            dup = seen.get(spec_key(spec))
            if dup:                               # same test under another name: no new trial, no new row
                log(f"{path.name}: same test as {dup}, marked a duplicate")
                if not DRY:
                    spec.update(status="done", verdict=f"DUPLICATE of {dup}", tested=now().isoformat(timespec="seconds"))
                    save_json(path, spec)
                    touched.append(str(path.relative_to(ROOT)))
                continue
            seen[spec_key(spec)] = spec.get("id") or path.stem
            try:
                row, res = run_spec(G, path, spec)
            except Exception as e:
                row, res = {"id": spec.get("id") or path.stem, "title": spec.get("title", ""),
                            "read": spec.get("read", "unverified"), "when": now().isoformat(timespec="seconds"), "variants": 0,
                            "verdict": "ERROR", "note": f"{type(e).__name__}: {e}"}, None
            b = row.get("best") or {}
            line = (f"| {row['when'][:16]} | {row['id']} | {row.get('read', '')} | {row['variants']} | "
                    f"{b.get('symbol', '')} {b.get('entry', '')} L{b.get('hold', '')} {b.get('side', '')} | "
                    f"{b.get('sharpe_pre', 0):.2f} / {b.get('sharpe_post', 0):.2f} | {row['verdict']} | "
                    f"{row.get('note') or row.get('gates', {}).get('dsr', '')} |")
            log(line)
            if DRY:
                continue
            if res is not None:
                if res["verdict"] == "PASS":
                    gates.record(res)            # ledger + docs/gates; logs one trial
                    extra = row["variants"] - 1
                    passed.append(res["id"])
                else:
                    extra = row["variants"]
                if extra > 0:
                    with TRIALS.open("a") as f:
                        f.write(json.dumps({"id": f"idea:{row['id']}", "when": row["when"],
                                            "verdict": row["verdict"], "count": extra}) + "\n")
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if not RESULTS_MD.exists():
                RESULTS_MD.write_text("# Idea specs tested by tools/idea_engine.py\n\nBest variant picked on the "
                                      "days before 2018; Sharpe at the real cost before 2018 / from 2018 to the "
                                      "holdout. Verdicts are tools/gates.py's.\n\n| when | id | read | variants | "
                                      "best | Sharpe | verdict | DSR or note |\n|---|---|---|---|---|---|---|---|\n",
                                      encoding="utf-8")
            with RESULTS_MD.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            spec.update(status="done", verdict=row["verdict"], tested=row["when"])
            save_json(path, spec)
            touched.append(str(path.relative_to(ROOT)))
        if DRY or not touched:
            return
        paths = touched + ["docs/ideas/results.jsonl", "docs/ideas/results.md", "docs/trials.jsonl"]
        if passed:
            paths += ["docs/candidates.json"] + [f"docs/gates/{c}.json" for c in passed]
            paths += [f"marketdata/candidates/{c}{s}.csv" for c in passed for s in ("", "_stress")]
            LOGDIR.mkdir(parents=True, exist_ok=True)
            save_json(FLAG, {"work": True, "reason": f"idea engine: {', '.join(passed)} passed every gate",
                             "request": None, "passed": passed, "at": now().isoformat(timespec="seconds")})
        commit(paths, f"Idea engine: {len(touched)} specs tested, {len(passed)} passed")
    finally:
        k32.ReleaseMutex(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    main()
