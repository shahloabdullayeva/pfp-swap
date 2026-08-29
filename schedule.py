from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Tashkent')

# Charlotte's rota, as (start hour, length in hours) per weekday. Mon=0 .. Sun=6.
# Wed-Sun 16:00-00:00, Mon and Tue off. In force from Wed 3 Sep 2026.
BASE = {2: (16, 8), 3: (16, 8), 4: (16, 8), 5: (16, 8), 6: (16, 8)}

# One-off changes, keyed by the date the shift STARTS; these beat BASE.
# Dina asked for two 12-hour weekend days, 16:00-04:00 (agreed 29 Aug 2026).
OVERRIDES = {
    date(2026, 8, 29): (16, 12),
    date(2026, 8, 30): (16, 12),
}

# How late a boundary cron job may fire and still count as "on the boundary".
SLACK_MINUTES = 30


def _now(now):
    return now if now is not None else datetime.now(TZ)


def shift_window(day):
    """(start, end) of the shift STARTING on `day`, or None on a day off.

    The end may land on the next date — a 12-hour day runs 16:00 -> 04:00.
    """
    spec = OVERRIDES.get(day, BASE.get(day.weekday()))
    if spec is None:
        return None
    hour, hours = spec
    start = datetime(day.year, day.month, day.day, hour, tzinfo=TZ)
    return start, start + timedelta(hours=hours)


def current_shift(now=None):
    """The shift `now` falls inside, or None. Looks back a day for overnights."""
    now = _now(now)
    for day in (now.date(), now.date() - timedelta(days=1)):
        window = shift_window(day)
        if window and window[0] <= now < window[1]:
            return window
    return None


def shift_just_ended(now=None, slack=SLACK_MINUTES):
    """The shift that ended in the last `slack` minutes, or None.

    Drives the end-of-shift pfp swap and the report, which cron fires at every
    possible finish time and each script then gates on.
    """
    now = _now(now)
    for day in (now.date(), now.date() - timedelta(days=1)):
        window = shift_window(day)
        if window and 0 <= (now - window[1]).total_seconds() / 60 < slack:
            return window
    return None


def charlotte_is_online(now=None):
    return current_shift(now) is not None


def vazira_is_online(now=None):
    now = _now(now)
    weekday = now.weekday()
    hour = now.hour
    if weekday in (6, 0) and 13 <= hour < 21:
        return True
    if weekday == 4 and hour >= 17:
        return True
    if weekday == 5 and (hour < 1 or hour >= 17):
        return True
    if weekday == 6 and hour < 1:
        return True
    return False
