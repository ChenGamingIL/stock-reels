"""Which shows go out on which day: two Reels a day instead of the whole lineup every third day.

Chen approved this on 2026-11-16 (HQ decision d-cadence). Six Reels on one day competed with each other and
daily reach fell from 30-70 to 2-20 accounts after the every-3-days lineup started (Insights, 6.11), so now
every day but Shabbat gets one daytime Reel and one evening Reel, rotating the series through the week:

    Sunday     hot 08:00          + lesson 20:00
    Monday     premarket 15:30    + question 18:00   (+ open and close Stories)
    Tuesday    didyouknow 12:30   + lesson 20:00
    Wednesday  hot 08:00          + question 18:00
    Thursday   premarket 15:30    + question 18:00   (+ open and close Stories)
    Friday     didyouknow 12:30   (one Reel: the evening is Shabbat)
    Saturday   nothing (Shabbat)

A week: question 3, hot 2, premarket 2, didyouknow 2, lesson 2. The episode counters move per post, so a
show that skips a day skips no episode, lesson or question. The open/close Stories go with the pre-market
show, so a day never has more Stories than a posting day had before. The Shabbat Shalom and good-week
Stories are not part of this and keep their own times (stockreels/clock.py, stockreels/shabbat.py).
Friday has nothing after 12:30, so nothing lands near candle lighting; Friday's close (23:15) never runs.
"""
import datetime as dt

# Python weekday (Monday 0 ... Sunday 6) -> the shows that go out that day.
LINEUP = {
    6: ("hot", "lesson"),
    0: ("premarket", "question", "open", "close"),
    1: ("didyouknow", "lesson"),
    2: ("hot", "question"),
    3: ("premarket", "question", "open", "close"),
    4: ("didyouknow",),
    5: (),
}
DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def shows_on(day):
    return LINEUP[day.weekday()]


def posts(show, day):
    """Does `show` go out on `day`?"""
    return show in shows_on(day)


def is_post_day(day):
    return bool(shows_on(day))


def next_post_day(after, show=None):
    """The first day after `after` with `show` on it (or with anything on it, without a show)."""
    day = after + dt.timedelta(days=1)
    while not (posts(show, day) if show else is_post_day(day)):
        day += dt.timedelta(days=1)
    return day


def next_label(show=None, today=None):
    """When `show` goes out next, for an outro: "מחר" or "ביום ראשון"."""
    from zoneinfo import ZoneInfo
    today = today or dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    day = next_post_day(today, show)
    return "מחר" if day == today + dt.timedelta(days=1) else f"ביום {DAYS_HE[day.weekday()]}"


if __name__ == "__main__":
    start = dt.date.today()
    for i in range(14):
        d = start + dt.timedelta(days=i)
        print(f"{d:%a %d.%m}  {', '.join(shows_on(d)) or '-'}")
