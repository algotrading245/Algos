"""The economic calendar: high-impact events from the ForexFactory weekly feed, fetched once a day.

python -m desk.news            fetch now and print this week's high-impact events
"""
import datetime as dt
import json
import sys
import urllib.request

from desk import clocks, journal, paths

FILE = paths.STATE / "calendar.json"
INDEX_CCY = {"US500": ["USD"], "US100": ["USD"], "GER40": ["EUR"], "JP225": ["JPY"], "WTI": ["USD"],
             "BTCUSD": ["USD"], "ETHUSD": ["USD"]}
STALE = dt.timedelta(hours=48)  # fetched daily with retries; two missed days means the feed is down


def currencies(instrument):
    """The currencies whose news moves an instrument."""
    if instrument in INDEX_CCY:
        return INDEX_CCY[instrument]
    if len(instrument) == 6:
        return [c for c in (instrument[:3], instrument[3:]) if c not in ("XAU", "XAG")]
    return ["USD"]


def fetch(cfg=None):
    """Download the week, keep High-impact rows, save with UTC times. Returns the rows, or None on failure."""
    cfg = cfg or paths.config()
    try:
        req = urllib.request.Request(cfg["calendar_url"], headers={"User-Agent": "aurum-desk/1.0"})
        raw = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except Exception as e:
        journal.log("calendar_error", error=str(e))
        return None
    rows = []
    for r in raw:
        if r.get("impact") != "High":
            continue
        try:
            t = dt.datetime.fromisoformat(r["date"]).astimezone(clocks.UTC)
        except (KeyError, ValueError):
            continue
        rows.append({"t": t.isoformat(timespec="seconds"), "ccy": r.get("country"), "title": r.get("title"),
                     "forecast": r.get("forecast"), "previous": r.get("previous")})
    old = paths.read_json(FILE, {}).get("events", [])
    keep = {(e["t"], e["ccy"], e["title"]): e for e in old + rows}
    cutoff = (clocks.now() - dt.timedelta(days=14)).isoformat()
    events = sorted((e for e in keep.values() if e["t"] >= cutoff), key=lambda e: e["t"])
    paths.write_json(FILE, {"fetched": clocks.now().isoformat(timespec="seconds"), "events": events})
    journal.log("calendar", events=len(rows))
    return rows


def events(start=None, end=None):
    rows = paths.read_json(FILE, {}).get("events", [])
    out = []
    for e in rows:
        t = dt.datetime.fromisoformat(e["t"])
        if (start is None or t >= start) and (end is None or t <= end):
            out.append(dict(e, time=t))
    return out


def stale(t=None):
    """Why the calendar cannot be trusted (missing, or no good fetch for STALE), or None."""
    t = t or clocks.now()
    got = paths.read_json(FILE, {}).get("fetched")
    if not got:
        return "no calendar fetched yet"
    if t - dt.datetime.fromisoformat(got) > STALE:
        return f"calendar stale (last fetch {got})"
    return None


def blocking(instrument, t=None, window_min=2):
    """The high-impact event within window_min minutes of t for this instrument's currencies, or None.
    With no trustworthy calendar every instrument is blocked: the news rule cannot be checked blind."""
    t = t or clocks.now()
    why = stale(t)
    if why:
        return {"ccy": "ALL", "title": why, "t": t.isoformat(timespec="seconds")}
    w = dt.timedelta(minutes=window_min)
    ccy = currencies(instrument)
    for e in events(t - w, t + w):
        if e["ccy"] in ccy:
            return e
    return None


def upcoming(hours=24, t=None):
    t = t or clocks.now()
    return events(t, t + dt.timedelta(hours=hours))


if __name__ == "__main__":
    got = fetch()
    if got is None:
        print("calendar fetch failed (see journal)")
        sys.exit(1)
    for e in got:
        print(e["t"], e["ccy"], e["title"])
