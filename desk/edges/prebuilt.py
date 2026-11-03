"""The reference library (owner 2026-11-02): ~70 well-known public rules, ready for any pod to run, tune and arm.

Every edge here is kind="reference", pod="library": none is armed by default and none is the desk's own finding. A pod
runs one with `edge sandbox NAME MARKET key=value`, tunes its defaults the same way, and arms it under the usual rule
(30+ trades, PF 1.1+, positive total R in both halves of the history). The precomputed brief section shows which of
them fire on a pod's home markets.

Common params on every edge: k (ATR(14) stop multiple, the fallback when a rule has no structural stop), side (both,
long or short), hold (bars before a time exit; 0 = none), trail (1 = trail the stop by k ATR).
Decisions are on the close of bar i, entries at the next open, as everywhere on the desk.
"""
import datetime as dt

import numpy as np
import pandas as pd

from desk.edges.base import (DAY, ZONES, at, atr, bar_before, close_sig, date_of, days, edge, last_weekday_of_month,
                             rsi, sig, sma, std, tf_secs, tod, weekday)

FX = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY",
      "NZDJPY", "EURGBP", "EURCHF", "EURAUD", "AUDCAD", "AUDNZD", "GBPCHF", "NZDCAD"]
MET = ["XAUUSD", "XAGUSD", "WTI"]
IDX = ["US500", "US100", "GER40", "JP225"]
CRY = ["BTCUSD", "ETHUSD"]
ALL = FX + MET + IDX + CRY
COMMON = {"k": 2.0, "side": "both", "hold": 0, "trail": 0}


def ref(name, markets, tf, bars=300, defaults=None, card=""):
    return edge(name, markets, tf, pod="library", kind="reference", bars=bars,
                defaults={**COMMON, **(defaults or {})}, card=card)


# ---- helpers --------------------------------------------------------------------------------------------------------

def ema(s, n):
    return s.ewm(span=int(n), adjust=False).mean()


def wma(s, n):
    n = max(int(n), 1)
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: x @ w / w.sum(), raw=True)


def _tr(df):
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def _mid(df, n):
    return (df["high"].rolling(int(n)).max() + df["low"].rolling(int(n)).min()) / 2


def _b(x):
    return np.asarray(pd.Series(np.asarray(x)).fillna(False).astype(bool))


def _f(x):
    return None if x is None else np.asarray(x, dtype=float)


def _x(cond):
    """True on the first bar of each run of cond."""
    c = pd.Series(_b(cond))
    return (c & ~c.shift(1, fill_value=False)).values


def up(a, b):
    """a crosses above b (b a series or a number), both sides valid."""
    a = pd.Series(a) if not isinstance(a, pd.Series) else a
    pb = b if np.isscalar(b) else b.shift(1)
    return _b((a > b) & (a.shift(1) <= pb))


def dn(a, b):
    a = pd.Series(a) if not isinstance(a, pd.Series) else a
    pb = b if np.isscalar(b) else b.shift(1)
    return _b((a < b) & (a.shift(1) >= pb))


def _sign(a, b, band=0.0):
    """+1 where a > b + band, -1 where a < b - band, 0 elsewhere (NaN gives 0)."""
    a, b = np.asarray(a, float), np.asarray(b, float) if not np.isscalar(b) else b
    return np.where(a > b + band, 1, np.where(a < b - band, -1, 0))


def _side(x, p):
    x = np.asarray(x).copy()
    s = p.get("side", "both")
    if s == "long":
        x[x < 0] = 0
    elif s == "short":
        x[x > 0] = 0
    return x


def _hold(li, si, lo=None, so=None):
    """A position that turns long on li, short on si, and goes flat on lo (long) or so (short)."""
    li, si = _b(li), _b(si)
    lo = _b(lo) if lo is not None else None
    so = _b(so) if so is not None else None
    pos, cur = np.zeros(len(li), int), 0
    for i in range(len(li)):
        if cur == 1 and lo is not None and lo[i]:
            cur = 0
        elif cur == -1 and so is not None and so[i]:
            cur = 0
        if li[i]:
            cur = 1
        elif si[i]:
            cur = -1
        pos[i] = cur
    return pos


def _entry(i, d, c, a, t, tf, p, why, stop=None, target=None, slot=0, exit_t=None):
    k = float(p.get("k", 2.0))
    if stop is None or not np.isfinite(stop) or (stop - c) * d >= 0:
        stop = c - d * k * a
    tg = [[float(target), 1.0]] if target is not None and np.isfinite(target) and (target - c) * d > 0 else None
    h = int(p.get("hold") or 0)
    if exit_t is None and h:
        exit_t = t[i] + (h + 1) * tf
    return sig(i, "buy" if d > 0 else "sell", stop, why, targets=tg, exit_t=exit_t,
               trail_atr=k if p.get("trail") else None, slot=slot)


def _state(df, p, pos, why):
    """Trade a target position (+1, 0, -1 per bar): enter on each change, flat or reverse when it changes again."""
    pos = _side(np.nan_to_num(np.asarray(pos, dtype=float)).astype(int), p)
    c, t, tf = df["close"].values, df["time"].values, tf_secs(df)
    a = atr(df, 14).values
    out, prev = [], 0
    for i in range(1, len(df)):
        cur = int(pos[i])
        if cur == prev:
            continue
        if prev:
            out.append(close_sig(i, f"{why}: signal {'off' if not cur else 'flipped'}"))
        if cur and np.isfinite(a[i]) and a[i] > 0:
            out.append(_entry(i, cur, c[i], a[i], t, tf, p, f"{why}: {'long' if cur > 0 else 'short'}"))
        prev = cur
    return out


def _events(df, p, longs, shorts, why, stop_l=None, stop_s=None, tgt_l=None, tgt_s=None, exit_l=None, exit_s=None,
            xt=None):
    """Entry events: longs in slot 0, shorts in slot 1; an exit series closes its slot; an entry closes the other."""
    c, t, tf = df["close"].values, df["time"].values, tf_secs(df)
    a = atr(df, 14).values
    n = len(df)
    s = p.get("side", "both")
    L = _b(longs) if s != "short" else np.zeros(n, bool)
    S = _b(shorts) if s != "long" else np.zeros(n, bool)
    XL = _b(exit_l) if exit_l is not None else None
    XS = _b(exit_s) if exit_s is not None else None
    sl, ss, tl, ts, xt = map(_f, (stop_l, stop_s, tgt_l, tgt_s, xt))
    out, open_ = [], [False, False]
    for i in range(1, n):
        if open_[0] and XL is not None and XL[i]:
            out.append(close_sig(i, f"{why}: long exit", 0))
            open_[0] = False
        if open_[1] and XS is not None and XS[i]:
            out.append(close_sig(i, f"{why}: short exit", 1))
            open_[1] = False
        if not (np.isfinite(a[i]) and a[i] > 0):
            continue
        x = int(xt[i]) if xt is not None and np.isfinite(xt[i]) else None
        if L[i]:
            out.append(_entry(i, 1, c[i], a[i], t, tf, p, f"{why}: long", sl[i] if sl is not None else None,
                              tl[i] if tl is not None else None, 0, x))
            open_[0] = True
            if open_[1]:
                out.append(close_sig(i, f"{why}: long signal", 1))
                open_[1] = False
        elif S[i]:
            out.append(_entry(i, -1, c[i], a[i], t, tf, p, f"{why}: short", ss[i] if ss is not None else None,
                              ts[i] if ts is not None else None, 1, x))
            open_[1] = True
            if open_[0]:
                out.append(close_sig(i, f"{why}: short signal", 0))
                open_[0] = False
    return out


def _setup_break(df, p, setup, why):
    """A close beyond the setup bar's high (long) or low (short), stop at its other end."""
    h, l, c = df["high"], df["low"], df["close"]
    s = pd.Series(_b(setup)).shift(1, fill_value=False).values
    return _events(df, p, s & _b(c > h.shift(1)), s & _b(c < l.shift(1)), why, stop_l=l.shift(1), stop_s=h.shift(1))


def _dates(t):
    return pd.to_datetime(np.asarray(t), unit="s")


def _prev_day(df):
    """Each bar's previous server day high, low and close."""
    d = days(df["time"].values)
    g = df.groupby(d)
    H, L, C = g["high"].max().shift(1), g["low"].min().shift(1), g["close"].last().shift(1)
    return H.reindex(d).values, L.reindex(d).values, C.reindex(d).values, d


def _first_per_day(cond, d):
    c = pd.Series(_b(cond))
    return (c & (c.groupby(np.asarray(d)).cumsum() == 1)).values


def dmi(df, n=14):
    h, l = df["high"], df["low"]
    um, dm = h.diff(), -l.diff()
    pdm = pd.Series(np.where((um > dm) & (um > 0), um, 0.0))
    mdm = pd.Series(np.where((dm > um) & (dm > 0), dm, 0.0))
    w = lambda s: s.ewm(alpha=1 / n, adjust=False).mean()  # noqa: E731
    a = w(_tr(df)).replace(0, np.nan)
    pdi, mdi = 100 * w(pdm) / a, 100 * w(mdm) / a
    dx = (100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)).fillna(0)
    return pdi, mdi, w(dx)


def stoch(df, n=14, sm=3):
    hh, ll = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    k = sma(100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan), sm)
    return k, sma(k, sm)


def cci(df, n=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mad = tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma(tp, n)) / (0.015 * mad.replace(0, np.nan))


def macd(c, f=12, s=26, g=9):
    m = ema(c, f) - ema(c, s)
    return m, ema(m, g)


def supertrend_dir(df, n=10, m=3.0):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    a = atr(df, n).values
    hl2 = (h + l) / 2
    fu, fl = hl2 + m * a, hl2 - m * a
    ub, lb = fu.copy(), fl.copy()
    d, cur = np.zeros(len(c), int), 1
    for i in range(1, len(c)):
        if not np.isfinite(a[i]):
            continue
        if np.isfinite(fu[i - 1]) and not (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]):
            fu[i] = fu[i - 1]
        if np.isfinite(fl[i - 1]) and not (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]):
            fl[i] = fl[i - 1]
        if cur == 1 and c[i] < fl[i]:
            cur = -1
        elif cur == -1 and c[i] > fu[i]:
            cur = 1
        d[i] = cur
    return d


def psar_dir(df, af0=0.02, step=0.02, mx=0.2):
    h, l = df["high"].values, df["low"].values
    d = np.zeros(len(h), int)
    if len(h) < 3:
        return d
    up_, s, ep, af = True, l[0], h[0], af0
    for i in range(1, len(h)):
        s = s + af * (ep - s)
        if up_:
            s = min(s, l[i - 1], l[max(i - 2, 0)])
            if l[i] < s:
                up_, s, ep, af = False, ep, l[i], af0
            elif h[i] > ep:
                ep, af = h[i], min(af + step, mx)
        else:
            s = max(s, h[i - 1], h[max(i - 2, 0)])
            if h[i] > s:
                up_, s, ep, af = True, ep, h[i], af0
            elif l[i] < ep:
                ep, af = l[i], min(af + step, mx)
        d[i] = 1 if up_ else -1
    return d


# ---- trend ----------------------------------------------------------------------------------------------------------

def _donch(df, p, why):
    h, l, c = df["high"], df["low"], df["close"]
    n, x = int(p["n"]), int(p["x"])
    hi, lo = h.rolling(n).max().shift(1), l.rolling(n).min().shift(1)
    return _events(df, p, up(c, hi), dn(c, lo), why, exit_l=c < l.rolling(x).min().shift(1),
                   exit_s=c > h.rolling(x).max().shift(1))


@ref("turtle_55_20", ALL, "D1", 120, {"n": 55, "x": 20}, card="""
Turtle system 2: a close above the prior 55-day high buys (below the low sells); out on a close beyond the 20-day
opposite channel. Stop k ATR.
""")
def turtle_55_20(df, p, ctx):
    return _donch(df, p, f"turtle {p['n']}/{p['x']}")


@ref("turtle_20_10", ALL, "D1", 60, {"n": 20, "x": 10}, card="""
Turtle system 1: a close beyond the prior 20-day channel enters; a close beyond the 10-day opposite channel exits.
""")
def turtle_20_10(df, p, ctx):
    return _donch(df, p, f"turtle {p['n']}/{p['x']}")


@ref("donchian_h4", ALL, "H4", 120, {"n": 20, "x": 10}, card="""
Donchian channel on H4: a close beyond the prior 20-bar channel enters, the 10-bar opposite channel exits.
""")
def donchian_h4(df, p, ctx):
    return _donch(df, p, f"H4 donchian {p['n']}/{p['x']}")


@ref("donchian_mid", ALL, "D1", 100, {"n": 40}, card="""
Donchian breakout with a midline exit: a close beyond the prior 40-day channel enters, a close back through the
channel's midpoint exits.
""")
def donchian_mid(df, p, ctx):
    h, l, c = df["high"], df["low"], df["close"]
    n = int(p["n"])
    hi, lo = h.rolling(n).max().shift(1), l.rolling(n).min().shift(1)
    mid = (hi + lo) / 2
    return _events(df, p, up(c, hi), dn(c, lo), "donchian midline", exit_l=c < mid, exit_s=c > mid)


@ref("keltner_break", ALL, "D1", 80, {"n": 20, "m": 2.0}, card="""
Keltner breakout: EMA(20) +- 2 ATR(20). A close above the upper band buys, below the lower sells; a close back
through the EMA exits.
""")
def keltner_break(df, p, ctx):
    c = df["close"]
    e, a = ema(c, p["n"]), atr(df, int(p["n"]))
    return _events(df, p, up(c, e + p["m"] * a), dn(c, e - p["m"] * a), "keltner break", exit_l=c < e, exit_s=c > e)


@ref("keltner_revert", ALL, "D1", 80, {"n": 20, "m": 2.0, "hold": 10}, card="""
Keltner reversion: a close below EMA(20) - 2 ATR buys for a return to the EMA (the mirror short above), out after
10 days.
""")
def keltner_revert(df, p, ctx):
    c = df["close"]
    e, a = ema(c, p["n"]), atr(df, int(p["n"]))
    return _events(df, p, dn(c, e - p["m"] * a), up(c, e + p["m"] * a), "keltner fade", tgt_l=e, tgt_s=e)


@ref("bollinger_break", ALL, "D1", 80, {"n": 20, "m": 2.0}, card="""
Bollinger breakout: a close above SMA(20) + 2 SD buys, below the lower band sells; a close back through the SMA
exits.
""")
def bollinger_break(df, p, ctx):
    c = df["close"]
    m, s = sma(c, int(p["n"])), std(c, int(p["n"]))
    return _events(df, p, up(c, m + p["m"] * s), dn(c, m - p["m"] * s), "bollinger break", exit_l=c < m,
                   exit_s=c > m)


@ref("bollinger_squeeze", ALL, "D1", 200, {"n": 20, "m": 2.0, "look": 120, "q": 0.2}, card="""
Bollinger squeeze: after the band width sat in its lowest 20% of the last 120 days within the past 5 days, a close
beyond a band enters that way; back through the SMA exits.
""")
def bollinger_squeeze(df, p, ctx):
    c = df["close"]
    m, s = sma(c, int(p["n"])), std(c, int(p["n"]))
    bw = 4 * s / m.abs().replace(0, np.nan)
    sq = (bw <= bw.rolling(int(p["look"])).quantile(p["q"])).astype(float).rolling(5).max() > 0
    return _events(df, p, sq.values & up(c, m + p["m"] * s), sq.values & dn(c, m - p["m"] * s), "squeeze break",
                   exit_l=c < m, exit_s=c > m)


@ref("ema_cross", ALL, "H4", 200, {"f": 20, "s": 50}, card="""
EMA cross on H4: long while EMA(20) is above EMA(50), short while below; reverses on each cross.
""")
def ema_cross(df, p, ctx):
    c = df["close"]
    return _state(df, p, _sign(ema(c, p["f"]), ema(c, p["s"])), f"EMA {p['f']}/{p['s']}")


@ref("triple_ma", ALL, "D1", 150, {"f": 10, "m": 30, "s": 100}, card="""
Triple moving average: long while SMA10 > SMA30 > SMA100, short while stacked the other way, flat otherwise.
""")
def triple_ma(df, p, ctx):
    c = df["close"]
    f, m, s = sma(c, int(p["f"])), sma(c, int(p["m"])), sma(c, int(p["s"]))
    pos = np.where((f > m) & (m > s), 1, np.where((f < m) & (m < s), -1, 0))
    return _state(df, p, pos, "triple MA")


@ref("macd_cross", ALL, "D1", 100, {"f": 12, "s": 26, "g": 9}, card="""
MACD signal cross: long while MACD(12,26) is above its 9-day signal line, short while below.
""")
def macd_cross(df, p, ctx):
    m, g = macd(df["close"], p["f"], p["s"], p["g"])
    return _state(df, p, _sign(m, g), "MACD signal cross")


@ref("macd_zero", ALL, "D1", 100, {"f": 12, "s": 26}, card="""
MACD zero line: long while MACD(12,26) is above zero, short while below.
""")
def macd_zero(df, p, ctx):
    m, _ = macd(df["close"], p["f"], p["s"])
    return _state(df, p, _sign(m, 0.0), "MACD zero line")


@ref("adx_dmi", ALL, "D1", 100, {"n": 14, "th": 25}, card="""
Wilder DMI: +DI crossing above -DI with ADX(14) above 25 buys (the mirror sells); the opposite DI cross exits.
""")
def adx_dmi(df, p, ctx):
    pdi, mdi, adx = dmi(df, int(p["n"]))
    strong = _b(adx > p["th"])
    return _events(df, p, up(pdi, mdi) & strong, up(mdi, pdi) & strong, "DMI", exit_l=mdi > pdi, exit_s=pdi > mdi)


@ref("psar", ALL, "D1", 100, {"af": 0.02, "step": 0.02, "max": 0.2}, card="""
Parabolic SAR (0.02, 0.02, 0.2): always in, long above the SAR and short below, reversing at each flip.
""")
def psar(df, p, ctx):
    return _state(df, p, psar_dir(df, p["af"], p["step"], p["max"]), "parabolic SAR")


@ref("supertrend", ALL, "D1", 100, {"n": 10, "m": 3.0}, card="""
Supertrend (ATR 10, x3): long while price holds above the trailing band, short below, reversing at each flip.
""")
def supertrend(df, p, ctx):
    return _state(df, p, supertrend_dir(df, int(p["n"]), p["m"]), "supertrend")


@ref("supertrend_h4", ALL, "H4", 200, {"n": 10, "m": 3.0}, card="""
Supertrend (ATR 10, x3) on H4 bars.
""")
def supertrend_h4(df, p, ctx):
    return _state(df, p, supertrend_dir(df, int(p["n"]), p["m"]), "H4 supertrend")


def _ichi(df, p):
    tk, kj = _mid(df, p["t"]), _mid(df, p["kj"])
    a = ((tk + kj) / 2).shift(int(p["kj"]))
    b = _mid(df, p["sb"]).shift(int(p["kj"]))
    return tk, kj, np.fmax(a, b), np.fmin(a, b)


@ref("ichimoku_tk", ALL, "D1", 120, {"t": 9, "kj": 26, "sb": 52}, card="""
Ichimoku TK cross: Tenkan crossing above Kijun with price above the cloud buys (the mirror below the cloud sells);
the opposite TK cross exits.
""")
def ichimoku_tk(df, p, ctx):
    c = df["close"]
    tk, kj, top, bot = _ichi(df, p)
    return _events(df, p, up(tk, kj) & _b(c > top), dn(tk, kj) & _b(c < bot), "ichimoku TK", exit_l=tk < kj,
                   exit_s=tk > kj)


@ref("ichimoku_cloud", ALL, "D1", 120, {"t": 9, "kj": 26, "sb": 52}, card="""
Ichimoku cloud: long while the close is above the cloud, short while below, flat inside it.
""")
def ichimoku_cloud(df, p, ctx):
    c = df["close"]
    _, _, top, bot = _ichi(df, p)
    return _state(df, p, np.where(c > top, 1, np.where(c < bot, -1, 0)), "ichimoku cloud")


@ref("heikin_ashi", ALL, "D1", 60, {"n": 3}, card="""
Heikin-Ashi trend: long after 3 green Heikin-Ashi candles in a row, short after 3 red, held until the other.
""")
def heikin_ashi(df, p, ctx):
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    hac = (o + h + l + c) / 4
    hao = np.empty(len(c))
    hao[0] = (o[0] + c[0]) / 2
    for i in range(1, len(c)):
        hao[i] = (hao[i - 1] + hac[i - 1]) / 2
    n = int(p["n"])
    g = pd.Series(hac > hao).astype(int).rolling(n).sum() == n
    r = pd.Series(hac < hao).astype(int).rolling(n).sum() == n
    return _state(df, p, _hold(g, r), "heikin-ashi")


@ref("tsmom", ALL, "D1", 200, {"n": 126}, card="""
Time-series momentum (Moskowitz, Ooi, Pedersen 2012): long when the 6-month return is positive, short when negative.
""")
def tsmom(df, p, ctx):
    c = df["close"]
    return _state(df, p, _sign(c / c.shift(int(p["n"])) - 1, 0.0), f"{p['n']}-day momentum")


@ref("tsmom_vote", ALL, "D1", 400, {"lags": [21, 63, 126, 252], "th": 2}, card="""
Momentum vote: the signs of the 1, 3, 6 and 12-month returns summed; long at +2 or more, short at -2 or less.
""")
def tsmom_vote(df, p, ctx):
    c = df["close"]
    v = sum(_sign(c / c.shift(int(n)) - 1, 0.0) for n in p["lags"])
    return _state(df, p, np.where(v >= p["th"], 1, np.where(v <= -p["th"], -1, 0)), "momentum vote")


@ref("momentum_12_1", ALL, "D1", 300, {"n": 252, "skip": 21}, card="""
12-1 momentum: the return from 12 months to 1 month ago, set at each month's first bar; long if positive, short if
negative.
""")
def momentum_12_1(df, p, ctx):
    c = df["close"]
    s = pd.Series(_sign(c.shift(int(p["skip"])) / c.shift(int(p["n"])) - 1, 0.0))
    ym = _dates(df["time"].values).to_period("M").astype(str).values
    reb = np.r_[True, ym[1:] != ym[:-1]]
    return _state(df, p, s.where(reb).ffill().fillna(0).values, "12-1 momentum")


@ref("roc_break", ALL, "D1", 300, {"n": 20, "z": 1.0, "hold": 20}, card="""
Rate-of-change burst: the 20-day return crossing +1 of its 250-day SD buys (-1 sells); out after 20 days.
""")
def roc_break(df, p, ctx):
    c = df["close"]
    roc = c / c.shift(int(p["n"])) - 1
    z = roc / roc.rolling(250).std()
    return _events(df, p, up(z, p["z"]), dn(z, -p["z"]), "ROC burst")


@ref("aroon", ALL, "D1", 60, {"n": 25, "th": 70}, card="""
Aroon(25): Aroon Up crossing above Aroon Down while above 70 buys (the mirror sells); the opposite cross exits.
""")
def aroon(df, p, ctx):
    n = int(p["n"])
    au = 100 * (n - df["high"].rolling(n + 1).apply(lambda x: n - int(np.argmax(x)), raw=True)) / n
    ad = 100 * (n - df["low"].rolling(n + 1).apply(lambda x: n - int(np.argmin(x)), raw=True)) / n
    return _events(df, p, up(au, ad) & _b(au > p["th"]), up(ad, au) & _b(ad > p["th"]), "aroon", exit_l=ad > au,
                   exit_s=au > ad)


@ref("linreg_slope", ALL, "D1", 100, {"n": 50, "th": 1.0}, card="""
Regression slope: the slope of a 50-day linear fit, times 50 over ATR; long above +1, short below -1, flat between.
""")
def linreg_slope(df, p, ctx):
    n = int(p["n"])
    x = np.arange(n) - (n - 1) / 2
    sxx = (x ** 2).sum()
    slope = df["close"].rolling(n).apply(lambda y: x @ y / sxx, raw=True)
    z = slope * n / atr(df, 14)
    return _state(df, p, _sign(z, 0.0, p["th"]), "regression slope")


@ref("hull_turn", ALL, "D1", 100, {"n": 55}, card="""
Hull moving average turn: long while HMA(55) rises, short while it falls.
""")
def hull_turn(df, p, ctx):
    c, n = df["close"], int(p["n"])
    hma = wma(2 * wma(c, n // 2) - wma(c, n), int(np.sqrt(n)))
    return _state(df, p, _sign(hma.diff(), 0.0), "hull turn")


@ref("vortex", ALL, "D1", 60, {"n": 14, "band": 0.05}, card="""
Vortex(14): long once VI+ leads VI- by 0.05, short once VI- leads by 0.05, held until the other.
""")
def vortex(df, p, ctx):
    n, h, l = int(p["n"]), df["high"], df["low"]
    tr = _tr(df).rolling(n).sum()
    vp, vm = (h - l.shift(1)).abs().rolling(n).sum() / tr, (l - h.shift(1)).abs().rolling(n).sum() / tr
    return _state(df, p, _hold(vp > vm + p["band"], vm > vp + p["band"]), "vortex")


@ref("trix", ALL, "D1", 100, {"n": 15, "g": 9}, card="""
TRIX(15): long while the triple-smoothed EMA's rate of change is above its 9-day signal, short while below.
""")
def trix(df, p, ctx):
    c = df["close"]
    e = ema(ema(ema(c, p["n"]), p["n"]), p["n"])
    tx = 100 * e.pct_change()
    return _state(df, p, _sign(tx, ema(tx, p["g"])), "TRIX")


@ref("high_52w", ALL, "D1", 300, {"n": 252, "k": 3.0, "side": "long", "trail": 1}, card="""
52-week high (George and Hwang 2004): a close above the prior 252-day high buys, trailed by 3 ATR. Long only by
default; side=both adds the 52-week-low short.
""")
def high_52w(df, p, ctx):
    c, n = df["close"], int(p["n"])
    return _events(df, p, up(c, df["high"].rolling(n).max().shift(1)), dn(c, df["low"].rolling(n).min().shift(1)),
                   "52-week extreme")


@ref("atr_channel", ALL, "D1", 100, {"n": 50, "m": 1.0}, card="""
ATR channel: SMA(50) +- 1 ATR(50); a close above the upper line buys, below the lower sells, back through the SMA
exits.
""")
def atr_channel(df, p, ctx):
    c = df["close"]
    m, a = sma(c, int(p["n"])), atr(df, int(p["n"]))
    return _events(df, p, up(c, m + p["m"] * a), dn(c, m - p["m"] * a), "ATR channel", exit_l=c < m, exit_s=c > m)


@ref("trend_pullback", ALL, "D1", 230, {"n": 200, "e": 20, "hold": 10}, card="""
Pullback in trend: above the 200-day SMA, a close back above the 20-day EMA after a dip buys, stop the 5-day low (the
mirror short below the 200-day); out after 10 days.
""")
def trend_pullback(df, p, ctx):
    c = df["close"]
    m, e = sma(c, int(p["n"])), ema(c, p["e"])
    return _events(df, p, _b(c > m) & up(c, e), _b(c < m) & dn(c, e), "pullback in trend",
                   stop_l=df["low"].rolling(5).min(), stop_s=df["high"].rolling(5).max())


@ref("rsi_50_trend", ALL, "D1", 60, {"n": 14, "hi": 55, "lo": 45}, card="""
RSI trend: long once RSI(14) passes 55, short once it falls under 45, held until the other.
""")
def rsi_50_trend(df, p, ctx):
    r = rsi(df["close"], int(p["n"]))
    return _state(df, p, _hold(r > p["hi"], r < p["lo"]), "RSI trend")


@ref("chandelier", ALL, "D1", 60, {"n": 20, "x": 22, "m": 3.0}, card="""
Breakout with a chandelier exit: a close beyond the prior 20-day channel enters; out when the close falls 3 ATR(22)
below the 22-day high (above the low for shorts).
""")
def chandelier(df, p, ctx):
    h, l, c = df["high"], df["low"], df["close"]
    n, x = int(p["n"]), int(p["x"])
    a = atr(df, x)
    return _events(df, p, up(c, h.rolling(n).max().shift(1)), dn(c, l.rolling(n).min().shift(1)), "chandelier",
                   exit_l=c < h.rolling(x).max() - p["m"] * a, exit_s=c > l.rolling(x).min() + p["m"] * a)


@ref("adx_range_fade", ALL, "D1", 80, {"n": 20, "m": 2.0, "th": 20, "hold": 10}, card="""
Range fade: with ADX(14) under 20 (no trend), a close below the lower Bollinger band buys for the SMA (the mirror
sells); out after 10 days.
""")
def adx_range_fade(df, p, ctx):
    c = df["close"]
    m, s = sma(c, int(p["n"])), std(c, int(p["n"]))
    quiet = _b(dmi(df, 14)[2] < p["th"])
    return _events(df, p, quiet & dn(c, m - p["m"] * s), quiet & up(c, m + p["m"] * s), "range fade", tgt_l=m,
                   tgt_s=m)


# ---- reversion ------------------------------------------------------------------------------------------------------

@ref("rsi14_revert", ALL, "D1", 60, {"n": 14, "lo": 30, "hi": 70, "hold": 10}, card="""
Classic RSI: RSI(14) crossing back above 30 buys, back under 70 sells; target the 20-day SMA, out after 10 days.
""")
def rsi14_revert(df, p, ctx):
    r, m = rsi(df["close"], int(p["n"])), sma(df["close"], 20)
    return _events(df, p, up(r, p["lo"]), dn(r, p["hi"]), "RSI(14) turn", tgt_l=m, tgt_s=m)


@ref("connors_rsi2_ma5", ALL, "D1", 230, {"lo": 5, "hi": 95, "hold": 10}, card="""
Connors RSI(2), MA exit: above the 200-day SMA, RSI(2) under 5 buys and a close above the 5-day SMA exits (the mirror
short below the 200-day).
""")
def connors_rsi2_ma5(df, p, ctx):
    c = df["close"]
    r, m200, m5 = rsi(c, 2), sma(c, 200), sma(c, 5)
    return _events(df, p, _x((c > m200) & (r < p["lo"])), _x((c < m200) & (r > p["hi"])), "RSI(2) MA5",
                   exit_l=c > m5, exit_s=c < m5)


@ref("connors_cumrsi", ALL, "D1", 230, {"lo": 35, "hi": 165, "x_lo": 65, "x_hi": 35, "hold": 10}, card="""
Connors cumulative RSI: above the 200-day SMA, RSI(2) summed over 2 days under 35 buys, RSI(2) over 65 exits (the
mirror short).
""")
def connors_cumrsi(df, p, ctx):
    c = df["close"]
    r, m200 = rsi(c, 2), sma(c, 200)
    cr = r.rolling(2).sum()
    return _events(df, p, _x((c > m200) & (cr < p["lo"])), _x((c < m200) & (cr > p["hi"])), "cumulative RSI",
                   exit_l=r > p["x_lo"], exit_s=r < p["x_hi"])


@ref("connors_3day", ALL, "D1", 230, {"hold": 10}, card="""
Connors 3-day high/low: above the 200-day SMA, 3 days of lower highs and lower lows buys; a close above the 5-day SMA
exits (the mirror short).
""")
def connors_3day(df, p, ctx):
    h, l, c = df["high"], df["low"], df["close"]
    m200, m5 = sma(c, 200), sma(c, 5)
    down3 = ((h < h.shift(1)) & (l < l.shift(1))).astype(int).rolling(3).sum() == 3
    up3 = ((h > h.shift(1)) & (l > l.shift(1))).astype(int).rolling(3).sum() == 3
    return _events(df, p, _x(down3 & (c > m200)), _x(up3 & (c < m200)), "3-day pattern", exit_l=c > m5,
                   exit_s=c < m5)


@ref("connors_double7", ALL, "D1", 230, {"n": 7, "hold": 15}, card="""
Double 7s: above the 200-day SMA, a 7-day closing low buys and a 7-day closing high exits (the mirror short).
""")
def connors_double7(df, p, ctx):
    c, n = df["close"], int(p["n"])
    m200 = sma(c, 200)
    lo, hi = c <= c.rolling(n).min(), c >= c.rolling(n).max()
    return _events(df, p, _x(lo & (c > m200)), _x(hi & (c < m200)), "double 7s", exit_l=hi, exit_s=lo)


@ref("stoch_revert", ALL, "D1", 60, {"n": 14, "lo": 20, "hi": 80, "hold": 10}, card="""
Stochastic reversal: %K(14,3) crossing above %D under 20 buys, crossing below over 80 sells; out at the other
extreme or after 10 days.
""")
def stoch_revert(df, p, ctx):
    k, d = stoch(df, int(p["n"]))
    return _events(df, p, up(k, d) & _b(k < p["lo"]), dn(k, d) & _b(k > p["hi"]), "stochastic turn",
                   exit_l=k > p["hi"], exit_s=k < p["lo"])


@ref("stoch_trend", ALL, "D1", 60, {"n": 14, "lo": 20, "hi": 80}, card="""
Stochastic momentum: long once %K(14,3) passes 80, short once it falls under 20, held until the other.
""")
def stoch_trend(df, p, ctx):
    k, _ = stoch(df, int(p["n"]))
    return _state(df, p, _hold(k > p["hi"], k < p["lo"]), "stochastic momentum")


@ref("williams_r", ALL, "D1", 60, {"n": 10, "lo": -90, "hi": -10, "x_lo": -30, "x_hi": -70, "hold": 10}, card="""
Williams %R(10): under -90 buys, over -10 sells; out at -30 (long) or -70 (short), or after 10 days.
""")
def williams_r(df, p, ctx):
    n = int(p["n"])
    hh, ll = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    wr = -100 * (hh - df["close"]) / (hh - ll).replace(0, np.nan)
    return _events(df, p, _x(wr < p["lo"]), _x(wr > p["hi"]), "williams %R", exit_l=wr > p["x_lo"],
                   exit_s=wr < p["x_hi"])


@ref("cci_revert", ALL, "D1", 60, {"n": 20, "th": 100, "hold": 10}, card="""
CCI reversal: CCI(20) crossing back above -100 buys, back under +100 sells; target the 20-day SMA, out after 10 days.
""")
def cci_revert(df, p, ctx):
    x, m = cci(df, int(p["n"])), sma(df["close"], 20)
    return _events(df, p, up(x, -p["th"]), dn(x, p["th"]), "CCI turn", tgt_l=m, tgt_s=m)


@ref("cci_trend", ALL, "D1", 60, {"n": 20, "th": 100}, card="""
CCI breakout (Lambert): CCI(20) crossing above +100 buys, below -100 sells; a cross of zero exits.
""")
def cci_trend(df, p, ctx):
    x = cci(df, int(p["n"]))
    return _events(df, p, up(x, p["th"]), dn(x, -p["th"]), "CCI breakout", exit_l=x < 0, exit_s=x > 0)


@ref("zscore_revert", ALL, "D1", 60, {"n": 20, "z": 2.0, "hold": 10}, card="""
Z-score reversion: the close more than 2 SD under its 20-day mean buys, over sells; out when the z-score crosses
zero or after 10 days.
""")
def zscore_revert(df, p, ctx):
    c, n = df["close"], int(p["n"])
    z = (c - sma(c, n)) / std(c, n).replace(0, np.nan)
    return _events(df, p, _x(z < -p["z"]), _x(z > p["z"]), "z-score", exit_l=z > 0, exit_s=z < 0)


@ref("bollinger_pctb", ALL, "D1", 60, {"n": 20, "m": 2.0, "hold": 10}, card="""
Bollinger %b re-entry: a close back inside the lower band (%b crossing above 0) buys for the SMA, back inside the
upper band (%b under 1) sells.
""")
def bollinger_pctb(df, p, ctx):
    c, n = df["close"], int(p["n"])
    m, s = sma(c, n), std(c, n)
    pb = (c - (m - p["m"] * s)) / (2 * p["m"] * s).replace(0, np.nan)
    return _events(df, p, up(pb, 0.0), dn(pb, 1.0), "%b re-entry", tgt_l=m, tgt_s=m)


@ref("ibs_revert", IDX + MET, "D1", 60, {"lo": 0.2, "hi": 0.8, "x": 0.7, "hold": 3, "side": "long"}, card="""
Internal bar strength: a close in the bottom 20% of the day's range buys; out on a close in the top 30% or after 3
days. Long only by default (side=both adds the top-20% short).
""")
def ibs_revert(df, p, ctx):
    h, l, c = df["high"], df["low"], df["close"]
    ibs = (c - l) / (h - l).replace(0, np.nan)
    return _events(df, p, _b(ibs < p["lo"]), _b(ibs > p["hi"]), "IBS", exit_l=ibs > p["x"],
                   exit_s=ibs < 1 - p["x"])


@ref("envelope_revert", ALL, "D1", 60, {"n": 20, "pct": 0.02, "hold": 10}, card="""
Moving-average envelope: a close 2% under the 20-day SMA buys for the SMA, 2% over sells.
""")
def envelope_revert(df, p, ctx):
    c = df["close"]
    m = sma(c, int(p["n"]))
    return _events(df, p, dn(c, m * (1 - p["pct"])), up(c, m * (1 + p["pct"])), "envelope", tgt_l=m, tgt_s=m)


@ref("down_streak", ALL, "D1", 30, {"n": 4, "hold": 5}, card="""
Streak reversal: 4 down closes in a row buys, out on the first up close (the mirror after 4 up closes).
""")
def down_streak(df, p, ctx):
    c, n = df["close"], int(p["n"])
    d, u = c < c.shift(1), c > c.shift(1)
    return _events(df, p, _x(d.astype(int).rolling(n).sum() == n), _x(u.astype(int).rolling(n).sum() == n),
                   "streak", exit_l=u, exit_s=d)


@ref("rsi2_h1", ALL, "H1", 230, {"lo": 10, "hi": 90, "hold": 24}, card="""
RSI(2) on H1: above the 200-hour SMA, RSI(2) under 10 buys and a close above the 5-hour SMA exits (the mirror short).
""")
def rsi2_h1(df, p, ctx):
    c = df["close"]
    r, m200, m5 = rsi(c, 2), sma(c, 200), sma(c, 5)
    return _events(df, p, _x((c > m200) & (r < p["lo"])), _x((c < m200) & (r > p["hi"])), "H1 RSI(2)",
                   exit_l=c > m5, exit_s=c < m5)


# ---- intraday -------------------------------------------------------------------------------------------------------

SESS = {"US500": ("NY", 9, 30), "US100": ("NY", 9, 30), "GER40": ("LONDON", 8, 0), "JP225": ("TOKYO", 9, 0)}
CLOSE = {"US500": ("NY", 16, 0), "US100": ("NY", 16, 0), "GER40": ("LONDON", 16, 30), "JP225": ("TOKYO", 15, 0)}


def _weekdays(t):
    for d in np.unique(days(t)):
        date = date_of(d)
        if date.weekday() < 5:
            yield d, date


def _next_weekday(date):
    nd = date + dt.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += dt.timedelta(days=1)
    return nd


def _orb(df, p, zone, hh, mm, why):
    t, h, l, c = (df[k].values for k in ("time", "high", "low", "close"))
    tf, side, out = tf_secs(df), p.get("side", "both"), []
    for _, date in _weekdays(t):
        s = at(date, hh, mm, ZONES[zone])
        i0, i1 = np.searchsorted(t, s), np.searchsorted(t, s + int(p["mins"]) * 60)
        if i1 - i0 < 2 or i1 >= len(t):
            continue
        hi, lo = h[i0:i1].max(), l[i0:i1].min()
        rng = hi - lo
        if rng <= 0:
            continue
        x = s + int(p["exit_h"] * 3600)
        tx = p.get("tgt_x") or 0
        for i in range(i1, min(np.searchsorted(t, s + int(p["until"]) * 60), len(t))):
            if t[i] + tf >= x:
                break
            if c[i] > hi and side != "short":
                out.append(sig(i, "buy", lo, f"{why}: close above the {p['mins']}-minute range",
                               targets=[[c[i] + tx * rng, 1.0]] if tx else None, exit_t=x))
                break
            if c[i] < lo and side != "long":
                out.append(sig(i, "sell", hi, f"{why}: close below the {p['mins']}-minute range",
                               targets=[[c[i] - tx * rng, 1.0]] if tx else None, exit_t=x))
                break
    return out


@ref("orb", IDX, "M5", 400, {"mins": 30, "until": 180, "exit_h": 6, "tgt_x": 2.0}, card="""
Opening range breakout at each index's cash open (US 09:30 NY, GER40 08:00 London, JP225 09:00 Tokyo): the first
close beyond the first 30 minutes' range within 3 hours enters, stop the other side, target 2 ranges, out after 6 h.
""")
def orb(df, p, ctx):
    zone, hh, mm = SESS.get(ctx.get("market"), SESS["US500"])
    return _orb(df, p, zone, hh, mm, "opening range")


@ref("orb_london", FX + MET, "M15", 200, {"mins": 60, "until": 300, "exit_h": 10, "tgt_x": 1.5, "hh": 7, "mm": 0},
     card="""
London opening range: the 07:00-08:00 London range; the first close beyond it by 12:00 enters, stop the other side,
target 1.5 ranges, out at 17:00 London.
""")
def orb_london(df, p, ctx):
    return _orb(df, p, "LONDON", int(p["hh"]), int(p["mm"]), "London range")


@ref("dual_thrust", IDX, "M5", 1600, {"k1": 0.3, "k2": 0.7, "n": 4, "open_min": 60, "end_h": 22}, card="""
Dual Thrust (Michael Chalek): range = max(HH-LC, HC-LL) of the last 4 days; a close above the day's open + 0.3 range
buys, below open - 0.7 range sells; stop the open, out at 22:00 server. One trade a day.
""")
def dual_thrust(df, p, ctx):
    t, o, h, l, c = (df[k].values for k in ("time", "open", "high", "low", "close"))
    tf, side, n, out = tf_secs(df), p.get("side", "both"), int(p["n"]), []
    d = days(t)
    ud, first = np.unique(d, return_index=True)
    g = pd.DataFrame({"d": d, "h": h, "l": l, "c": c}).groupby("d")
    dh, dl, dc = g["h"].max().values, g["l"].min().values, g["c"].last().values
    for j in range(n, len(ud)):
        if date_of(ud[j]).weekday() >= 5:
            continue
        R = max(dh[j - n:j].max() - dc[j - n:j].min(), dc[j - n:j].max() - dl[j - n:j].min())
        op = o[first[j]]
        if R <= 0:
            continue
        x = int(ud[j] * DAY + p["end_h"] * 3600)
        end = first[j + 1] if j + 1 < len(ud) else len(t)
        for i in range(max(first[j], np.searchsorted(t, ud[j] * DAY + int(p["open_min"]) * 60)), end):
            if t[i] + tf >= x:
                break
            if c[i] > op + p["k1"] * R and side != "short":
                out.append(sig(i, "buy", op, "dual thrust: above the upper line", exit_t=x))
                break
            if c[i] < op - p["k2"] * R and side != "long":
                out.append(sig(i, "sell", op, "dual thrust: below the lower line", exit_t=x))
                break
    return out


def _gap_days(df):
    """(i_open, prev_close, e_open, e_close) per NY session: the bar closing at 09:30 NY and the prior 16:00 close."""
    t, c = df["time"].values, df["close"].values
    tf, NY, pc = tf_secs(df), ZONES["NY"], None
    for _, date in _weekdays(t):
        eo, ec = at(date, 9, 30, NY), at(date, 16, 0, NY)
        io = bar_before(t, eo, tf)
        if io is not None and pc is not None:
            yield io, pc, eo, ec
        ic = bar_before(t, ec, tf)
        if ic is not None:
            pc = c[ic]


@ref("gap_fade", ["US500", "US100"], "M5", 600, {"min_gap": 0.0015, "max_gap": 0.01, "stop_x": 1.0, "exit_h": 3},
     card="""
Opening gap fade: a gap of 0.15-1% between the prior 16:00 NY close and the 09:30 open is faded at the open,
target the prior close, stop one more gap away, out after 3 hours.
""")
def gap_fade(df, p, ctx):
    c, tf, side, out = df["close"].values, tf_secs(df), p.get("side", "both"), []
    for io, pc, eo, ec in _gap_days(df):
        g = c[io] - pc
        if not (p["min_gap"] <= abs(g) / pc <= p["max_gap"]):
            continue
        d = -1 if g > 0 else 1
        if (d > 0 and side == "short") or (d < 0 and side == "long"):
            continue
        out.append(sig(io, "buy" if d > 0 else "sell", c[io] - d * abs(g) * p["stop_x"], "gap fade",
                       targets=[[pc, 1.0]], exit_t=eo + int(p["exit_h"] * 3600)))
    return out


@ref("gap_go", ["US500", "US100"], "M5", 600, {"min_gap": 0.003, "wait": 30}, card="""
Gap and go: a gap of 0.3%+ that still holds beyond the open price 30 minutes after 09:30 NY enters with it, stop the
extreme since the open, out at 16:00 NY.
""")
def gap_go(df, p, ctx):
    t, h, l, c = (df[k].values for k in ("time", "high", "low", "close"))
    tf, side, out = tf_secs(df), p.get("side", "both"), []
    for io, pc, eo, ec in _gap_days(df):
        g = c[io] - pc
        if abs(g) / pc < p["min_gap"]:
            continue
        i = bar_before(t, eo + int(p["wait"]) * 60, tf)
        if i is None or i <= io or t[i] + tf >= ec:
            continue
        if g > 0 and c[i] > c[io] and side != "short":
            out.append(sig(i, "buy", l[io + 1:i + 1].min(), "gap and go up", exit_t=ec))
        elif g < 0 and c[i] < c[io] and side != "long":
            out.append(sig(i, "sell", h[io + 1:i + 1].max(), "gap and go down", exit_t=ec))
    return out


@ref("session_mean", FX + MET, "M15", 100, {"n": 32, "z": 2.5, "from": 480, "to": 1200, "hold": 16}, card="""
Intraday mean reversion on M15: the close 2.5 SD from its 8-hour mean, between 08:00 and 20:00 server, is faded
toward the mean; out after 4 hours.
""")
def session_mean(df, p, ctx):
    c, n = df["close"], int(p["n"])
    m = sma(c, n)
    z = (c - m) / std(c, n).replace(0, np.nan)
    m_ = tod(df["time"].values)
    ok = (m_ >= p["from"]) & (m_ < p["to"])
    return _events(df, p, ok & _x(z < -p["z"]), ok & _x(z > p["z"]), "session mean", tgt_l=m, tgt_s=m)


def _pivots(df):
    H, L, C, d = _prev_day(df)
    P = (H + L + C) / 3
    return P, 2 * P - H, 2 * P - L, P - (H - L), P + (H - L), d


@ref("pivot_bounce", FX + MET + IDX, "M15", 200, {}, card="""
Floor pivot bounce: the first M15 bar of the day to dip through yesterday's S1 and close back above it buys, target
the pivot (the mirror at R1); out at the day's end.
""")
def pivot_bounce(df, p, ctx):
    l, h, c = df["low"].values, df["high"].values, df["close"].values
    P, S1, R1, _, _, d = _pivots(df)
    xt = (d + 1) * DAY - tf_secs(df)
    return _events(df, p, _first_per_day((l <= S1) & (c > S1) & (c < P), d),
                   _first_per_day((h >= R1) & (c < R1) & (c > P), d), "pivot bounce", tgt_l=P, tgt_s=P, xt=xt)


@ref("pivot_break", FX + MET + IDX, "M15", 200, {}, card="""
Floor pivot breakout: the first close of the day above yesterday's R1 buys, stop the pivot, target R2 (the mirror
below S1); out at the day's end.
""")
def pivot_break(df, p, ctx):
    c = df["close"]
    P, S1, R1, S2, R2, d = _pivots(df)
    xt = (d + 1) * DAY - tf_secs(df)
    return _events(df, p, _first_per_day(up(c, pd.Series(R1)), d), _first_per_day(dn(c, pd.Series(S1)), d),
                   "pivot break", stop_l=P, stop_s=P, tgt_l=R2, tgt_s=S2, xt=xt)


@ref("overnight_drift", IDX, "H1", 100, {"k": 4.0, "side": "long"}, card="""
Overnight drift: buy the index at its cash close (US 16:00 NY, GER40 16:30 London, JP225 15:00 Tokyo), sell at the
next cash open. Long only by default.
""")
def overnight_drift(df, p, ctx):
    m = ctx.get("market")
    zone, ch, cm = CLOSE.get(m, CLOSE["US500"])
    _, oh, om = SESS.get(m, SESS["US500"])
    t, c = df["time"].values, df["close"].values
    a, tf, out = atr(df, 14).values, tf_secs(df), []
    d = -1 if p.get("side") == "short" else 1
    for _, date in _weekdays(t):
        i = bar_before(t, at(date, ch, cm, ZONES[zone]), tf)
        if i is None or not (np.isfinite(a[i]) and a[i] > 0):
            continue
        out.append(_entry(i, d, c[i], a[i], t, tf, {**p, "hold": 0}, "overnight drift",
                          exit_t=at(_next_weekday(date), oh, om, ZONES[zone])))
    return out


# ---- patterns -------------------------------------------------------------------------------------------------------

@ref("williams_vb", ALL, "D1", 30, {"f": 0.6, "hold": 2}, card="""
Larry Williams volatility breakout, close version: a day that closes more than 0.6 of yesterday's range above its
open buys (below sells); out after 2 days.
""")
def williams_vb(df, p, ctx):
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    r = (h - l).shift(1)
    return _events(df, p, _b(c - o > p["f"] * r), _b(o - c > p["f"] * r), "volatility breakout")


@ref("inside_bar", ALL, "D1", 30, {"hold": 5}, card="""
Inside bar breakout: after a day inside the prior day's range, a close beyond the inside day's high buys (below its
low sells), stop its other end; out after 5 days.
""")
def inside_bar(df, p, ctx):
    h, l = df["high"], df["low"]
    return _setup_break(df, p, (h < h.shift(1)) & (l > l.shift(1)), "inside bar")


@ref("nr7", ALL, "D1", 30, {"n": 7, "hold": 5}, card="""
NR7 (Toby Crabel): after the narrowest range of 7 days, a close beyond that day's high or low enters, stop its other
end; out after 5 days.
""")
def nr7(df, p, ctx):
    r = df["high"] - df["low"]
    return _setup_break(df, p, r <= r.rolling(int(p["n"])).min(), "NR7")


@ref("nr4_ib", ALL, "D1", 30, {"hold": 5}, card="""
NR4 inside bar (Crabel): a day that is both the narrowest of 4 and inside the prior day, then a close beyond it.
""")
def nr4_ib(df, p, ctx):
    h, l = df["high"], df["low"]
    r = h - l
    return _setup_break(df, p, (r <= r.rolling(4).min()) & (h < h.shift(1)) & (l > l.shift(1)), "NR4 inside bar")


@ref("outside_bar", ALL, "D1", 30, {"hold": 5}, card="""
Outside bar reversal: a day that takes out both sides of the prior day and closes above its high buys, stop the
day's low (the mirror sells); out after 5 days.
""")
def outside_bar(df, p, ctx):
    h, l, c = df["high"], df["low"], df["close"]
    out_ = (h > h.shift(1)) & (l < l.shift(1))
    return _events(df, p, _b(out_ & (c > h.shift(1))), _b(out_ & (c < l.shift(1))), "outside bar", stop_l=l,
                   stop_s=h)


@ref("pin_bar", ALL, "D1", 30, {"n": 10, "wick": 0.66, "hold": 5}, card="""
Pin bar: a 10-day low with a lower wick of two thirds of the range and a close in the top third buys, stop the low
(the mirror at a 10-day high sells); out after 5 days.
""")
def pin_bar(df, p, ctx):
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    r = (h - l).replace(0, np.nan)
    lw, uw = (np.minimum(o, c) - l) / r, (h - np.maximum(o, c)) / r
    n = int(p["n"])
    bull = (l <= l.rolling(n).min()) & (lw >= p["wick"]) & ((c - l) / r >= 2 / 3)
    bear = (h >= h.rolling(n).max()) & (uw >= p["wick"]) & ((h - c) / r >= 2 / 3)
    return _events(df, p, _b(bull), _b(bear), "pin bar", stop_l=l, stop_s=h)


# ---- calendar -------------------------------------------------------------------------------------------------------

def _last_wd(df):
    return np.array([last_weekday_of_month(x.date()) for x in _dates(df["time"].values)])


@ref("turn_of_month", IDX + MET, "D1", 30, {"hold": 4, "k": 3.0, "side": "long"}, card="""
Turn of the month (Ariel 1987; Lakonishok and Smidt 1988): buy the close of the month's last weekday, out after 4
days. Long only by default.
""")
def turn_of_month(df, p, ctx):
    return _events(df, p, _last_wd(df), np.zeros(len(df), bool) if p.get("side") != "short" else _last_wd(df),
                   "turn of the month")


@ref("halloween", IDX, "D1", 30, {"k": 6.0, "side": "long"}, card="""
Halloween effect (Bouman and Jacobsen 2002): long from the last weekday of October to the last weekday of April, flat
over the summer. Long only by default.
""")
def halloween(df, p, ctx):
    m = _dates(df["time"].values).month.values
    lw = _last_wd(df)
    return _events(df, p, lw & (m == 10), lw & (m == 4) & (p.get("side") == "short"), "halloween",
                   exit_l=lw & (m == 4), exit_s=lw & (m == 10))


@ref("weekday_drift", IDX, "D1", 30, {"wd": 0, "hold": 1, "k": 3.0, "side": "long"}, card="""
Day-of-week drift: buy the close of weekday wd (0 = Monday), out a day later. Long only by default.
""")
def weekday_drift(df, p, ctx):
    w = weekday(df["time"].values) == int(p["wd"])
    return _events(df, p, w, w if p.get("side") == "short" else np.zeros(len(df), bool), "weekday drift")


@ref("seasonal_month", ALL, "D1", 2000, {"min_years": 5, "th": 0.0, "k": 3.0}, card="""
Monthly seasonality (Heston and Sadka 2008): each month, the average return of the same calendar month in the prior
years (5 at least); long if above th, short if below -th, set on the month's first bar.
""")
def seasonal_month(df, p, ctx):
    dts = _dates(df["time"].values)
    ym = (dts.year * 12 + dts.month - 1).values
    r = pd.Series(df["close"].values).groupby(ym).last().pct_change()
    rd = {int(k): v for k, v in r.items() if np.isfinite(v)}
    ks = sorted(rd)
    exp = {}
    for k in r.index:
        v = [rd[j] for j in range(int(k) - 12, (ks[0] if ks else k) - 1, -12) if j in rd]
        exp[int(k)] = np.mean(v) if len(v) >= p["min_years"] else np.nan
    e = np.array([exp.get(int(k), np.nan) for k in ym])
    return _state(df, p, np.where(e > p["th"], 1, np.where(e < -p["th"], -1, 0)), "monthly seasonality")


@ref("graziani_tsr", ["US500", "US100"], "D1", 60, {"exit_day": 0, "k": 3.0, "side": "long"}, card="""
Graziani (2024) time-series reversal: on the month's last weekday, if the close is below the close on the fourth
Friday, buy; out at the next month's last weekday (exit_day 0) or the first close on or after day exit_day of the
next month. Failed the desk's gate at halves (docs/gates/graziani_ea.json): a reference, not a leg.
""")
def graziani_tsr(df, p, ctx):
    dts = _dates(df["time"].values)
    c, t, tf = df["close"].values, df["time"].values, tf_secs(df)
    a = atr(df, 14).values
    mo, dd = dts.month.values, dts.day.values
    out, fri, fourth, entry_m, open_ = [], None, 0, None, False
    for i in range(len(c)):
        if i == 0 or mo[i] != mo[i - 1]:
            x = dts[i]
            fourth = 1 + (4 - dt.date(x.year, x.month, 1).weekday()) % 7 + 21
            fri = None
        if dd[i] <= fourth:
            fri = c[i]
        if i == 0:
            continue
        if open_ and p["exit_day"] and mo[i] != entry_m and dd[i] >= p["exit_day"]:
            out.append(close_sig(i, "graziani: day exit"))
            open_ = False
        if last_weekday_of_month(dts[i].date()):
            if open_:
                out.append(close_sig(i, "graziani: month end"))
                open_ = False
            if fri is not None and c[i] < fri and np.isfinite(a[i]) and a[i] > 0 and p.get("side") != "short":
                out.append(_entry(i, 1, c[i], a[i], t, tf, {**p, "hold": 0}, "graziani: month fell after the "
                                  "fourth Friday"))
                open_, entry_m = True, mo[i]
    return out


# ---- carry ----------------------------------------------------------------------------------------------------------

RATES = {"USD": 4.375, "EUR": 2.0, "GBP": 4.0, "JPY": 0.5, "CHF": 0.0, "CAD": 2.75, "AUD": 3.6, "NZD": 3.25}


@ref("carry", FX, "D1", 120, {"min_diff": 1.0, "n": 100, "k": 3.0, "rates": RATES}, card="""
FX carry with a trend filter: long the higher-yielding currency when the policy-rate gap is 1 point or more and the
pair is above its 100-day SMA (short when the gap is the other way and below it). The rates are a param (rates=...);
update them when a central bank moves.
""")
def carry(df, p, ctx):
    m = ctx.get("market") or ""
    rates = p.get("rates") or RATES
    b, q = m[:3], m[3:6]
    if b not in rates or q not in rates:
        return []
    diff = rates[b] - rates[q]
    c = df["close"]
    s = sma(c, int(p["n"]))
    if diff >= p["min_diff"]:
        pos = np.where(c > s, 1, 0)
    elif diff <= -p["min_diff"]:
        pos = np.where(c < s, -1, 0)
    else:
        pos = np.zeros(len(c), int)
    return _state(df, p, pos, f"carry {b} {rates[b]} vs {q} {rates[q]}")
