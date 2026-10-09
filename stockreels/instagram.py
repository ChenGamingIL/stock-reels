"""Publish a Reel through the Instagram Graph API using resumable upload.

With Facebook Login (graph.facebook.com) the MP4 is sent with resumable upload.
The Instagram Login API (graph.instagram.com) only accepts a public video_url,
so the video is first attached to a GitHub release in this (public) repo.

Needs:
  IG_USER_ID       Instagram professional (business/creator) account id
  IG_ACCESS_TOKEN  long-lived token with instagram_content_publish permission
Optional:
  GRAPH_HOST       graph.instagram.com (Instagram Login, default) or graph.facebook.com (Facebook Login)
  GRAPH_VERSION    default v21.0
"""
import os
import time

import requests

HOST = os.environ.get("GRAPH_HOST") or "graph.instagram.com"
VERSION = os.environ.get("GRAPH_VERSION", "v21.0")


def _check(resp):
    if not resp.ok:
        raise RuntimeError(f"Instagram API {resp.status_code}: {resp.text}")
    return resp.json()


def check_connection():
    """Read the account's username and confirm the token works, without posting."""
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    info = _check(requests.get(f"https://{HOST}/{VERSION}/{user_id}", params={
        "fields": "username,account_type", "access_token": token}, timeout=30))
    return info


def refresh_token():
    """Exchange the current long-lived token for a fresh 60-day one (Instagram Login only).

    The token must be at least 24 hours old and still valid.
    """
    resp = _check(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=30))
    return resp["access_token"], resp.get("expires_in")


def host_on_github(video_path, tag):
    """Attach the video to a GitHub release and return its public download URL."""
    repo, gh = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    headers = {"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json"}
    release = _check(requests.post(f"https://api.github.com/repos/{repo}/releases", headers=headers,
                                   json={"tag_name": tag, "name": tag, "body": "Daily reel"}, timeout=30))
    with open(video_path, "rb") as f:
        asset = _check(requests.post(
            f"https://uploads.github.com/repos/{repo}/releases/{release['id']}/assets",
            params={"name": "reel.mp4"}, headers={**headers, "Content-Type": "video/mp4"},
            data=f.read(), timeout=300))
    return asset["browser_download_url"]


def publish_reel(video_path, caption, tag="reel"):
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = f"https://{HOST}/{VERSION}"
    params = {"media_type": "REELS", "caption": caption, "share_to_feed": "true", "access_token": token}

    if HOST == "graph.facebook.com":
        cid = _check(requests.post(f"{base}/{user_id}/media", data={**params, "upload_type": "resumable"},
                                   timeout=60))["id"]
        data = open(video_path, "rb").read()
        _check(requests.post(f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{cid}", headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data)),
        }, data=data, timeout=300))
    else:
        video_url = host_on_github(video_path, tag)
        print(f"[upload] video hosted at {video_url}")
        cid = _check(requests.post(f"{base}/{user_id}/media", data={**params, "video_url": video_url},
                                   timeout=60))["id"]

    for _ in range(60):  # processing usually takes 30s to a few minutes
        status = _check(requests.get(f"{base}/{cid}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {status}")
        time.sleep(10)
    else:
        raise TimeoutError("Instagram did not finish processing the video in 10 minutes")

    published = _check(requests.post(f"{base}/{user_id}/media_publish", data={
        "creation_id": cid, "access_token": token}, timeout=60))
    return published["id"]
