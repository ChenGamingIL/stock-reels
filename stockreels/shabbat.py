"""Shabbat and Yom Tov: no posting from candle lighting to havdalah (Tel Aviv times, from Hebcal)."""
import datetime as dt
from zoneinfo import ZoneInfo

import requests

IL = ZoneInfo("Asia/Jerusalem")
HEBCAL = "https://www.hebcal.com/shabbat"
TEL_AVIV = 293397  # GeoNames id


def week_times(now=None):
    """Upcoming candle-lighting/havdalah windows plus this week's parasha, from Hebcal."""
    now = now or dt.datetime.now(IL)
    # pass the date explicitly: without it Hebcal's cache sometimes answers for last week
    resp = requests.get(HEBCAL, params={"cfg": "json", "geonameid": TEL_AVIV, "M": "on", "lg": "he",
                                        "gy": now.year, "gm": now.month, "gd": now.day}, timeout=20)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    print(f"[shabbat] hebcal: {[(i.get('category'), i.get('date')) for i in items]}")
    windows, start, parasha = [], None, None
    for it in sorted(items, key=lambda i: i["date"]):
        t = dt.datetime.fromisoformat(it["date"])
        if it["category"] == "candles" and start is None:
            start = t
        elif it["category"] == "havdalah" and start is not None:
            windows.append((start, t))
            start = None
        elif it["category"] == "parashat":
            parasha = it.get("hebrew") or it.get("title")
    return windows, parasha


def _fallback_window(now):
    """Without Hebcal, stay quiet on a safe superset: Friday 15:45 to Saturday 20:45."""
    friday = now.date() - dt.timedelta(days=(now.weekday() - 4) % 7)
    return (dt.datetime.combine(friday, dt.time(15, 45), IL),
            dt.datetime.combine(friday + dt.timedelta(days=1), dt.time(20, 45), IL))


def is_quiet(now=None):
    """True between candle lighting and havdalah (Shabbat or Yom Tov)."""
    now = now or dt.datetime.now(IL)
    try:
        windows, _ = week_times(now)
    except Exception as e:
        print(f"[shabbat] Hebcal unavailable ({e.__class__.__name__}: {e})")
        windows = []
    if not windows:  # never risk posting on Shabbat because of a parsing problem
        print("[shabbat] no times from Hebcal, using the fallback window")
        windows = [_fallback_window(now)]
    return any(a <= now <= b for a, b in windows)


def candle_lighting(now=None):
    """(candle lighting, havdalah, parasha) for the coming Shabbat, or None."""
    now = now or dt.datetime.now(IL)
    try:
        windows, parasha = week_times(now)
    except Exception as e:
        print(f"[shabbat] Hebcal unavailable ({e.__class__.__name__}: {e})")
        return None
    upcoming = [w for w in windows if w[1] >= now]
    return (*upcoming[0], parasha) if upcoming else None
