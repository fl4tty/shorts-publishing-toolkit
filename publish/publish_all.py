"""Unified CLI: post one short to YouTube, TikTok, and/or Instagram from
posting_checklist.json.

Examples:
  python publish_all.py characters --platforms youtube
  python publish_all.py characters --platforms youtube,tiktok,instagram
  python publish_all.py --list

Each platform's auth/setup is handled by its own module (see the docstrings
in youtube_upload.py, tiktok_auth.py + tiktok_upload.py, and
instagram_upload.py) — run those setup steps once before using this.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(os.path.dirname(HERE), "output")
CHECKLIST_FILE = os.path.join(HERE, "posting_checklist.json")


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
    hashtag_line = " ".join(defaults["youtube_hashtags"])
    credit = defaults["credit_images"] if yt.get("credit") == "images" else defaults["credit_footage"]
    description = f"{yt['description']}\n\n{credit}\n\n{hashtag_line}"
    tags = defaults["youtube_tags"]
    return yt["title"], description, tags


def build_social_caption(core_tags, platform_block):
    tags = " ".join(core_tags + platform_block.get("theme_tags", []))
    return f"{platform_block['caption']}\n\n{tags}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video_id", nargs="?")
    p.add_argument("--platforms", default="youtube,tiktok,instagram",
                    help="comma-separated subset of youtube,tiktok,instagram")
    p.add_argument("--privacy-youtube", default="public", choices=["public", "unlisted", "private"])
    p.add_argument("--privacy-tiktok", default="SELF_ONLY",
                    choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY", "FOLLOWER_OF_CREATOR"])
    p.add_argument("--instagram-video-url", help="override the public URL instagram_upload.py fetches from")
    p.add_argument("--list", action="store_true", help="list all video ids and exit")
    args = p.parse_args()

    checklist = load_checklist()

    if args.list:
        for v in checklist["videos"]:
            flag = "  !! " + v["note"] if "note" in v else ""
            print(f"{v['date']}  {v['id']:<32} {v['file']}{flag}")
        return

    if not args.video_id:
        p.error("video_id is required unless --list is given")

    video = find_video(checklist, args.video_id)
    file_path = os.path.join(OUTPUT_DIR, video["file"])
    if not os.path.exists(file_path):
        sys.exit(f"Video file not found: {file_path}")

    if "note" in video:
        print(f"NOTE: {video['note']}")
        confirm = input("Continue anyway? [y/N] ").strip().lower()
        if confirm != "y":
            return

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    defaults = checklist["defaults"]

    if "youtube" in platforms:
        print(f"\n--- YouTube: {video['id']} ---")
        import youtube_upload
        title, description, tags = build_youtube_args(defaults, video)
        youtube_upload.upload_video(file_path, title, description, tags, privacy_status=args.privacy_youtube)

    if "tiktok" in platforms:
        print(f"\n--- TikTok: {video['id']} ---")
        import tiktok_upload
        caption = build_social_caption(defaults["tiktok_core_tags"], video["tiktok"])
        tiktok_upload.upload_video(file_path, caption, privacy_level=args.privacy_tiktok)

    if "instagram" in platforms:
        print(f"\n--- Instagram: {video['id']} ---")
        import instagram_upload
        caption = build_social_caption(defaults["instagram_core_tags"], video["instagram"])
        instagram_upload.upload_video(file_path=video["file"], caption=caption, video_url=args.instagram_video_url)


if __name__ == "__main__":
    main()
