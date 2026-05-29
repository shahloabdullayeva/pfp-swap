from datetime import datetime

from schedule import TZ, charlotte_is_online, vazira_is_online


# Reference week (Tashkent local time):
#   Mon 2025-01-06, Tue 01-07, Wed 01-08, Thu 01-09,
#   Fri 01-10, Sat 01-11, Sun 01-12
DAY = {
    'mon': 6, 'tue': 7, 'wed': 8, 'thu': 9,
    'fri': 10, 'sat': 11, 'sun': 12,
}


def t(day, hour, minute=0):
    return datetime(2025, 1, DAY[day], hour, minute, tzinfo=TZ)


CHARLOTTE_CASES = [
    # Mon: carryover from Sun until 04:00, offline rest of day
    ('mon', 0, True), ('mon', 3, True), ('mon', 4, False),
    ('mon', 15, False), ('mon', 23, False),
    # Tue: never online
    ('tue', 0, False), ('tue', 12, False), ('tue', 23, False),
    # Wed: online from 16:00, no carryover (Tue is offline)
    ('wed', 0, False), ('wed', 15, False), ('wed', 16, True), ('wed', 23, True),
    # Thu: carryover 0-3, offline 4-15, online 16+
    ('thu', 0, True), ('thu', 3, True), ('thu', 4, False),
    ('thu', 15, False), ('thu', 16, True), ('thu', 23, True),
    # Fri: same pattern as Thu
    ('fri', 0, True), ('fri', 3, True), ('fri', 4, False),
    ('fri', 15, False), ('fri', 16, True), ('fri', 23, True),
    # Sat: same pattern as Thu
    ('sat', 0, True), ('sat', 3, True), ('sat', 4, False),
    ('sat', 15, False), ('sat', 16, True), ('sat', 23, True),
    # Sun: same pattern as Thu
    ('sun', 0, True), ('sun', 3, True), ('sun', 4, False),
    ('sun', 15, False), ('sun', 16, True), ('sun', 23, True),
]

# Boundary minutes: ensure transitions happen exactly on the hour, not before/after.
CHARLOTTE_BOUNDARIES = [
    # Mon: offline at 04:00
    ('mon', 3, 59, True), ('mon', 4, 0, False),
    # Wed: online at 16:00 (no carryover from Tue)
    ('wed', 15, 59, False), ('wed', 16, 0, True),
    # Thu-Sun: offline at 04:00, online at 16:00
    ('thu', 3, 59, True), ('thu', 4, 0, False),
    ('thu', 15, 59, False), ('thu', 16, 0, True),
    ('fri', 3, 59, True), ('fri', 4, 0, False),
    ('fri', 15, 59, False), ('fri', 16, 0, True),
    ('sat', 3, 59, True), ('sat', 4, 0, False),
    ('sat', 15, 59, False), ('sat', 16, 0, True),
    ('sun', 3, 59, True), ('sun', 4, 0, False),
    ('sun', 15, 59, False), ('sun', 16, 0, True),
]

VAZIRA_CASES = [
    # Sun: online 00:00-00:59 (carryover from Sat), offline 01:00-12:59,
    #      online 13:00-20:59, offline 21:00+
    ('sun', 0, True), ('sun', 1, False), ('sun', 12, False),
    ('sun', 13, True), ('sun', 20, True), ('sun', 21, False),
    ('sun', 23, False),
    # Mon: offline 00:00-12:59, online 13:00-20:59, offline 21:00+
    ('mon', 0, False), ('mon', 12, False), ('mon', 13, True),
    ('mon', 20, True), ('mon', 21, False),
    # Tue/Wed/Thu: never online
    ('tue', 12, False), ('wed', 12, False), ('thu', 12, False),
    # Fri: online from 17:00
    ('fri', 0, False), ('fri', 16, False), ('fri', 17, True),
    ('fri', 23, True),
    # Sat: online 00:00-00:59 (carryover from Fri), offline 01:00-16:59,
    #      online 17:00+
    ('sat', 0, True), ('sat', 1, False), ('sat', 16, False),
    ('sat', 17, True), ('sat', 23, True),
]

VAZIRA_BOUNDARIES = [
    ('sun', 0, 59, True), ('sun', 1, 0, False),
    ('sun', 12, 59, False), ('sun', 13, 0, True),
    ('sun', 20, 59, True), ('sun', 21, 0, False),
    ('mon', 12, 59, False), ('mon', 13, 0, True),
    ('mon', 20, 59, True), ('mon', 21, 0, False),
    ('fri', 16, 59, False), ('fri', 17, 0, True),
    ('sat', 0, 59, True), ('sat', 1, 0, False),
    ('sat', 16, 59, False), ('sat', 17, 0, True),
]


def run():
    failures = []

    for day, hour, expected in CHARLOTTE_CASES:
        got = charlotte_is_online(t(day, hour))
        if got != expected:
            failures.append(f"charlotte {day} {hour:02d}:00 expected {expected}, got {got}")

    for day, hour, minute, expected in CHARLOTTE_BOUNDARIES:
        got = charlotte_is_online(t(day, hour, minute))
        if got != expected:
            failures.append(f"charlotte {day} {hour:02d}:{minute:02d} expected {expected}, got {got}")

    for day, hour, expected in VAZIRA_CASES:
        got = vazira_is_online(t(day, hour))
        if got != expected:
            failures.append(f"vazira {day} {hour:02d}:00 expected {expected}, got {got}")

    for day, hour, minute, expected in VAZIRA_BOUNDARIES:
        got = vazira_is_online(t(day, hour, minute))
        if got != expected:
            failures.append(f"vazira {day} {hour:02d}:{minute:02d} expected {expected}, got {got}")

    total = (
        len(CHARLOTTE_CASES) + len(CHARLOTTE_BOUNDARIES)
        + len(VAZIRA_CASES) + len(VAZIRA_BOUNDARIES)
    )

    if failures:
        print(f"FAILED {len(failures)}/{total}")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)

    print(f"OK {total} cases passed")


if __name__ == '__main__':
    run()
