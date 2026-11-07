"""Five textbook edges. They are the shadow benchmark: traded on paper beside the desk so its pods have a plain,
rule-based book to beat. A pod that cannot beat these over a quarter gets less capital (DESIGN.md section 13).
"""
import numpy as np

from desk.edges.base import DAY, ZONES, at, atr, date_of, days, edge, rsi, sig, sma, std, tf_secs, tod

MARKETS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "US500"]


@edge("donchian_trend", MARKETS, "D1", kind="benchmark", bars=80, defaults={"n": 20, "k": 2.0, "hold": 60}, card="""
Donchian breakout: a close beyond the prior 20-day high or low, stop and trail 2 ATR, out after 60 days.
""")
def donchian_trend(df, p, ctx):
    c, h, l = df["close"].values, df["high"], df["low"]
    hi = h.rolling(p["n"]).max().shift(1).values
    lo = l.rolling(p["n"]).min().shift(1).values
    a = atr(df, 14).values
    t, tf = df["time"].values, tf_secs(df)
    out = []
    for i in range(p["n"] + 1, len(df)):
        if not np.isfinite(a[i]):
            continue
        if c[i] > hi[i] and c[i - 1] <= hi[i - 1]:
            out.append(sig(i, "buy", c[i] - p["k"] * a[i], f"new {p['n']}-day high", exit_t=t[i] + (p["hold"] + 1) * tf,
                           trail_atr=p["k"]))
        elif c[i] < lo[i] and c[i - 1] >= lo[i - 1]:
            out.append(sig(i, "sell", c[i] + p["k"] * a[i], f"new {p['n']}-day low", exit_t=t[i] + (p["hold"] + 1) * tf,
                           trail_atr=p["k"]))
    return out


@edge("rsi2_reversion", MARKETS, "D1", kind="benchmark", bars=230, defaults={"lo": 10, "hi": 90, "k": 2.5, "hold": 5},
      card="""
Connors RSI(2): above the 200-day average and RSI(2) under 10, buy (the mirror short below it); target the 5-day
average, stop 2.5 ATR, out after 5 days.
""")
def rsi2_reversion(df, p, ctx):
    c = df["close"]
    r, m200, m5 = rsi(c, 2).values, sma(c, 200).values, sma(c, 5).values
    a = atr(df, 14).values
    cv, t, tf = c.values, df["time"].values, tf_secs(df)
    out = []
    for i in range(200, len(df)):
        if not (np.isfinite(a[i]) and np.isfinite(m200[i])):
            continue
        if cv[i] > m200[i] and r[i] < p["lo"] and m5[i] > cv[i]:
            out.append(sig(i, "buy", cv[i] - p["k"] * a[i], f"RSI2 {r[i]:.0f} in an uptrend", targets=[[m5[i], 1.0]],
                           exit_t=t[i] + (p["hold"] + 1) * tf))
        elif cv[i] < m200[i] and r[i] > p["hi"] and m5[i] < cv[i]:
            out.append(sig(i, "sell", cv[i] + p["k"] * a[i], f"RSI2 {r[i]:.0f} in a downtrend", targets=[[m5[i], 1.0]],
                           exit_t=t[i] + (p["hold"] + 1) * tf))
    return out


@edge("london_breakout", MARKETS, "M15", kind="benchmark", bars=120, defaults={}, card="""
London breakout: the Asian range (00:00-07:00 London); the first close beyond it from 07:00 to 12:00 London enters,
stop at the far side; out at 16:00 London. One trade a day.
""")
def london_breakout(df, p, ctx):
    t = df["time"].values
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    d = days(t)
    out = []
    for day in np.unique(d):
        date = date_of(day)
        if date.weekday() > 4:
            continue
        a0, a1 = at(date, 0, 0, ZONES["LONDON"]), at(date, 7, 0, ZONES["LONDON"])
        e1, x = at(date, 12, 0, ZONES["LONDON"]), at(date, 16, 0, ZONES["LONDON"])
        lo_i, hi_i = np.searchsorted(t, a0), np.searchsorted(t, a1)
        if hi_i - lo_i < 8:
            continue
        hi, lo = h[lo_i:hi_i].max(), l[lo_i:hi_i].min()
        for i in range(hi_i, np.searchsorted(t, e1)):
            if c[i] > hi:
                out.append(sig(i, "buy", lo, "close above the Asian range", exit_t=x))
                break
            if c[i] < lo:
                out.append(sig(i, "sell", hi, "close below the Asian range", exit_t=x))
                break
    return out


@edge("bollinger_reversion", MARKETS, "H1", kind="benchmark", bars=60, defaults={"n": 20, "sd": 2.0, "k": 1.5, "hold": 24},
      card="""
Bollinger fade: a close that crosses outside the 20-bar, 2-sigma band is faded to the middle band; stop 1.5 ATR, out
after 24 bars.
""")
def bollinger_reversion(df, p, ctx):
    c = df["close"]
    m, s = sma(c, p["n"]).values, std(c, p["n"]).values
    a = atr(df, 14).values
    cv, t, tf = c.values, df["time"].values, tf_secs(df)
    up, dn = m + p["sd"] * s, m - p["sd"] * s
    out = []
    for i in range(p["n"] + 1, len(df)):
        if not np.isfinite(a[i]) or not np.isfinite(up[i - 1]):
            continue
        if cv[i] > up[i] and cv[i - 1] <= up[i - 1]:
            out.append(sig(i, "sell", cv[i] + p["k"] * a[i], "close above the upper band", targets=[[m[i], 1.0]],
                           exit_t=t[i] + (p["hold"] + 1) * tf))
        elif cv[i] < dn[i] and cv[i - 1] >= dn[i - 1]:
            out.append(sig(i, "buy", cv[i] - p["k"] * a[i], "close below the lower band", targets=[[m[i], 1.0]],
                           exit_t=t[i] + (p["hold"] + 1) * tf))
    return out


@edge("ma_cross", MARKETS, "D1", kind="benchmark", bars=230, defaults={"fast": 50, "slow": 200, "k": 3.0, "hold": 60},
      card="""
Golden and death cross: the 50-day average crossing the 200-day; stop 3 ATR, out after 60 days.
""")
def ma_cross(df, p, ctx):
    c = df["close"]
    f, s = sma(c, p["fast"]).values, sma(c, p["slow"]).values
    a = atr(df, 14).values
    cv, t, tf = c.values, df["time"].values, tf_secs(df)
    out = []
    for i in range(p["slow"] + 1, len(df)):
        if not (np.isfinite(s[i - 1]) and np.isfinite(a[i])):
            continue
        if f[i] > s[i] and f[i - 1] <= s[i - 1]:
            out.append(sig(i, "buy", cv[i] - p["k"] * a[i], "50-day crossed above the 200-day",
                           exit_t=t[i] + (p["hold"] + 1) * tf))
        elif f[i] < s[i] and f[i - 1] >= s[i - 1]:
            out.append(sig(i, "sell", cv[i] + p["k"] * a[i], "50-day crossed below the 200-day",
                           exit_t=t[i] + (p["hold"] + 1) * tf))
    return out
