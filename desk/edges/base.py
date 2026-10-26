"""The edge library's common parts: the registry, history bars and the indicators every edge uses.

An edge is a function signal(df, p, ctx) -> list of signals over a bar frame (columns time, open, high, low, close;
time is the bar's open in server epoch seconds, as MT5 and the history files store it). A signal is
    {"i": bar index, "side": "buy"|"sell", "stop": price, "targets": [[price, share], ...],
     "exit_t": server epoch to leave at (or None), "trail_atr": ATR multiple to trail by (or None), "why": text}
It is decided on the close of bar i; the trade enters at the open of bar i + 1. The same function runs in the sandbox
over years of history and live over the broker's last bars, where only a signal on the last closed bar counts.
"""
import datetime as dt
import os
from pathlib import Path

import numpy as np
import pandas as pd

from desk import broker, clocks, paths

HIST = Path(os.environ.get("AURUM_DESK_HIST", paths.ROOT / "marketdata" / "histdata"))
HOLDOUT = dt.date(2025, 10, 13)  # never read on or after this date (server time)
HOLDOUT_EPOCH = (HOLDOUT - dt.date(1970, 1, 1)).days * 86400
DAY = 86400

EDGES = {}


def edge(name, markets, tf, pod="systematic", kind="leg", bars=300, needs=(), defaults=None, card=""):
    """Register an edge. `bars` is how many closed bars it needs live; `needs` lists ctx frames (e.g. "spx_d1")."""
    def deco(fn):
        EDGES[name] = {"name": name, "markets": list(markets), "tf": tf, "pod": pod, "kind": kind, "bars": bars,
                       "needs": list(needs), "defaults": dict(defaults or {}), "card": card.strip(), "fn": fn}
        return fn
    return deco


def get(name):
    if name not in EDGES:
        raise KeyError(f"unknown edge {name}; known: {', '.join(sorted(EDGES))}")
    return EDGES[name]


def describe(e):
    return {k: v for k, v in e.items() if k != "fn"}


def run(name, df, params=None, ctx=None):
    e = get(name)
    p = dict(e["defaults"])
    p.update(params or {})
    if df is None or len(df) < 3:
        return []
    return e["fn"](df.reset_index(drop=True), p, ctx or {})


# ---- history --------------------------------------------------------------------------------------------------------

def hist_bars(sym, tf, cfg=None):
    """History bars for a desk instrument, cut before the holdout, weekends dropped. Cached in logs/desk/cache."""
    cfg = cfg or paths.config()
    h = cfg["instruments"].get(sym, {}).get("hist") if sym in cfg["instruments"] else sym
    if not h:
        raise ValueError(f"no history file for {sym}")
    src = HIST / f"{h}_M1.csv.gz"
    if not src.exists():
        raise FileNotFoundError(src)
    cache = paths.LOGS / "cache" / f"{h}_{tf}.pkl"
    if cache.exists() and cache.stat().st_mtime >= src.stat().st_mtime:
        return pd.read_pickle(cache)
    m1 = pd.read_csv(src, dtype={"time": "int64", "open": "float64", "high": "float64", "low": "float64",
                                 "close": "float64"})
    m1 = m1[m1["time"] < HOLDOUT_EPOCH]
    m1 = m1[weekday(m1["time"].values) < 5]
    secs = broker.TF_MIN[tf] * 60
    if secs == 60:
        out = m1.reset_index(drop=True)
    else:
        key = m1["time"].values // secs * secs
        g = m1.groupby(key, sort=True)
        out = pd.DataFrame({"time": g["time"].first().index.values, "open": g["open"].first().values,
                            "high": g["high"].max().values, "low": g["low"].min().values,
                            "close": g["close"].last().values})
    out["spread"] = 0
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_pickle(cache)
    return out


# ---- time -----------------------------------------------------------------------------------------------------------

def days(t):
    return np.asarray(t) // DAY


def weekday(t):
    """Monday 0 for server epoch seconds (1970-01-01 was a Thursday)."""
    return (np.asarray(t) // DAY + 3) % 7


def tod(t):
    """Minutes after server midnight."""
    return (np.asarray(t) % DAY) // 60


def date_of(day):
    return dt.date(1970, 1, 1) + dt.timedelta(days=int(day))


def day_of(date):
    return (date - dt.date(1970, 1, 1)).days


def at(date, hh, mm, zone=None):
    """Server epoch of a wall-clock time on `date` in `zone` (None: server time itself)."""
    if zone is None:
        return day_of(date) * DAY + hh * 3600 + mm * 60
    t = dt.datetime(date.year, date.month, date.day, hh, mm, tzinfo=zone)
    return broker.utc_to_server_epoch(t)


def bar_before(times, e, tf_secs):
    """Index of the bar that closes at event time e (its open is e - tf), or None. The trade enters at e."""
    i = int(np.searchsorted(times, e, side="left")) - 1
    if i < 0 or times[i] < e - tf_secs:
        return None
    return i


def last_weekday_of_month(date):
    nxt = date + dt.timedelta(days=1)
    while nxt.month == date.month:
        if nxt.weekday() < 5:
            return False
        nxt += dt.timedelta(days=1)
    return date.weekday() < 5


def trade_days(df):
    """The server dates present in a frame, in order."""
    return [date_of(d) for d in np.unique(days(df["time"].values))]


def tf_secs(df):
    t = df["time"].values
    if len(t) < 2:
        return 60
    return int(np.median(np.diff(t[-200:])))


# ---- indicators -----------------------------------------------------------------------------------------------------

def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def sma(s, n):
    return s.rolling(n).mean()


def std(s, n):
    return s.rolling(n).std(ddof=0)


def rsi(s, n=2):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def sig(i, side, stop, why, targets=None, exit_t=None, trail_atr=None, slot=0, weight=1.0):
    """An entry. slot: an edge may hold one position per slot (a grid's levels); weight: the share of the edge's risk
    this trade takes (the sandbox scales its R by it, live the ticket's risk_pct)."""
    return {"i": int(i), "side": side, "stop": float(stop), "targets": targets or [],
            "exit_t": int(exit_t) if exit_t is not None else None,
            "trail_atr": float(trail_atr) if trail_atr else None, "why": why, "slot": int(slot),
            "weight": float(weight)}


def close_sig(i, why, slot=0):
    """An exit by the edge's own rule, decided on the close of bar i: the slot's position leaves at the next open."""
    return {"i": int(i), "close": True, "slot": int(slot), "why": why}


# ---- the S&P context for event legs ---------------------------------------------------------------------------------

class Spx:
    """S&P D1 closes as seen before a server date: only bars of earlier days count, so nothing looks ahead."""

    def __init__(self, d1):
        self.ok = d1 is not None and len(d1) > 5
        if self.ok:
            self.day = days(d1["time"].values)
            self.close = d1["close"].values.astype(float)

    def _k(self, date):
        return int(np.searchsorted(self.day, day_of(date), side="left")) - 1  # last bar before this date

    def last_move(self, date):
        k = self._k(date)
        return None if not self.ok or k < 1 else self.close[k] / self.close[k - 1] - 1

    def move(self, date, n):
        k = self._k(date)
        return None if not self.ok or k < n else self.close[k] / self.close[k - n] - 1

    def mtd(self, date):
        """Month to date: the last close before `date` against the last close of the month before `date`'s month."""
        if not self.ok:
            return None
        k = self._k(date)
        first = day_of(date.replace(day=1))
        j = int(np.searchsorted(self.day, first, side="left")) - 1
        if k < 0 or j < 0 or k <= j:
            return None
        return self.close[k] / self.close[j] - 1


def spx(ctx):
    s = ctx.get("_spx")
    if s is None:
        s = ctx["_spx"] = Spx(ctx.get("spx_d1"))
    return s


def to_utc(server_epoch):
    return broker.server_epoch_to_utc(server_epoch)


ZONES = {"NY": clocks.NY, "LONDON": clocks.LONDON, "TOKYO": clocks.TOKYO, "UTC": clocks.UTC}
