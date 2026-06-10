from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Tashkent')


def _now(now):
    return now if now is not None else datetime.now(TZ)


def charlotte_is_online(now=None):
    now = _now(now)
    weekday = now.weekday()
    hour = now.hour
    if weekday == 0:
        return hour < 4
    if weekday == 1:
        return False
    if weekday == 2:
        return hour >= 16
    return hour < 4 or hour >= 16


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
