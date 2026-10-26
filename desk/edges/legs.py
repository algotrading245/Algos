"""The ten legs the research found (docs/book.json), rewritten as desk edges. Each one's card says what it does.

Times: the history and the broker both stamp bars in server time (NY + 7). Event legs work out the event's wall-clock
time per date (the London fix moves with UK summer time, the Tokyo open with NY's), find the bar that closes at it and
enter at the next bar's open, which is the event itself.
"""
import datetime as dt

import numpy as np
import pandas as pd

from desk.edges.base import (DAY, ZONES, at, atr, bar_before, close_sig, date_of, day_of, days, edge,
                             last_weekday_of_month, sig, sma, spx, std, tf_secs, tod, trade_days)

FIXPAIRS = {"EURUSD": 1, "GBPUSD": 1, "AUDUSD": 1, "USDCAD": -1, "USDCHF": -1}  # +1: the pair rises when USD falls
CROSSES = ["AUDJPY", "CADJPY", "GBPJPY"]
MORNING = ["EURJPY", "GBPJPY", "CADJPY"]


def usd_side(sym, sell_usd):
    up = FIXPAIRS.get(sym, 1) > 0
    return "buy" if up == sell_usd else "sell"


def window_trade(df, a, side, start, end, k_stop, why, n_atr=14):
    """A trade entered at server epoch `start` and left at `end`, stop k ATR away (ATR scaled to two hours)."""
    t = df["time"].values
    i = bar_before(t, start, tf_secs(df))
    if i is None:
        return None
    v = a[i]
    if not np.isfinite(v) or v <= 0:
        return None
    px = df["close"].values[i]
    d = k_stop * v
    return sig(i, side, px - d if side == "buy" else px + d, why, exit_t=end)


def scaled_atr(df, n=14, hours=2):
    """ATR of the bar frame scaled by sqrt(bars in `hours`), so a stop means the same on M5 as on M15."""
    per = max(1, int(hours * 3600 / tf_secs(df)))
    return atr(df, n).values * np.sqrt(per)


def fix_time(date):
    return at(date, 16, 0, ZONES["LONDON"])


# ---- grid -----------------------------------------------------------------------------------------------------------

@edge("grid", ["AUDCAD"], "H1", bars=20000, defaults={"months": 5, "step": 1.0, "levels": 4}, card="""
AUDCAD H1 grid (tools/backtest_hydra.py `grid`). Distance from the 5-month average of log closes, in steps of one
monthly sigma (40-month window): one equal-size level opens against the move at each step out (up to 4), each closes
when the price is back a step inside it, the first at the average. At 5 steps the whole grid stops out and waits until
the price is back within half a step. The grid's full stop-out costs one unit of the edge's risk.
""")
def grid(df, p, ctx):
    L = p["levels"]
    lp = np.log(df["close"].values.astype(float))
    t = df["time"].values
    bpd = max(1, round(DAY / tf_secs(df) * 22 / 24))  # trading bars a day (the research used hours 1-22)
    avg = pd.Series(lp).rolling(p["months"] * 22 * bpd).mean().values
    r = np.diff(lp, prepend=lp[0])
    dv = (pd.Series(r).rolling(22 * 40 * bpd).std() * np.sqrt(22 * bpd)).shift(1).values
    risk = L * (L + 1) / 2  # steps lost by equal levels at the stop-out
    out, q, dead, unit, base = [], 0, False, 1.0, 0.0
    for i in range(len(lp)):
        if not (np.isfinite(avg[i]) and np.isfinite(dv[i])) or dv[i] <= 0:
            continue
        z = (lp[i] - avg[i]) / (p["step"] * dv[i])
        az, side = abs(z), (1 if z > 0 else -1)
        if dead:
            dead = az >= 0.5
            continue
        if q == 0:
            unit, base = p["step"] * dv[i], avg[i]
        if az >= L + 1:
            new, dead = 0, True
        else:
            cur = abs(q) if q * side < 0 else 0
            new = -side * max(min(int(az), L), min(cur, int(np.ceil(az))))
        if new == q:
            continue
        d = int(np.sign(q)) if q else 0
        for k in range(abs(q), 0, -1):  # close levels the new position no longer holds
            if np.sign(new) != d or abs(new) < k:
                out.append(close_sig(i, "stop-out at 5 steps" if dead else f"back inside level {k}", slot=k))
        for k in range(1, abs(new) + 1):  # open levels it adds
            if np.sign(new) != d or k > abs(q):
                sd = "buy" if new > 0 else "sell"
                stop = float(np.exp(base - np.sign(new) * (L + 1) * unit))
                out.append(sig(i, sd, stop, f"grid level {k}: {z:+.2f} steps from the 5-month average", slot=k,
                               weight=(L + 1 - k) / risk))
        q = new
    return out


# ---- hold -----------------------------------------------------------------------------------------------------------

@edge("hold", ["XAUUSD"], "D1", bars=300, defaults={"lags": [20, 60, 120, 250], "k": 3.0, "hold": 60}, card="""
XAUUSD D1 trend hold. The share of four lookbacks (20, 60, 120, 250 days) on which gold is higher; long while any is up.
Stop and trail 3 ATR; out after 60 days, then back in on the next bar if the trend still holds.
""")
def hold(df, p, ctx):
    c = df["close"]
    s = sum(np.sign(c - c.shift(L)) for L in p["lags"]) / len(p["lags"])
    s = s.clip(lower=0).values
    a = atr(df, 14).values
    t = df["time"].values
    tf = tf_secs(df)
    out = []
    for i in range(max(p["lags"]), len(df)):
        if s[i] > 0 and np.isfinite(a[i]):
            out.append(sig(i, "buy", c.values[i] - p["k"] * a[i], f"trend score {s[i]:.2f}",
                           exit_t=t[i] + (p["hold"] + 1) * tf, trail_atr=p["k"]))
    return out


# ---- the month-end fix family ---------------------------------------------------------------------------------------

@edge("fix", list(FIXPAIRS), "M5", bars=300, needs=["spx_d1"], defaults={"pre": 120, "post": 60, "k": 3.0}, card="""
Month-end London 4pm fix. On the last weekday of the month, if the S&P is up month to date, foreign holders of US
stocks sell dollars to rebalance their hedges into the fix: sell USD for the two hours before it, then buy it back for
the hour after (the move unwinds). Down month: the mirror. Stop 3 ATR (two-hour scale).
""")
def fix(df, p, ctx):
    s = spx(ctx)
    a = scaled_atr(df)
    sym = ctx.get("market", "EURUSD")
    out = []
    for d in trade_days(df):
        if not last_weekday_of_month(d):
            continue
        mtd = s.mtd(d)
        if mtd is None or mtd == 0:
            continue
        f = fix_time(d)
        sell_usd = mtd > 0
        x = window_trade(df, a, usd_side(sym, sell_usd), f - p["pre"] * 60, f, p["k"],
                         f"month end, S&P {mtd:+.1%} MTD: {'sell' if sell_usd else 'buy'} USD into the fix")
        y = window_trade(df, a, usd_side(sym, not sell_usd), f, f + p["post"] * 60, p["k"],
                         "after the fix: the rebalancing move unwinds")
        out += [z for z in (x, y) if z]
    return out


@edge("cross", CROSSES, "M5", bars=300, needs=["spx_d1"], defaults={"pre": 120, "k": 3.0}, card="""
Month-end yen crosses. On the last weekday of an up month for the S&P, Japanese investors sell yen to rebalance: buy
AUDJPY, CADJPY and GBPJPY for the two hours into the London fix. Stop 3 ATR (two-hour scale).
""")
def cross(df, p, ctx):
    s = spx(ctx)
    a = scaled_atr(df)
    out = []
    for d in trade_days(df):
        if not last_weekday_of_month(d):
            continue
        mtd = s.mtd(d)
        if mtd is None or mtd <= 0:
            continue
        f = fix_time(d)
        x = window_trade(df, a, "buy", f - p["pre"] * 60, f, p["k"], f"month end, S&P {mtd:+.1%} MTD: sell yen")
        if x:
            out.append(x)
    return out


@edge("fall", list(FIXPAIRS), "M5", bars=300, needs=["spx_d1"], defaults={"drop": -0.03, "pre": 60, "k": 3.0}, card="""
Fix after a sell-off. When the S&P has fallen more than 3% over five days (and it is not month end), dollar demand
into the London fix is strong: buy USD for the hour before the fix. Stop 3 ATR (two-hour scale).
""")
def fall(df, p, ctx):
    s = spx(ctx)
    a = scaled_atr(df)
    sym = ctx.get("market", "EURUSD")
    out = []
    for d in trade_days(df):
        if d.weekday() > 4 or last_weekday_of_month(d):
            continue
        m5 = s.move(d, 5)
        if m5 is None or m5 >= p["drop"]:
            continue
        f = fix_time(d)
        x = window_trade(df, a, usd_side(sym, False), f - p["pre"] * 60, f, p["k"],
                         f"S&P {m5:+.1%} over 5 days: buy USD into the fix")
        if x:
            out.append(x)
    return out


# ---- Tokyo morning --------------------------------------------------------------------------------------------------

@edge("morning", MORNING, "M5", bars=300, needs=["spx_d1"], defaults={"move": 0.015, "hours": 2, "k": 3.0}, card="""
Tokyo morning reversal. After an S&P day of more than 1.5% either way, the yen crosses overshoot overnight and give
some back once Tokyo opens: trade against the S&P's move from 8:55 to 10:55 Tokyo. Stop 3 ATR (two-hour scale).
""")
def morning(df, p, ctx):
    s = spx(ctx)
    a = scaled_atr(df)
    out = []
    for d in trade_days(df):
        if d.weekday() > 4:
            continue
        r = s.last_move(d)
        if r is None or abs(r) < p["move"]:
            continue
        start = at(d, 8, 55, ZONES["TOKYO"])
        if days(start) != day_of(d):  # Tokyo 8:55 falls on this server date; skip if the clocks say otherwise
            continue
        side = "buy" if r < 0 else "sell"
        x = window_trade(df, a, side, start, start + p["hours"] * 3600, p["k"],
                         f"S&P {r:+.1%} last session: fade it in the Tokyo morning")
        if x:
            out.append(x)
    return out


# ---- after a US holiday ---------------------------------------------------------------------------------------------

_HOLIDAYS = None


def us_holidays():
    global _HOLIDAYS
    if _HOLIDAYS is None:
        from pandas.tseries.holiday import USFederalHolidayCalendar
        h = USFederalHolidayCalendar().holidays(start="2000-01-01", end="2040-12-31")
        _HOLIDAYS = {x.date() for x in h}
    return _HOLIDAYS


def after_holiday(d):
    prev = d - dt.timedelta(days=1)
    while prev.weekday() > 4:
        prev -= dt.timedelta(days=1)
    return d.weekday() < 5 and prev in us_holidays()


@edge("after", list(FIXPAIRS), "M5", bars=300, defaults={"start": [9, 5], "end": [15, 0], "k": 3.0}, card="""
The day after a US holiday. US desks come back to a backlog of dollar purchases: buy USD from 09:05 to 15:00 server
time (02:05 to 08:00 New York) on the first weekday after a federal holiday. Stop 3 ATR (two-hour scale).
""")
def after(df, p, ctx):
    a = scaled_atr(df)
    sym = ctx.get("market", "EURUSD")
    out = []
    for d in trade_days(df):
        if not after_holiday(d):
            continue
        x = window_trade(df, a, usd_side(sym, False), at(d, *p["start"]), at(d, *p["end"]), p["k"],
                         "first day after a US holiday: buy USD")
        if x:
            out.append(x)
    return out


# ---- gold dip -------------------------------------------------------------------------------------------------------

@edge("golddip", ["XAUUSD"], "M15", bars=60, defaults={"n": 20, "z": -3.0, "from": 75, "to": 465, "k": 2.0, "hold": 16},
      card="""
XAUUSD Asia-session dip. A close more than 3 standard deviations below the 20-bar mean between 01:15 and 07:45 server
time (thin Asian hours) is a liquidity hole, not news: buy it. Stop 2 ATR; out after 16 bars (4 hours).
""")
def golddip(df, p, ctx):
    c = df["close"]
    m, s = sma(c, p["n"]), std(c, p["n"])
    z = ((c - m) / s.replace(0, np.nan)).values
    a = atr(df, 14).values
    t = df["time"].values
    m_of_day = tod(t)
    tf = tf_secs(df)
    out = []
    for i in np.nonzero((z <= p["z"]) & (m_of_day >= p["from"]) & (m_of_day <= p["to"]))[0]:
        if np.isfinite(a[i]):
            out.append(sig(i, "buy", c.values[i] - p["k"] * a[i], f"z {z[i]:.2f} in Asian hours: buy the hole",
                           exit_t=t[i] + (p["hold"] + 1) * tf))
    return out


# ---- USDJPY range breakout ------------------------------------------------------------------------------------------

@edge("breakout", ["USDJPY"], "M15", bars=120, defaults={"r_from": 60, "r_to": 540, "e_from": 600, "e_to": 1080,
                                                         "exit": [23, 0]}, card="""
USDJPY Tokyo-range breakout. The range of 01:00-09:00 server time (Tokyo's session); the first close beyond it between
10:00 and 18:00 enters that way, stop at the far side of the range. One trade a day; out at 23:00 server.
""")
def breakout(df, p, ctx):
    t = df["time"].values
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    d, m = days(t), tod(t)
    out = []
    for day in np.unique(d):
        rng = (d == day) & (m >= p["r_from"]) & (m < p["r_to"])
        if rng.sum() < 8:
            continue
        hi, lo = h[rng].max(), l[rng].min()
        for i in np.nonzero((d == day) & (m >= p["e_from"]) & (m < p["e_to"]))[0]:
            if c[i] > hi:
                out.append(sig(i, "buy", lo, f"close {c[i]:.3f} above the Tokyo range {hi:.3f}",
                               exit_t=day * DAY + p["exit"][0] * 3600 + p["exit"][1] * 60))
                break
            if c[i] < lo:
                out.append(sig(i, "sell", hi, f"close {c[i]:.3f} below the Tokyo range {lo:.3f}",
                               exit_t=day * DAY + p["exit"][0] * 3600 + p["exit"][1] * 60))
                break
    return out


# ---- US index noise band --------------------------------------------------------------------------------------------

NOISE_VM = {"US100": 1.0, "US500": 1.5}  # the research's band multiples (research/noise_area_index.py)


@edge("noise", ["US100", "US500"], "M30", bars=700, defaults={"open": [16, 30], "look": 14, "exit": [23, 0],
                                                              "vm": None, "stop_vol": 3.0}, card="""
US index intraday momentum (Zarattini, Aziz, Barbon 2024; research/noise_area_index.py). sigma(time) = mean of
|close/open - 1| at that half hour over the previous 14 days. Bands: max(open 9:30 NY, yesterday's 16:00 close) x
(1 + vm sigma) and min(...) x (1 - vm sigma), vm 1.0 on US100, 1.5 on US500. Checked on each half-hour close from
10:00 to 15:30 NY: long above the upper band, short below the lower. A long leaves when a check closes below max(upper
band, the session's time-weighted average price), a short above min(lower band, TWAP), and may reverse at once.
Everything out at 16:00 NY (23:00 server). Broker stop 3 daily vols from entry, so R sizes as the paper's vol target.
""")
def noise(df, p, ctx):
    t = df["time"].values
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    start = p["open"][0] * 60 + p["open"][1]
    end = p["exit"][0] * 60 + p["exit"][1]
    n = (end - start) // 30  # bars from the open to the close (13: 9:30 to 16:00 NY)
    vm = p["vm"] if p["vm"] is not None else NOISE_VM.get(ctx.get("market"), 1.0)
    d, m = days(t), tod(t)
    k = (m - start) // 30
    inside = (m >= start) & (m < end) & ((m - start) % 30 == 0)
    frame = pd.DataFrame({"day": d[inside], "k": k[inside], "i": np.arange(len(t))[inside]})
    idx = frame.pivot_table(index="day", columns="k", values="i", aggfunc="first").reindex(columns=range(n))
    idx = idx.dropna()  # whole sessions only
    if len(idx) < p["look"] + 2:
        return []
    I = idx.to_numpy().astype(int)
    C, O = c[I], o[I[:, 0]]
    typ = (h[I] + l[I] + c[I]) / 3
    twap = np.cumsum(typ, axis=1) / np.arange(1, n + 1)
    sigma = pd.DataFrame(np.abs(C / O[:, None] - 1)).rolling(p["look"]).mean().shift(1).to_numpy()
    close16 = C[:, -1]
    dvol = pd.Series(close16).pct_change().rolling(p["look"]).std().shift(1).to_numpy()
    out = []
    for r in range(1, len(I)):
        if not np.isfinite(sigma[r, 0]) or not dvol[r] > 0:
            continue
        day = int(idx.index[r])
        hi, lo = max(O[r], close16[r - 1]), min(O[r], close16[r - 1])
        exit_t = day * DAY + end * 60
        pos = 0
        for j in range(n - 1):  # the last bar closes at 16:00: the time exit handles it
            i, px = int(I[r, j]), C[r, j]
            ub, lb = hi * (1 + vm * sigma[r, j]), lo * (1 - vm * sigma[r, j])
            if pos:
                stop = max(ub, twap[r, j]) if pos > 0 else min(lb, twap[r, j])
                if (pos > 0 and px < stop) or (pos < 0 and px > stop):
                    out.append(close_sig(i, f"close {px:.1f} back through {stop:.1f}"))
                    pos = 0
            if pos == 0:
                if px > ub:
                    pos = 1
                    out.append(sig(i, "buy", px * (1 - p["stop_vol"] * dvol[r]),
                                   f"close {px:.1f} above the noise band {ub:.1f}", exit_t=exit_t))
                elif px < lb:
                    pos = -1
                    out.append(sig(i, "sell", px * (1 + p["stop_vol"] * dvol[r]),
                                   f"close {px:.1f} below the noise band {lb:.1f}", exit_t=exit_t))
    return out
