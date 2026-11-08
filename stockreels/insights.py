"""Read-only reach report: account info, account insights and per-post insights.

python -m stockreels.insights  -> prints a summary and writes insights.json
"""
import datetime as dt
import json
import os

import requests

from stockreels.instagram import HOST, VERSION, list_media

REEL_METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
STORY_METRICS = ["views", "reach", "replies", "navigation"]
FEED_METRICS = ["views", "reach", "likes", "comments", "shares", "saved"]


def _get(path, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    r = requests.get(f"https://{HOST}/{VERSION}/{path}", params=params, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text[:300]}
    return r.ok, body


def _metrics(path, metrics, **extra):
    """Ask for each metric on its own, so one unsupported metric doesn't hide the rest."""
    out = {}
    for m in metrics:
        ok, body = _get(f"{path}/insights", metric=m, **extra)
        if not ok:
            out[m] = "ERR " + str(body.get("error", {}).get("message", body))[:120]
            continue
        for d in body.get("data", []):
            if "total_value" in d:
                out[d["name"]] = d["total_value"].get("value")
            elif d.get("values"):
                out[d["name"]] = d["values"][-1].get("value")
    return out


def account():
    uid = os.environ["IG_USER_ID"]
    _, info = _get(uid, fields="username,name,account_type,followers_count,follows_count,media_count,"
                               "biography,website,profile_picture_url")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    windows = {}
    for days in (7, 28):
        since = now - days * 86400
        windows[f"{days}d"] = _metrics(uid, ["reach", "views", "accounts_engaged", "total_interactions",
                                             "profile_views", "follows_and_unfollows", "likes",
                                             "shares", "saves", "comments"],
                                       period="day", metric_type="total_value", since=since, until=now)
    daily = {}
    ok, body = _get(f"{uid}/insights", metric="reach", period="day",
                    since=now - 28 * 86400, until=now)
    if ok:
        for d in body.get("data", []):
            daily = {v["end_time"][:10]: v["value"] for v in d.get("values", [])}
    ok, demo = _get(f"{uid}/insights", metric="follower_demographics", period="lifetime",
                    metric_type="total_value", breakdown="country", timeframe="this_month")
    return {"info": info, "insights": windows, "daily_reach": daily,
            "followers_by_country": demo if ok else str(demo)[:200]}


def posts(limit=200):
    out = []
    for m in list_media(limit):
        kind = m.get("media_product_type")
        metrics = REEL_METRICS if kind == "REELS" else FEED_METRICS
        _, extra = _get(m["id"], fields="like_count,comments_count,is_shared_to_feed")
        out.append({"id": m["id"], "time": m["timestamp"], "type": kind, "media_type": m.get("media_type"),
                    "link": m.get("permalink"), "title": (m.get("caption") or "").split("\n")[0][:80],
                    "caption": m.get("caption") or "", **_metrics(m["id"], metrics),
                    "shared_to_feed": extra.get("is_shared_to_feed")})
    return out


def stories():
    uid = os.environ["IG_USER_ID"]
    ok, body = _get(f"{uid}/stories", fields="id,timestamp,media_type")
    if not ok:
        return str(body)[:200]
    return [{"id": s["id"], "time": s["timestamp"], **_metrics(s["id"], STORY_METRICS)}
            for s in body.get("data", [])]


def main():
    acc = account()
    print("[account]", json.dumps(acc["info"], ensure_ascii=False))
    print("[insights]", json.dumps(acc["insights"], ensure_ascii=False))
    print("[daily reach]", json.dumps(acc["daily_reach"]))
    ps = posts()
    for p in ps:
        print(p["time"][:16], p["type"], "views", p.get("views"), "reach", p.get("reach"),
              "watch", p.get("ig_reels_avg_watch_time"), "|", p["title"][:50])
    st = stories()
    print("[stories live]", json.dumps(st, ensure_ascii=False)[:2000])
    report = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "account": acc, "posts": ps,
              "stories": st}
    with open("insights.json", "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


if __name__ == "__main__":
    main()
