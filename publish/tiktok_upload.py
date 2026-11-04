"""TikTok Content Posting API — direct post of a local video file.

Run tiktok_auth.py once first to get an access token into .env.

privacy_level options: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY,
FOLLOWER_OF_CREATOR. Until your app passes TikTok's Content Posting API
audit, PUBLIC_TO_EVERYONE will be rejected or silently downgraded for
non-tester accounts — see the note in tiktok_auth.py.
"""
import os
import time

import requests
from dotenv import load_dotenv

from tiktok_auth import refresh_access_token

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN")
API_BASE = "https://open.tiktokapis.com/v2"


def _headers():
    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def upload_video(file_path, caption, privacy_level="SELF_ONLY",
                  disable_comment=False, disable_duet=False, disable_stitch=False):
    global ACCESS_TOKEN
    ACCESS_TOKEN = refresh_access_token() or ACCESS_TOKEN
    video_size = os.path.getsize(file_path)

    init_resp = requests.post(
        f"{API_BASE}/post/publish/video/init/",
        headers=_headers(),
        json={
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_comment": disable_comment,
                "disable_stitch": disable_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        },
    )
    init_resp.raise_for_status()
    init_data = init_resp.json()["data"]
    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]

    with open(file_path, "rb") as f:
        video_bytes = f.read()

    put_resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        data=video_bytes,
    )
    put_resp.raise_for_status()

    status = _poll_status(publish_id)
    print(f"TikTok publish_id {publish_id}: {status}")
    return publish_id, status


def _poll_status(publish_id, timeout_s=120, interval_s=5):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.post(
            f"{API_BASE}/post/publish/status/fetch/",
            headers=_headers(),
            json={"publish_id": publish_id},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data.get("status")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            return status
        time.sleep(interval_s)
    return "TIMED_OUT"


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Upload one video to TikTok via direct post.")
    p.add_argument("file")
    p.add_argument("--caption", required=True)
    p.add_argument("--privacy", default="SELF_ONLY",
                    choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY", "FOLLOWER_OF_CREATOR"])
    args = p.parse_args()

    upload_video(args.file, args.caption, privacy_level=args.privacy)
