"""Unified CLI: post one or more shorts to YouTube, TikTok, and/or Instagram
from posting_checklist.json.

Examples:
  python publish_all.py characters --platforms youtube
  python publish_all.py characters --platforms youtube,tiktok,instagram
  python publish_all.py ultimate_edition_bonuses leonida_new_drop --platforms youtube,tiktok,instagram
  python publish_all.py --list

Each platform's auth/setup is handled by its own module (see the docstrings
in youtube_upload.py, tiktok_auth.py + tiktok_upload.py, and
instagram_upload.py) — run those setup steps once before using this.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(os.path.dirname(HERE), "output")
CHECKLIST_FILE = os.path.join(HERE, "posting_checklist.json")
MEDIA_LOG_FILE = os.path.join(HERE, "media_log.json")
YOUTUBE_LOG_FILE = os.path.join(HERE, "youtube_log.json")
TIKTOK_LOG_FILE = os.path.join(HERE, "tiktok_log.json")
MEDIA_REPO = os.environ.get(
    "MEDIA_REPO_DIR", os.path.join(os.path.dirname(os.path.dirname(HERE)), "my-media-repo"))
MEDIA_PUBLIC_BASE_URL = os.environ.get("IG_VIDEO_PUBLIC_BASE_URL", "").rstrip("/")
PIPELINE_DIR = os.path.join(os.path.dirname(HERE), "pipeline")


def host_on_media_repo(file_path, filename, poll_timeout_s=120, poll_interval_s=8):
    """Copy a rendered short into the media-hosting repo (MEDIA_REPO_DIR) and push it, so
    Instagram's fetcher (which needs a public URL, not a direct upload) can
    reach it. Polls the public URL until GitHub Pages has actually deployed
    it - the push alone doesn't mean the URL is live yet."""
    dest = os.path.join(MEDIA_REPO, filename)
    with open(file_path, "rb") as src, open(dest, "wb") as out:
        out.write(src.read())
    subprocess.run(["git", "add", filename], check=True, cwd=MEDIA_REPO)
    status = subprocess.run(["git", "status", "--porcelain", "--", filename],
                            check=True, cwd=MEDIA_REPO, capture_output=True, text=True)
    if not status.stdout.strip():
        print(f"  {filename} already hosted and unchanged, skipping push.")
        return
    subprocess.run(["git", "commit", "--quiet", "-m", f"Add {filename} for Instagram hosting"],
                   check=True, cwd=MEDIA_REPO)
    subprocess.run(["git", "push", "--quiet"], check=True, cwd=MEDIA_REPO)

    if not MEDIA_PUBLIC_BASE_URL:
        return
    url = f"{MEDIA_PUBLIC_BASE_URL}/{filename}"
    deadline = time.time() + poll_timeout_s
    while time.time() < deadline:
        if requests.head(url, timeout=10).status_code == 200:
            print(f"  Live at {url}")
            return
        time.sleep(poll_interval_s)
    print(f"  WARNING: {url} isn't live yet after {poll_timeout_s}s - Instagram's fetch may fail.")


def run_prune():
    """Check media_log.json for anything past its hosting window and remove
    it from the media repo - run right after a post instead of on a timer."""
    print("\n--- Checking for media to prune ---")
    subprocess.run([sys.executable, os.path.join(HERE, "prune_media.py")], check=True)


def log_instagram_post(video_id, filename, media_id):
    """Record when a video was fetched by Instagram, so prune_media.py knows
    when it's safe to delete the public copy from the media-hosting repo."""
    log = []
    if os.path.exists(MEDIA_LOG_FILE):
        with open(MEDIA_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    log.append({
        "id": video_id,
        "file": filename,
        "media_id": media_id,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "pruned": False,
    })
    with open(MEDIA_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_youtube_log():
    if os.path.exists(YOUTUBE_LOG_FILE):
        with open(YOUTUBE_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def find_youtube_upload(log, video_id):
    for entry in log:
        if entry["id"] == video_id:
            return entry
    return None


def log_youtube_post(video_id, filename, yt_video_id, url):
    """Record a successful YouTube upload so re-running publish_all.py for
    the same video (e.g. after TikTok/Instagram failed) doesn't re-upload
    it - checked before every YouTube upload attempt."""
    log = load_youtube_log()
    log.append({
        "id": video_id,
        "file": filename,
        "video_id": yt_video_id,
        "url": url,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    })
    with open(YOUTUBE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_tiktok_log():
    if os.path.exists(TIKTOK_LOG_FILE):
        with open(TIKTOK_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def find_tiktok_upload(log, video_id):
    for entry in log:
        if entry["id"] == video_id:
            return entry
    return None


def log_tiktok_post(video_id, filename, publish_id, status):
    """Record a TikTok publish attempt so re-running publish_all.py for the
    same video doesn't post it twice - checked before every TikTok upload
    attempt, mirroring the existing YouTube dedup log."""
    log = load_tiktok_log()
    log.append({
        "id": video_id,
        "file": filename,
        "publish_id": publish_id,
        "status": status,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    })
    with open(TIKTOK_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_short_config(video_id):
    """Locate the shorts.json entry for a video id - same SHORTS_CONFIG
    convention as make_shorts.py, so this points at whatever config you
    actually rendered the video from."""
    path = os.environ.get("SHORTS_CONFIG", os.path.join(PIPELINE_DIR, "shorts.json"))
    if not os.path.isabs(path):
        path = os.path.join(PIPELINE_DIR, path)
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    short = next((s for s in cfg.get("shorts", []) if s["id"] == video_id), None)
    return (cfg, short) if short else (None, None)


def compute_cover_offset_ms(video_id):
    """Midpoint (ms) of the first time the logo overlay (if any) is on
    screen, for use as TikTok's/Instagram's cover-frame offset - without
    this, both default to frame 0, which misses any on-screen element that
    isn't visible right at t=0. Returns None (let the platform use its own
    default frame) if the short has no VO, no logo overlay configured, or
    its voiceover WAVs haven't been generated yet."""
    cfg, short = find_short_config(video_id)
    if not short or not short.get("vo"):
        return None
    if PIPELINE_DIR not in sys.path:
        sys.path.insert(0, PIPELINE_DIR)
    import re
    import make_shorts as ms
    pattern = re.compile(short.get("logo_pattern", cfg.get("logo_pattern", ms.DEFAULT_LOGO_PATTERN)),
                          re.IGNORECASE)
    try:
        segments = ms.layout_segments(short)
    except SystemExit:
        return None
    wins = ms.logo_windows(segments, pattern)
    if not wins:
        return None
    a, b = wins[0]
    return int((a + b) / 2 * 1000)


def extract_thumbnail_frame(file_path, offset_ms):
    """TikTok/Instagram take a timestamp and pick the frame themselves;
    YouTube's thumbnails.set needs an actual image file, so pull one frame
    with ffmpeg. Caller is responsible for deleting the returned temp file."""
    fd, out_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(offset_ms / 1000), "-i", file_path,
         "-frames:v", "1", "-update", "1", "-q:v", "2", out_path],
        check=True, capture_output=True,
    )
    return out_path


def load_checklist():
    with open(CHECKLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def find_video(checklist, video_id):
    for v in checklist["videos"]:
        if v["id"] == video_id:
            return v
    raise KeyError(f"No video with id '{video_id}' in {CHECKLIST_FILE}")


def build_youtube_args(defaults, video):
    yt = video["youtube"]
    hashtag_line = " ".join(yt.get("hashtags", defaults["youtube_hashtags"]))
    credit = defaults.get(f"credit_{yt.get('credit')}", defaults["credit_footage"])
    description = f"{yt['description']}\n\n{credit}\n\n{hashtag_line}"
    tags = defaults["youtube_tags"]
    return yt["title"], description, tags


def build_social_caption(core_tags, platform_block):
    tags = " ".join(core_tags + platform_block.get("theme_tags", []))
    return f"{platform_block['caption']}\n\n{tags}"


def publish_one(video, checklist, args):
    """Post a single video to the requested platforms. Raises on failure -
    the caller decides whether that should stop the batch."""
    file_path = os.path.join(OUTPUT_DIR, video["file"])
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    if "note" in video:
        print(f"NOTE: {video['note']}")
        confirm = input(f"Continue posting {video['id']} anyway? [y/N] ").strip().lower()
        if confirm != "y":
            print(f"  skipped {video['id']}.")
            return

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    defaults = checklist["defaults"]

    if "youtube" in platforms:
        print(f"\n--- YouTube: {video['id']} ---")
        existing = find_youtube_upload(load_youtube_log(), video["id"])
        if existing and not args.force_youtube:
            print(f"  already uploaded at {existing['url']} on {existing['posted_at']} "
                  f"- skipping (use --force-youtube to re-upload anyway).")
        else:
            import youtube_upload
            title, description, tags = build_youtube_args(defaults, video)
            thumb_offset_ms = compute_cover_offset_ms(video["id"])
            thumbnail_path = None
            if thumb_offset_ms is not None:
                print(f"  using cover frame at {thumb_offset_ms}ms (GTA 6 logo window)")
                thumbnail_path = extract_thumbnail_frame(file_path, thumb_offset_ms)
            try:
                yt_video_id, url = youtube_upload.upload_video(
                    file_path, title, description, tags, privacy_status=args.privacy_youtube,
                    thumbnail_path=thumbnail_path)
            finally:
                if thumbnail_path:
                    os.remove(thumbnail_path)
            log_youtube_post(video["id"], video["file"], yt_video_id, url)

    if "tiktok" in platforms:
        print(f"\n--- TikTok: {video['id']} ---")
        existing = find_tiktok_upload(load_tiktok_log(), video["id"])
        if existing and not args.force_tiktok:
            print(f"  already posted (publish_id {existing['publish_id']}, status {existing['status']}) "
                  f"on {existing['posted_at']} - skipping (use --force-tiktok to re-upload anyway).")
        else:
            if args.tiktok_method == "browser":
                import tiktok_browser_upload as tiktok_upload
            else:
                import tiktok_upload
            caption = build_social_caption(defaults["tiktok_core_tags"], video["tiktok"])
            cover_offset_ms = compute_cover_offset_ms(video["id"])
            if cover_offset_ms is not None:
                print(f"  using cover frame at {cover_offset_ms}ms (logo window)")
            publish_id, status = tiktok_upload.upload_video(file_path, caption, privacy_level=args.privacy_tiktok,
                                                              cover_offset_ms=cover_offset_ms)
            log_tiktok_post(video["id"], video["file"], publish_id, status)

    if "instagram" in platforms:
        print(f"\n--- Instagram: {video['id']} ---")
        if not args.instagram_video_url:
            host_on_media_repo(file_path, video["file"])
        import instagram_upload
        caption = build_social_caption(defaults["instagram_core_tags"], video["instagram"])
        thumb_offset_ms = compute_cover_offset_ms(video["id"])
        if thumb_offset_ms is not None:
            print(f"  using cover frame at {thumb_offset_ms}ms (logo window)")
        media_id = instagram_upload.upload_video(file_path=video["file"], caption=caption,
                                                   video_url=args.instagram_video_url,
                                                   media_type=args.instagram_media_type,
                                                   thumb_offset_ms=thumb_offset_ms)
        log_instagram_post(video["id"], video["file"], media_id)
        run_prune()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video_ids", nargs="*", metavar="video_id", help="one or more video ids to post")
    p.add_argument("--platforms", default="youtube,tiktok,instagram",
                    help="comma-separated subset of youtube,tiktok,instagram")
    p.add_argument("--privacy-youtube", default="public", choices=["public", "unlisted", "private"])
    p.add_argument("--tiktok-method", default="browser", choices=["browser", "api"],
                    help="browser (default): simulate a manual upload through tiktok.com, not subject to the "
                    "Content Posting API's audit restriction, can post fully public. api: the audited-API path "
                    "in tiktok_upload.py, limited to SELF_ONLY until the app passes TikTok's review.")
    p.add_argument("--privacy-tiktok", default=None,
                    choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY", "FOLLOWER_OF_CREATOR"],
                    help="defaults to PUBLIC_TO_EVERYONE for --tiktok-method browser, SELF_ONLY for api")
    p.add_argument("--instagram-video-url", help="override the public URL instagram_upload.py fetches from "
                    "(only valid with a single video_id - each video needs its own hosted URL)")
    p.add_argument("--instagram-media-type", default="REELS", choices=["REELS", "VIDEO", "STORIES"],
                    help="REELS (default, max 15min/300MB), VIDEO (feed post), or STORIES")
    p.add_argument("--force-youtube", action="store_true",
                    help="re-upload to YouTube even if youtube_log.json says it's already posted")
    p.add_argument("--force-tiktok", action="store_true",
                    help="re-upload to TikTok even if tiktok_log.json says it's already posted")
    p.add_argument("--list", action="store_true", help="list all video ids and exit")
    args = p.parse_args()
    if args.privacy_tiktok is None:
        args.privacy_tiktok = "PUBLIC_TO_EVERYONE" if args.tiktok_method == "browser" else "SELF_ONLY"

    checklist = load_checklist()

    if args.list:
        for v in checklist["videos"]:
            flag = "  !! " + v["note"] if "note" in v else ""
            print(f"{v['date']}  {v['id']:<32} {v['file']}{flag}")
        return

    if not args.video_ids:
        p.error("at least one video_id is required unless --list is given")
    if args.instagram_video_url and len(args.video_ids) > 1:
        p.error("--instagram-video-url only makes sense with a single video_id")

    videos = [find_video(checklist, vid) for vid in args.video_ids]

    failures = []
    for i, video in enumerate(videos, 1):
        if len(videos) > 1:
            print(f"\n=== [{i}/{len(videos)}] {video['id']} ===")
        try:
            publish_one(video, checklist, args)
        except Exception as e:
            print(f"  FAILED: {video['id']}: {e}")
            failures.append(video["id"])

    if len(videos) > 1:
        ok = len(videos) - len(failures)
        print(f"\n=== Done: {ok}/{len(videos)} posted without error"
              f"{' - failed: ' + ', '.join(failures) if failures else ''} ===")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
