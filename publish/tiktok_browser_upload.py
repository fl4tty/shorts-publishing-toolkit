"""Simulated *manual* TikTok upload via browser automation (Playwright) —
NOT the Content Posting API. Posts go through TikTok's own web upload page,
the same flow a human clicking through tiktok.com would use, so they are NOT
subject to the Content Posting API's audit restriction (see tiktok_auth.py)
and can be set fully public immediately, without the app ever being audited.

Setup (one-time):
  1. pip install playwright && playwright install chromium
  2. python tiktok_browser_upload.py login
     Opens a real, visible browser window to tiktok.com. Log in by hand
     (password, 2FA, whatever your account needs — this script never
     touches your credentials). Once you see your feed/profile, come back
     to the terminal and press Enter. The logged-in session is saved to a
     dedicated browser profile under .tiktok_browser_profile/, so later
     runs are already signed in.

IMPORTANT — ToS risk: TikTok's Terms of Service generally prohibit
automated/bot interaction with their consumer web app outside the official
API. This script is meant for personal use on your own account/content, not
spam or scale, but TikTok's bot-detection could still flag or restrict the
account if it notices non-human upload patterns. That's a real tradeoff,
not a hypothetical one — weigh it before relying on this for every post.

IMPORTANT — fragility: TikTok's web upload page's DOM changes periodically
without notice, and this has NOT been tested against a live, logged-in
TikTok session (built without TikTok account access). Selectors below use
role/text lookups where possible since those tend to survive redesigns
better than CSS class names, but they will eventually break. Run with
TIKTOK_BROWSER_HEADLESS unset (visible browser) the first several times so
you can watch it work and catch any step that silently fails — a
screenshot is also saved to upload_failure.png whenever a step times out or
raises, so a failure can be diagnosed without needing to see your screen.

cover_offset_ms is accepted for call-site compatibility with tiktok_upload.py
but ISN'T wired up here — TikTok's web upload only lets you pick a cover
frame through a separate "Select cover" modal with a manual scrub bar, which
isn't practical to hit a precise timestamp through automation. Posts made
this way get TikTok's own auto-picked cover instead.
"""
import os
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

PROFILE_DIR = os.path.join(HERE, ".tiktok_browser_profile")
HEADLESS = os.environ.get("TIKTOK_BROWSER_HEADLESS", "0") == "1"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?lang=en"
FAILURE_SCREENSHOT = os.path.join(HERE, "upload_failure.png")

# TikTok's web UI only exposes these three audiences for a normal post.
PRIVACY_LABELS = {
    "PUBLIC_TO_EVERYONE": "Everyone",
    "MUTUAL_FOLLOW_FRIENDS": "Friends",
    "SELF_ONLY": "Only me",
}


def login():
    """One-time interactive login - saves the session into PROFILE_DIR."""
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(PROFILE_DIR, headless=False)
        page = context.new_page()
        page.goto("https://www.tiktok.com/login")
        print("Log in to TikTok in the opened browser window (password, 2FA, etc.) -")
        print("this script never sees your credentials, only the resulting session.")
        input("Once you're logged in and see your feed/profile, press Enter here to save the session...")
        context.close()
    print(f"Session saved to {PROFILE_DIR}")


def _find_caption_box(page):
    # TikTok's caption editor is a contenteditable div, not a <textarea>, so a
    # role-based textbox lookup is more stable across redesigns than a CSS selector.
    box = page.get_by_role("textbox").first
    box.wait_for(state="visible", timeout=30_000)
    return box


def _set_privacy(page, privacy_level):
    label = PRIVACY_LABELS.get(privacy_level)
    if label is None:
        raise ValueError(f"privacy_level {privacy_level!r} isn't available on the web upload UI "
                          f"(only {list(PRIVACY_LABELS)} are)")
    try:
        page.get_by_text("Who can watch this video", exact=False).first.locator("..").click(timeout=5_000)
        page.get_by_text(label, exact=True).first.click(timeout=5_000)
    except PlaywrightTimeoutError:
        print(f"  warning: couldn't find the privacy dropdown - it likely stayed on its default "
              f"(probably private/draft). Check the post manually.")


def _set_toggle(page, label_text, enabled):
    try:
        row = page.get_by_text(label_text, exact=False).first.locator("..")
        switch = row.locator("input[type=checkbox], [role=switch]").first
        is_checked = (switch.is_checked() if switch.get_attribute("type") == "checkbox"
                      else switch.get_attribute("aria-checked") == "true")
        if is_checked != enabled:
            switch.click(timeout=5_000)
    except Exception:
        print(f"  warning: couldn't find the '{label_text}' toggle - leaving it at its default.")


def upload_video(file_path, caption, privacy_level="SELF_ONLY",
                  disable_comment=False, disable_duet=False, disable_stitch=False,
                  cover_offset_ms=None):
    if not os.path.isdir(PROFILE_DIR):
        sys.exit("No saved session - run `python tiktok_browser_upload.py login` first.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(PROFILE_DIR, headless=HEADLESS)
        page = context.new_page()
        try:
            page.goto(UPLOAD_URL, wait_until="networkidle", timeout=60_000)

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(file_path)
            print("  video handed to the page, waiting for TikTok to finish processing...")

            # the Post button stays disabled until TikTok's finished transcoding
            post_button = page.get_by_role("button", name="Post", exact=True)
            post_button.wait_for(state="visible", timeout=120_000)

            caption_box = _find_caption_box(page)
            caption_box.click()
            # select-all + type so a default/placeholder caption doesn't survive
            page.keyboard.press("Control+A")
            page.keyboard.type(caption[:2200])

            _set_privacy(page, privacy_level)
            if disable_comment:
                _set_toggle(page, "Comment", enabled=False)
            if disable_duet:
                _set_toggle(page, "Duet", enabled=False)
            if disable_stitch:
                _set_toggle(page, "Stitch", enabled=False)

            for _ in range(30):
                if post_button.is_enabled():
                    break
                time.sleep(2)
            else:
                page.screenshot(path=FAILURE_SCREENSHOT)
                return f"browser-{int(time.time())}", "TIMED_OUT"

            post_button.click()

            try:
                page.get_by_text("Your video has been uploaded", exact=False).wait_for(timeout=60_000)
                status = "PUBLISH_COMPLETE"
            except PlaywrightTimeoutError:
                page.screenshot(path=FAILURE_SCREENSHOT)
                status = "TIMED_OUT"

            print(f"  TikTok (browser): {status}")
            return f"browser-{int(time.time())}", status
        except Exception:
            page.screenshot(path=FAILURE_SCREENSHOT)
            raise
        finally:
            context.close()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Upload one video to TikTok by simulating the manual web upload flow.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("login", help="one-time interactive login, saves the session")
    up = sub.add_parser("upload")
    up.add_argument("file")
    up.add_argument("--caption", required=True)
    up.add_argument("--privacy", default="SELF_ONLY",
                     choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"])
    args = p.parse_args()

    if args.cmd == "login":
        login()
    elif args.cmd == "upload":
        upload_video(args.file, args.caption, privacy_level=args.privacy)
    else:
        p.print_help()
