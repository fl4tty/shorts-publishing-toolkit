"""One-time TikTok OAuth2 login — gets the access/refresh token tiktok_upload.py needs.

Setup (one-time):
  1. developers.tiktok.com -> create an app (or use the Sandbox of an
     existing one while testing).
  2. Add the "Content Posting API" product, enable "Direct Post" under it,
     and add the `video.publish` scope (it appears automatically once
     Direct Post is on).
  3. Host oauth_callback.html somewhere public (a Claude Artifact works
     well — see README.md), then under the app's Login Kit settings, add
     that exact URL as a redirect URI, and put it in .env as
     TIKTOK_REDIRECT_URI. TikTok's Web client rejects both "localhost" and
     loopback IPs (127.0.0.1) as redirect URIs, so a local HTTP server
     can't catch the callback here — this flow uses that public page to
     show the authorization code for you to copy and paste back into this
     script instead.
  4. Copy the app's Client Key and Client Secret into .env
     (TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET) — use the Sandbox
     credentials while the app is unaudited.

Usage (two steps, since this has to run non-interactively):
    python tiktok_auth.py login
        Opens your browser to TikTok's login/consent screen.
    python tiktok_auth.py --code <code>
        After approving, TikTok redirects to the callback page showing an
        authorization code. Paste it here to exchange it for tokens, which
        get written into .env.

IMPORTANT — TikTok's audit restriction: until TikTok reviews and approves
your app for the Content Posting API (an app review step, not instant),
videos posted through an unaudited app can only be set to private
(SELF_ONLY) visibility, or can only be delivered to accounts you've added
as Target Users in the Sandbox (see the app's Sandbox settings). Public
auto-posting on your main account requires that audit to pass first —
budget time for that before counting on fully hands-off TikTok posting.
"""
import argparse
import os
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv, set_key

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")
load_dotenv(ENV_FILE)

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REDIRECT_URI = os.environ["TIKTOK_REDIRECT_URI"]
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def open_login():
    params = {
        "client_key": CLIENT_KEY,
        "scope": "video.publish",
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": "shorts_kit",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"Opening: {url}")
    webbrowser.open(url)
    print("After you approve, TikTok redirects to a page showing an authorization code.")
    print("Run: python tiktok_auth.py --code <code>")


def exchange_code(code):
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )
    tokens = resp.json()
    if not resp.ok or "access_token" not in tokens:
        print(f"Token exchange failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        return
    set_key(ENV_FILE, "TIKTOK_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_FILE, "TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    print("Saved TIKTOK_ACCESS_TOKEN and TIKTOK_REFRESH_TOKEN to .env")


def refresh_access_token():
    """TikTok access tokens expire after 24h (the refresh token lasts a
    year), so tiktok_upload.py calls this before every upload instead of
    tracking expiry - cheap, and always valid as long as the refresh token
    itself hasn't expired."""
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
        },
    )
    tokens = resp.json()
    if not resp.ok or "access_token" not in tokens:
        print(f"Token refresh failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        return None
    set_key(ENV_FILE, "TIKTOK_ACCESS_TOKEN", tokens["access_token"])
    if "refresh_token" in tokens:
        set_key(ENV_FILE, "TIKTOK_REFRESH_TOKEN", tokens["refresh_token"])
    os.environ["TIKTOK_ACCESS_TOKEN"] = tokens["access_token"]
    return tokens["access_token"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", nargs="?", choices=["login", "refresh"],
                    help="open the TikTok login page, or refresh an expired access token")
    p.add_argument("--code", help="authorization code from the callback page")
    args = p.parse_args()

    if args.code:
        exchange_code(args.code)
    elif args.action == "refresh":
        if refresh_access_token():
            print("Refreshed TIKTOK_ACCESS_TOKEN in .env")
    else:
        open_login()
