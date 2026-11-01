"""Instagram API with Unified Login — publish a video as a Reel, a Feed
video post, or a Story. No Facebook Page required, and nothing here shares
to Facebook (that needs a linked Page, which this setup doesn't have); see
instagram_auth.py for the one-time setup and login.

Calls go to graph.facebook.com, not graph.instagram.com — the System User
token this flow produces (see instagram_auth.py) only works against the
Facebook Graph API host, despite what the older Instagram API docs show.

IMPORTANT: Instagram's publishing API does not accept a direct file upload.
Meta's servers fetch the video themselves from a public URL you give them.
So before this script can run, the rendered .mp4 has to already be sitting
somewhere publicly reachable (an S3/R2 bucket, a Cloudflare/Netlify static
host, etc.) — put IG_VIDEO_PUBLIC_BASE_URL in .env to that location and this
script will build the full URL from the filename, or pass --video-url
directly if you're hosting it ad hoc.
"""
import os
import time

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("IG_BUSINESS_ACCOUNT_ID")
PUBLIC_BASE_URL = os.environ.get("IG_VIDEO_PUBLIC_BASE_URL", "")
GRAPH_BASE = "https://graph.facebook.com/v23.0"


def _headers():
    return {"Authorization": f"Bearer {ACCESS_TOKEN}"}


MEDIA_TYPES = ("REELS", "VIDEO", "STORIES")  # Reels, Feed video post, Story


def upload_video(file_path=None, caption="", video_url=None, media_type="REELS",
                  timeout_s=300, poll_interval_s=10):
    if media_type not in MEDIA_TYPES:
        raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
    if video_url is None:
        if not file_path or not PUBLIC_BASE_URL:
            raise ValueError("Pass --video-url, or set IG_VIDEO_PUBLIC_BASE_URL and a local file_path.")
        filename = os.path.basename(file_path)
        video_url = f"{PUBLIC_BASE_URL.rstrip('/')}/{filename}"

    data = {"media_type": media_type, "video_url": video_url}
    if media_type != "STORIES":
        # Stories don't carry a caption.
        data["caption"] = caption[:2200]

    create_resp = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media",
        headers=_headers(),
        data=data,
    )
    create_resp.raise_for_status()
    container_id = create_resp.json()["id"]

    status = _poll_container(container_id, timeout_s, poll_interval_s)
    if status != "FINISHED":
        raise RuntimeError(f"Instagram container {container_id} ended in status {status}")

    publish_resp = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media_publish",
        headers=_headers(),
        data={"creation_id": container_id},
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json()["id"]
    print(f"Instagram media id: {media_id}")
    return media_id


def _poll_container(container_id, timeout_s, interval_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            headers=_headers(),
            params={"fields": "status_code"},
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status in ("FINISHED", "ERROR", "EXPIRED"):
            return status
        time.sleep(interval_s)
    return "TIMED_OUT"


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Publish one video to Instagram.")
    p.add_argument("file", nargs="?", help="local filename (used to build the public URL)")
    p.add_argument("--video-url", help="public URL to the video, overrides IG_VIDEO_PUBLIC_BASE_URL")
    p.add_argument("--caption", default="")
    p.add_argument("--media-type", default="REELS", choices=MEDIA_TYPES,
                    help="REELS (default), VIDEO (feed post), or STORIES")
    args = p.parse_args()

    upload_video(file_path=args.file, caption=args.caption, video_url=args.video_url,
                 media_type=args.media_type)
