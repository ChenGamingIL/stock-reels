"""Publish a Reel through the Instagram Graph API using resumable upload.

Resumable upload sends the MP4 bytes straight to Meta, so the video does not
need to be hosted on a public URL first.

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


def publish_reel(video_path, caption):
    user_id, token = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    base = f"https://{HOST}/{VERSION}"

    container = _check(requests.post(f"{base}/{user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption,
        "share_to_feed": "true", "access_token": token,
    }, timeout=60))
    cid = container["id"]

    data = open(video_path, "rb").read()
    _check(requests.post(f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{cid}", headers={
        "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data)),
    }, data=data, timeout=300))

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
