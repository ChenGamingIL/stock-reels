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


def fetch_profile_picture(dest):
    """Download the account's profile picture (the logo) to `dest`."""
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    info = _check(requests.get(f"https://{HOST}/{VERSION}/{user_id}", params={
        "fields": "profile_picture_url", "access_token": token}, timeout=30))
    img = requests.get(info["profile_picture_url"], timeout=60)
    img.raise_for_status()
    with open(dest, "wb") as f:
        f.write(img.content)


def refresh_token():
    """Exchange the current long-lived token for a fresh 60-day one (Instagram Login only).

    The token must be at least 24 hours old and still valid.
    """
    resp = _check(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]}, timeout=30))
    return resp["access_token"], resp.get("expires_in")


def _gh_headers():
    return {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}


def _create_release(tag):
    repo = os.environ["GITHUB_REPOSITORY"]
    return _check(requests.post(f"https://api.github.com/repos/{repo}/releases", headers=_gh_headers(),
                                json={"tag_name": tag, "name": tag, "body": "Daily reel"}, timeout=30))["id"]


def _upload_asset(release_id, path, name, content_type):
    repo = os.environ["GITHUB_REPOSITORY"]
    with open(path, "rb") as f:
        asset = _check(requests.post(
            f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets",
            params={"name": name}, headers={**_gh_headers(), "Content-Type": content_type},
            data=f.read(), timeout=300))
    return asset["browser_download_url"]


def host_on_github(video_path, tag):
    """Attach the video to a GitHub release and return its public download URL."""
    return _upload_asset(_create_release(tag), video_path, "reel.mp4", "video/mp4")


def publish_reel(video_path, caption, tag="reel"):
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = f"https://{HOST}/{VERSION}"
    params = {"media_type": "REELS", "caption": caption, "share_to_feed": "true", "access_token": token}
    video_url = None  # only set when the video is hosted for the Instagram Login API

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

    return _wait_and_publish(base, user_id, token, cid), video_url


def publish_story(video_url=None, image_url=None):
    """Post an already-hosted 9:16 video or JPEG as a Story."""
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = f"https://{HOST}/{VERSION}"
    media = {"video_url": video_url} if video_url else {"image_url": image_url}
    cid = _check(requests.post(f"{base}/{user_id}/media", data={
        "media_type": "STORIES", **media, "access_token": token}, timeout=60))["id"]
    return _wait_and_publish(base, user_id, token, cid)


def publish_story_slides(png_paths, tag):
    """Post each slide as its own Story image, in order (Instagram needs JPEG)."""
    from PIL import Image

    release_id = _create_release(tag)
    ids = []
    for i, png in enumerate(png_paths):
        jpg = str(png).rsplit(".", 1)[0] + ".jpg"
        Image.open(png).convert("RGB").save(jpg, quality=92)
        url = _upload_asset(release_id, jpg, f"story_{i}.jpg", "image/jpeg")
        ids.append(publish_story(image_url=url))
    return ids


def _wait_and_publish(base, user_id, token, cid):
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
