from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Tashkent')


def _now(now):
    return now if now is not None else datetime.now(TZ)


def charlotte_is_online(now=None):
    now = _now(now)
    weekday = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    hour = now.hour
    if weekday == 0:   # Mon: carryover from Sun until 04:00, then offline
        return hour < 4
    if weekday == 1:   # Tue: always offline
        return False
    if weekday == 2:   # Wed: online from 16:00, no carryover (Tue is offline)
        return hour >= 16
    return hour < 4 or hour >= 16  # Thu-Sun: carryover 0-3, offline 4-15, online 16+


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
