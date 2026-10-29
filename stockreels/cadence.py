"""Posting days: the whole lineup goes out once every few days instead of every day (Chen, 2026-10-29).

A posting day comes EVERY days after the last one; one that would land on Saturday moves to Sunday,
since Shabbat is quiet anyway. With EVERY = 3 from Thursday 29.10 that settles on Sunday and Wednesday.
The episode counters move per post, so a day off skips no episode, lesson or question.
The Shabbat Shalom and good-week Stories are not part of this and keep their own times.
"""
import datetime as dt

EVERY = 3
ANCHOR = dt.date(2026, 10, 29)  # a posting day
DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def post_days(until):
    day = ANCHOR
    while day <= until:
        yield day
        day += dt.timedelta(days=EVERY)
        if day.weekday() == 5:
            day += dt.timedelta(days=1)


def is_post_day(day):
    if day < ANCHOR:
        return True
    return day in set(post_days(day))


def next_post_day(after):
    day = after + dt.timedelta(days=1)
    while not is_post_day(day):
        day += dt.timedelta(days=1)
    return day


def next_label(today=None):
    """When the next posting day is, for an outro: "מחר" or "ביום ראשון"."""
    from zoneinfo import ZoneInfo
    today = today or dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    day = next_post_day(today)
    return "מחר" if day == today + dt.timedelta(days=1) else f"ביום {DAYS_HE[day.weekday()]}"


if __name__ == "__main__":
    print([f"{d:%a %d.%m}" for d in post_days(ANCHOR + dt.timedelta(days=30))])
