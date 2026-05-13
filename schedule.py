from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Tashkent')


def _now(now):
    return now if now is not None else datetime.now(TZ)


def charlotte_is_online(now=None):
    now = _now(now)
    weekday = now.weekday()
    hour = now.hour
    if weekday == 2 and hour >= 17:
        return True
    if weekday == 3 and (hour < 1 or hour >= 16):
        return True
    if weekday == 4 and (hour < 1 or hour >= 17):
        return True
    if weekday == 5 and (hour < 1 or hour >= 16):
        return True
    if weekday == 6 and (hour < 1 or hour >= 16):
        return True
    if weekday == 0 and hour < 1:
        return True
    return False


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
