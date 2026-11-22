"""Normal spreads: the 20-day median spread of each symbol by hour of the server day, from the broker's M5 bars.

The liquidity rule (DESIGN.md): no new entry while the spread is wider than spread_mult x its normal level. The bar
spread MT5 reports is the narrowest of the bar, so the median by hour (Asia is wider than London) is the yardstick, and
cached once a server day.
"""
import pandas as pd

from desk import clocks, paths

FILE = paths.STATE / "spreads.json"
BARS = 20 * 288


def table(b, sym, spec):
    """{hour: median spread in price, 'all': overall median}, cached for the server day."""
    day = clocks.trading_day().isoformat()
    cache = paths.read_json(FILE, {})
    hit = cache.get(sym)
    if hit and hit.get("day") == day:
        return hit["med"]
    df = b.bars(sym, "M5", BARS)
    if df is None or len(df) < 288 or "spread" not in df:
        return None
    pt = spec["point"]
    hrs = pd.to_datetime(df["time"], unit="s").dt.hour
    sp = df["spread"].astype(float) * pt
    med = {str(h): float(v) for h, v in sp.groupby(hrs).median().items()}
    med["all"] = float(sp.median())
    cache[sym] = {"day": day, "med": med}
    paths.write_json(FILE, cache)
    return med


def normal(b, sym, spec, t=None):
    """The yardstick spread for this server hour (never below the all-day median), or None if no history."""
    med = table(b, sym, spec)
    if not med:
        return None
    h = str(clocks.server(t).hour)
    return max(med.get(h, med["all"]), med["all"])


def check(b, sym, spec, tick, mult, cost=None, t=None):
    """(ok, why). Without bar history the instrument's cost in config.json (spread + fees, price units) stands in."""
    spread = tick["ask"] - tick["bid"]
    norm = normal(b, sym, spec, t)
    if norm is None or norm <= 0:
        if cost:
            return (spread <= mult * cost, f"spread {spread:.6g} vs cost {cost:.6g} (no spread history)")
        return True, "no spread history"
    return spread <= mult * norm, f"spread {spread:.6g} vs normal {norm:.6g} x{mult}"
