"""Named shows with episode numbers, so the feed reads as a series."""
import json
from pathlib import Path

EPISODES_FILE = Path(__file__).resolve().parent.parent / "episodes.json"

SHOWS = {
    "hot": "המניה החמה",
    "premarket": "לפני הפעמון",
    "lesson": "שוק ההון מאפס",
    "didyouknow": "הידעת?",
    "close": "סיכום היום",
}


def _load():
    return json.loads(EPISODES_FILE.read_text()) if EPISODES_FILE.exists() else {}


def next_episode(show):
    """The number this run's episode will carry (not saved until it's posted)."""
    return _load().get(show, 0) + 1


def mark_posted(show, n):
    eps = _load()
    eps[show] = max(eps.get(show, 0), n)
    EPISODES_FILE.write_text(json.dumps(eps, indent=2, ensure_ascii=False))


def kicker(show, n):
    return f"{SHOWS[show]} · פרק {n}"
