"""One-off experiments Chen approved on the team's HQ page. Each one is limited to its dates and then the
normal lineup comes back by itself, so nothing here needs to be reverted by hand.

- x-2026-47-hot-evening: on Wednesday 18.11 only, the hot stock goes out at 18:00 and "שאלה של היום" at
  08:00 (judged in the 23.11 report: hot views and reach at 48h vs the last 4 hot Reels).
- x-2026-47-share-ask: on the question episodes of 18.11 and 19.11, the outro line and the caption's first
  line ask to send the Reel to one specific friend (judged 23.11 and 30.11: shares + saves per episode).
"""
import datetime as dt
from zoneinfo import ZoneInfo

IL = ZoneInfo("Asia/Jerusalem")

# date -> {show: (hour, minute)}: Israel-time slots that replace the usual one on that day.
SLOT_SWAPS = {dt.date(2026, 11, 18): {"hot": (18, 0), "question": (8, 0)}}

SHARE_ASK_DATES = {dt.date(2026, 11, 18), dt.date(2026, 11, 19)}
SHARE_ASK = "שלחו את זה לחבר שתמיד שואל אתכם על מניות 📤"


def today():
    return dt.datetime.now(IL).date()


def slot(show, day, default):
    """The (hour, minute) `show` goes out at on `day`."""
    return SLOT_SWAPS.get(day, {}).get(show, default)


def slot_label(show, default, day=None):
    """"HH:MM" for a caption, e.g. "08:00", after any swap for that day."""
    h, m = slot(show, day or today(), default)
    return f"{h:02d}:{m:02d}"


def share_ask(day=None):
    return (day or today()) in SHARE_ASK_DATES
