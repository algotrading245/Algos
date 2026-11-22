"""Desk time. Everything is stored in UTC; sessions and briefs are set in New York or broker server time.

Server time is New York + 7 h (UTC+2 in US winter, UTC+3 in US summer), the clock IC Markets, Pepperstone and FTMO
use, so 17:00 New York is always 00:00 server and the trading day rolls at 17:00 New York.
"""
import datetime as dt
import os
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")
TOKYO = ZoneInfo("Asia/Tokyo")


def now():
    fake = os.environ.get("AURUM_DESK_NOW")  # tests pin the clock
    if fake:
        t = dt.datetime.fromisoformat(fake)
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    return dt.datetime.now(UTC)


def server(t=None):
    """Broker server wall clock (naive) for a UTC time."""
    t = t or now()
    return (t.astimezone(NY) + dt.timedelta(hours=7)).replace(tzinfo=None)


def from_server(naive):
    """UTC time for a naive server wall-clock time."""
    ny = (naive - dt.timedelta(hours=7)).replace(tzinfo=NY)
    return ny.astimezone(UTC)


def trading_day(t=None):
    """The server date: the day rolls at 17:00 New York."""
    return server(t).date()


def week_key(t=None):
    d = trading_day(t)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def fx_open(t=None):
    """FX and metals trade from Sunday 17:00 to Friday 17:00 New York."""
    s = server(t)
    wd = s.weekday()  # server Monday 00:00 = Sunday 17:00 New York
    return wd < 5


def parse_hhmm(s):
    h, m = s.split(":")
    return int(h), int(m)


def local_time(t, zone):
    return t.astimezone({"NY": NY, "LONDON": LONDON, "TOKYO": TOKYO, "UTC": UTC}[zone])


def due(event, t, last_run):
    """True when an event {at: 'HH:MM', zone: 'LONDON', days: [0..6]} has passed today and has not run since.

    last_run is the UTC time it last ran (or None). An event fires once per local day, within 3 hours of its time,
    so a PC that was off does not fire a stale brief.
    """
    loc = local_time(t, event.get("zone", "UTC"))
    h, m = parse_hhmm(event["at"])
    at = loc.replace(hour=h, minute=m, second=0, microsecond=0)
    if loc.weekday() not in event.get("days", [0, 1, 2, 3, 4]):
        return False
    if not (at <= loc < at + dt.timedelta(hours=event.get("window_h", 3))):
        return False
    return last_run is None or last_run < at.astimezone(UTC)
