from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Tashkent')

BASE = {2: (16, 8), 3: (16, 8), 4: (16, 8), 5: (16, 8), 6: (16, 8)}

OVERRIDES = {
    date(2026, 8, 29): (16, 12),
    date(2026, 8, 30): (21, 12),
}

SLACK_MINUTES = 30


def _now(now):
    return now if now is not None else datetime.now(TZ)


def shift_window(day):
    spec = OVERRIDES.get(day, BASE.get(day.weekday()))
    if spec is None:
        return None
    hour, hours = spec
    start = datetime(day.year, day.month, day.day, hour, tzinfo=TZ)
    return start, start + timedelta(hours=hours)


def current_shift(now=None):
    now = _now(now)
    for day in (now.date(), now.date() - timedelta(days=1)):
        window = shift_window(day)
        if window and window[0] <= now < window[1]:
            return window
    return None


def shift_just_ended(now=None, slack=SLACK_MINUTES):
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
