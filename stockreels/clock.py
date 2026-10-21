"""The posting clock: starts each show on time instead of trusting GitHub's cron.

GitHub starts scheduled runs late or not at all when it is busy (on 2026-10-19 no cron ran
from 20:07 UTC until past noon), so clock.yml stays alive for up to ~5.5 hours, sleeps until
each slot, dispatches the show's workflow, and before it ends dispatches the next clock run.
slots.json remembers which slot was already started so a restarted clock never repeats one.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

IL = ZoneInfo("Asia/Jerusalem")
NY = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "slots.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "ChenGamingIL/stock-reels")

# (clock, time, show, hours it may still go out late, weekdays or None for every day).
# Market shows follow New York, so they keep their place around the bell when only one country changed clocks.
SLOTS = [(IL, (8, 0), "hot", 6, None), (IL, (12, 30), "didyouknow", 4, None), (IL, (20, 0), "lesson", 3, None),
         (NY, (8, 30), "premarket", 0.9, range(5)), (NY, (9, 45), "open", 2, range(5)),
         (NY, (16, 15), "close", 3, range(5))]
SHABBAT_GRACE = 25 / 60  # shabbat.story_due accepts up to 8 minutes before candle lighting
WEEK_GRACE = 40 / 60  # shabbat.week_due accepts up to 60 minutes after havdalah
_hebcal = []


def slots(now):
    """(due, show, grace hours, key) for yesterday, today and tomorrow, plus the next Shabbat/Yom Tov Story."""
    out = []
    for tz, (h, m), show, grace, days in SLOTS:
        local = now.astimezone(tz)
        for d in (-1, 0, 1):
            day = local.date() + dt.timedelta(days=d)
            if days is None or day.weekday() in days:
                out.append((dt.datetime.combine(day, dt.time(h, m), tz), show, grace, day.isoformat()))
    try:
        from stockreels import shabbat
        if not _hebcal or now - _hebcal[0] > dt.timedelta(hours=1):  # the loop wakes every 5 minutes
            _hebcal[:] = [now, shabbat.recent_windows(now.astimezone(IL))]
        for candles, havdalah in _hebcal[1]:
            out.append((candles - shabbat.STORY_BEFORE, "shabbat", SHABBAT_GRACE, candles.date().isoformat()))
            if havdalah.weekday() == 5:  # a good-week Story after Shabbat (not after a Yom Tov that ends midweek)
                out.append((havdalah + shabbat.WEEK_AFTER, "week", WEEK_GRACE, havdalah.date().isoformat()))
    except Exception as e:  # shabbat.yml's own 10-minute check still covers it
        print(f"[clock] no Hebcal times ({e.__class__.__name__}: {e})")
    return sorted(out)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(state, show):
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    if os.environ.get("CLOCK_DRY"):
        return
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, check=False)
    git("add", "slots.json")
    git("commit", "-q", "-m", f"clock: {show} {state[show]}")
    for _ in range(3):
        if git("pull", "--rebase", "-q", "origin", "main").returncode == 0 and git("push", "-q").returncode == 0:
            return
        time.sleep(5)


def dispatch(workflow, inputs):
    print(f"[clock] dispatch {workflow} {inputs}", flush=True)
    if os.environ.get("CLOCK_DRY"):
        return True
    args = ["gh", "api", "-X", "POST", f"repos/{REPO}/actions/workflows/{workflow}/dispatches", "-f", "ref=main"]
    for k, v in inputs.items():
        args += ["-f", f"inputs[{k}]={v}"]
    for attempt in range(3):
        if subprocess.run(args).returncode == 0:
            return True
        time.sleep(10 * (attempt + 1))
    return False


def workflow_of(show):
    return "shabbat.yml" if show in ("shabbat", "week") else "daily-reel.yml"


def fire(show):
    if show in ("shabbat", "week"):
        return dispatch("shabbat.yml", {"dry_run": "false", "show": show})
    return dispatch("daily-reel.yml", {"show": show})


def gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout else {}


def find_run(show, since):
    """The id of the run a dispatch made: the newest dispatched run of that show since `since`
    (daily-reel.yml names each run after its show)."""
    runs = gh_json(f"repos/{REPO}/actions/workflows/{workflow_of(show)}/runs?event=workflow_dispatch&per_page=20")
    ids = [r["id"] for r in runs.get("workflow_runs", [])
           if dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since
           and r.get("display_title", "").split(" ")[0] == show]
    return max(ids) if ids else None


def alert(show, key, url):
    """Open an issue on the repo: GitHub emails the owner, so a missed post never goes unnoticed."""
    title = f"לא עלה: {show} {key}"
    body = (f"הריצה של {show} ל-{key} נכשלה פעמיים, אז הפוסט לא עלה.\n\n{url}\n\n"
            "The clock retried once; look at the run log for the error.")
    print(f"[clock] ALERT {title} {url}", flush=True)
    if not os.environ.get("CLOCK_DRY"):
        subprocess.run(["gh", "api", "-X", "POST", f"repos/{REPO}/issues", "-f", f"title={title}", "-f", f"body={body}"])


def check(watch, state):
    """Follow each started run: retry a failed one once, then raise an alert."""
    for w in list(watch):
        if w["run"] is None:
            w["run"] = find_run(w["show"], w["since"])
            if w["run"] is None:
                if dt.datetime.now(dt.timezone.utc) - w["since"] > dt.timedelta(minutes=20):
                    alert(w["show"], w["key"], "(no run started)")
                    watch.remove(w)
                continue
        run = gh_json(f"repos/{REPO}/actions/runs/{w['run']}")
        if run.get("status") != "completed":
            continue
        watch.remove(w)
        print(f"[clock] {w['show']} {w['key']}: {run.get('conclusion')} {run.get('html_url')}", flush=True)
        if run.get("conclusion") == "success":
            continue
        if w["tries"] < 2:
            since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
            if fire(w["show"]):
                watch.append({**w, "run": None, "since": since, "tries": w["tries"] + 1})
                continue
        alert(w["show"], w["key"], run.get("html_url", ""))


def run(budget=dt.timedelta(hours=5, minutes=30)):
    start = dt.datetime.now(dt.timezone.utc)
    state, watch = load(), []
    while True:
        check(watch, state)
        now = dt.datetime.now(dt.timezone.utc)
        plan = slots(now)
        for due, show, grace, key in plan:  # anything due and not started yet, oldest first
            late = (now - due).total_seconds() / 3600
            if 0 <= late <= grace and state.get(show) != key:
                since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
                if fire(show):
                    watch.append({"show": show, "key": key, "since": since, "run": None, "tries": 1})
                    state[show] = key
                    save(state, show)
                    time.sleep(90)  # let one show's run start before the next one
        now = dt.datetime.now(dt.timezone.utc)
        upcoming = [(due, show) for due, show, _, key in plan if due > now and state.get(show) != key]
        due, show = upcoming[0] if upcoming else (now + dt.timedelta(days=1), "nothing")
        if due > start + budget and not watch:
            print(f"[clock] next is {show} at {due.astimezone(IL):%a %H:%M} Israel, past this run's budget")
            return
        if now > start + budget + dt.timedelta(minutes=10):
            print("[clock] out of time; the next clock picks up from here")
            return
        print(f"[clock] next: {show} at {due.astimezone(IL):%a %d.%m %H:%M} Israel; watching {len(watch)} run(s)", flush=True)
        time.sleep(min(300, max(0, (due - now).total_seconds()) + 5))


if __name__ == "__main__":
    if "--plan" in sys.argv:
        state = load()
        for due, show, grace, key in slots(dt.datetime.now(dt.timezone.utc)):
            print(f"{due.astimezone(IL):%a %d.%m %H:%M} Israel  {show:<10} grace {grace:.1f}h  "
                  f"{'started' if state.get(show) == key else ''}")
    else:
        run()
