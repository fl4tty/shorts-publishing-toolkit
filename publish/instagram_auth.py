"""One-time Instagram login — gets the access token instagram_upload.py
needs. No Facebook Page required.

Setup (one-time):
  1. developers.facebook.com -> create a Business-type app -> add the
     "Instagram" use case ("Manage messaging & content on Instagram").
  2. Create a Business Portfolio for the app if you don't have one (the app
     creation flow prompts for this).
  3. Host oauth_callback.html somewhere public (a Claude Artifact works
     well — see README.md). Under Instagram API > API setup with Unified
     login, create a login configuration (template values are fine), then
     register that URL as the redirect URL. Put the URL in .env as
     IG_REDIRECT_URI, and the configuration's id in .env as
     IG_CONFIG_ID.
  4. Under App roles > Roles > Instagram Testers, add your Instagram
     username, then accept the invite from Instagram itself at
     instagram.com/accounts/manage_access/ (Tester Invites tab).
  5. On Instagram itself: Settings > Professional account > Facebook >
     Connect. This step turned out to be required even without a Page —
     until it's done, the login flow below errors with "Instagram Pro
     account required" even though the account already shows up as a
     business asset in Meta Business Suite.
  6. Add the Instagram account as a business asset: Business Settings >
     Business assets > Apps > Add > Connect an app ID (your App ID). If it
     says "you don't own this app", make sure you're looking at the actual
     business portfolio id — business.facebook.com/settings/ can silently
     redirect to a different default business than the one you created;
     check the business switcher / the "Meta Business Suite account" card
     on the app's Roles page for the right one.
  7. Copy the App ID and App Secret from App settings > Basic into .env as
     IG_APP_ID / IG_APP_SECRET.

Usage (two steps, since this has to run non-interactively):
    python instagram_auth.py login
        Opens your browser to Facebook Login for Business (Instagram's
        newer "Unified Login" apps use this instead of a plain
        instagram.com/oauth/authorize screen). Walk through it: pick your
        Instagram account, and when it asks for an optional Ad Account,
        either fill in the minimal required fields (name/country/currency —
        no payment info is requested) or see if your app's config skips
        that step.
    python instagram_auth.py --code <code>
        After approving, Instagram redirects to the callback page. Copy the
        code= value from the browser's address bar (the page's own display
        of it doesn't reliably work, and codes expire fast) and paste it
        here right away. Writes IG_ACCESS_TOKEN to .env.

This flow hands back a System User access token tied to the Business
Portfolio rather than a per-person Instagram token — it does not expire and
never needs refreshing, unlike the older Instagram Login flow's 60-day
tokens. It also means all Graph API calls (here and in instagram_upload.py)
go to graph.facebook.com, not graph.instagram.com, despite what the older
Instagram API docs show.
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

APP_ID = os.environ["IG_APP_ID"]
APP_SECRET = os.environ["IG_APP_SECRET"]
REDIRECT_URI = os.environ["IG_REDIRECT_URI"]
# The app's "Instagram API (Unified Login)" configuration id, from
# Instagram API > API setup with Unified login in the Meta app dashboard.
CONFIG_ID = os.environ["IG_CONFIG_ID"]
AUTHORIZE_URL = "https://www.facebook.com/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v23.0/oauth/access_token"


def open_login():
    params = {
        "client_id": APP_ID,
        "config_id": CONFIG_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "override_default_response_type": "true",
        "state": "shorts_kit",
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    print(f"Opening: {url}")
    webbrowser.open(url)
    print("After you approve, Instagram redirects to a page showing an authorization code.")
    print("Copy the code= value from the browser's address bar (strip any trailing #_).")
    print("Run: python instagram_auth.py --code <code>")


def exchange_code(code):
    code = code.split("#")[0]

    resp = requests.get(
        TOKEN_URL,
        params={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )
    if not resp.ok:
        print(f"Token exchange failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
    token_data = resp.json()

    set_key(ENV_FILE, "IG_ACCESS_TOKEN", token_data["access_token"])
    print("Saved IG_ACCESS_TOKEN to .env (System User token — does not expire)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", nargs="?", choices=["login"], help="open the login page")
    p.add_argument("--code", help="authorization code from the callback page")
    args = p.parse_args()

    if args.code:
        exchange_code(args.code)
    else:
        open_login()
