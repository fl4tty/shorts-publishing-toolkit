# Publishing toolkit

Scripts that post a rendered short directly to YouTube, TikTok, and Instagram
using each platform's own official API. No third-party tool in the middle.

**Read this before you expect "fully automatic" — each platform gatekeeps
auto-posting differently:**

| Platform | Setup cost | Real restriction |
|---|---|---|
| YouTube | ~10 min | None once set up. You can leave your OAuth consent screen in "Testing" mode forever, since you're only ever authorizing your own channel. |
| TikTok | ~30 min + review | Content Posting API requires TikTok to **audit your developer app**. Until that's approved: (1) the TikTok *account* you're posting to must be set to Private in its own settings — this is separate from the post's `privacy_level`, and the API returns a 403 (`unaudited_client_can_only_post_to_private_accounts`) if the account is public; (2) the app's Web client also rejects `localhost` and `127.0.0.1` redirect URIs outright, so the OAuth login flow here uses a public callback page you copy the code from by hand. Neither of these go away until the app passes audit. |
| Instagram | ~45 min | No Facebook Page needed, but two non-obvious steps are: (1) the Graph API **fetches the video from a URL you host** — it will not accept a direct file upload, so every video needs to be pushed somewhere public first; (2) even with the Instagram account already showing as a Business Portfolio asset, the OAuth consent screen errors with "Instagram Pro account required" until you *also* go to Instagram's own Settings → Professional account → Facebook → **Connect** (this links the account identity — it does not create or require a Page). Skip that step and the login flow silently fails with `access_denied`/`user_denied`. |

So "upload to all three with one command" is real for YouTube today, and
real for TikTok/Instagram once you've done the one-time setup below
(TikTok's audit can take a few days — start that now if you want it live
before a launch date you're building toward).

## Install

```bash
pip install -r requirements.txt
cp .env.example .env
cp example_posting_checklist.json posting_checklist.json
```

Fill in `.env` and `posting_checklist.json` as you complete each platform's
setup below.

## A public callback page, first

Both TikTok and Instagram's login flows redirect to a URL after you approve
— and both reject `localhost`/loopback addresses, so the redirect target has
to be genuinely public. `oauth_callback.html` in this folder is a small page
that just shows the authorization code so you can copy it by hand. The
simplest way to host it: publish it as a **Claude Artifact** (if you're
setting this up with Claude's help, just ask it to publish the file) and use
that URL. Any other static host works too — it just needs HTTPS and a
publicly reachable URL that isn't localhost.

You can reuse the same hosted page for both TikTok (`TIKTOK_REDIRECT_URI`)
and Instagram (`IG_REDIRECT_URI`) in `.env`.

## YouTube setup

See the docstring in `youtube_upload.py`. Summary: Google Cloud project →
enable YouTube Data API v3 → OAuth consent screen (External, add yourself as
a test user) → OAuth client ID (Desktop app) → save the downloaded JSON as
`client_secret.json` in this folder. First run opens a browser to approve;
after that it's silent.

## TikTok setup

See the docstring in `tiktok_auth.py`. Summary: register an app at
developers.tiktok.com (the Sandbox version of the app while unaudited — use
its Sandbox client key/secret, add your TikTok account as a Sandbox Target
User) → add the Content Posting API product → enable **Direct Post** under it
(this is what actually adds the `video.publish` scope — the scope doesn't
show up in a plain scope search) → add your hosted callback page as the
redirect URI (TikTok's Web client rejects `localhost` and `127.0.0.1`
outright) → put the client key/secret and `TIKTOK_REDIRECT_URI` in `.env`.

Login flow (two steps, since the code has to be copied by hand):
```bash
python tiktok_auth.py login
# sign in, approve, land on the callback page
# copy the code= value from the browser's address bar (the page's own
# display of it doesn't reliably work on every host — reading it from the
# address bar always works)
python tiktok_auth.py --code <paste the code here, immediately — it expires fast>
```

Before the app passes TikTok's audit, uploads also require the destination
TikTok account itself to be set to **Private** (Settings → Privacy →
Private account) — not just the post's privacy level. Switch it back to
Public once you're done testing, or whenever you don't want new followers
blocked from finding the account. Submit the Production version of the app
for TikTok's audit when you want to drop both restrictions (private account
requirement, SELF_ONLY-only posting).

## Instagram setup

Uses Meta's newer "Instagram API with Instagram Login" / Unified Login —
**no Facebook Page required**. See the full docstring in `instagram_auth.py`
for every step; summary:

1. Instagram account must already be Professional (Creator/Business).
2. developers.facebook.com → create a **Business-type** app → add the
   "Manage messaging & content on Instagram" use case → create a Business
   Portfolio for it if prompted.
3. Instagram API → API setup with Unified login → create a login
   configuration → register your hosted callback page as the redirect URL
   → put that URL in `.env` as `IG_REDIRECT_URI`, and the configuration's
   id as `IG_CONFIG_ID`.
4. App roles → Roles → Instagram Testers → add your username → accept the
   invite from **instagram.com/accounts/manage_access/** (Tester Invites tab).
5. **The easy-to-miss step:** on Instagram itself, Settings → Professional
   account → Facebook → **Connect**. Without this, the login dialog shows
   "Instagram Pro account required" and the account doesn't appear in the
   asset picker — even though it's already listed as a business asset in
   Meta Business Suite. This connects the account identity only; it doesn't
   create or need a Page.
6. Business Settings → Business assets → Apps → Add → Connect an app ID →
   your App ID. If you get "you don't own this app," you're likely looking
   at the wrong business — `business.facebook.com/settings/` without an
   explicit `business_id` can silently default to a different business than
   the one you created; check the "Meta Business Suite account" card on the
   app's Roles page for the right one, and pass its id explicitly in the URL.
7. App settings → Basic → copy App ID / App Secret into `.env`
   (`IG_APP_ID` / `IG_APP_SECRET`).

Login flow (two steps, since the code has to be copied by hand — same
pattern as TikTok, and for the same reason: reading it from the browser's
address bar is more reliable than trusting the callback page's own display):
```bash
python instagram_auth.py login
# walk the consent screen: pick the Instagram account, and for the optional
# Ad Account step either fill in name/country/currency (no payment info is
# asked) or skip it if your flow doesn't show it
python instagram_auth.py --code <paste the code here, immediately>
```

This flow hands back a **System User access token** tied to the Business
Portfolio — unlike the older Instagram Login flow's 60-day tokens, this one
**never expires** and needs no refresh. It also only works against
`graph.facebook.com`, not `graph.instagram.com`, despite what the Instagram
API docs show — both `instagram_auth.py` and `instagram_upload.py` already
point at the right host.

`instagram_upload.py` can publish as a Reel (default), a Feed video post, or
a Story — pass `--media-type REELS|VIDEO|STORIES`. None of these share to
Facebook; that only happens with a linked Page, which this setup doesn't have.

### Public video hosting

Since the Graph API fetches from a URL, every video needs to be reachable
publicly before publishing. The simplest option: a public GitHub Pages repo.
```bash
mkdir my-media-repo && cd my-media-repo && git init
cp /path/to/your-video.mp4 .
git add . && git commit -m "add video"
gh repo create my-media-repo --public --source=. --remote=origin --push
gh api repos/<you>/my-media-repo/pages -X POST -f "source[branch]=main" -f "source[path]=/"
```
Then set `IG_VIDEO_PUBLIC_BASE_URL=https://<you>.github.io/my-media-repo`
in `.env`. Push each day's video to this repo before publishing it — the
file needs to already be live at that URL when `media_publish` runs. Any
other public static host (S3, Cloudflare R2, Netlify, …) works the same way.

## Usage

```bash
# see every video id and its scheduled date
python publish_all.py --list

# post one video everywhere
python publish_all.py some_video_id --platforms youtube,tiktok,instagram

# just YouTube, as unlisted (good for a dry run)
python publish_all.py some_video_id --platforms youtube --privacy-youtube unlisted

# TikTok, explicitly public once your app is audited
python publish_all.py some_video_id --platforms tiktok --privacy-tiktok PUBLIC_TO_EVERYONE

# Instagram, pointing at a video URL directly instead of .env's base URL
python publish_all.py some_video_id --platforms instagram --instagram-video-url https://my-bucket.s3.amazonaws.com/some_video.mp4

# Instagram directly (not through publish_all.py), as a Feed post or Story instead of a Reel
python instagram_upload.py some_video.mp4 --caption "..." --media-type VIDEO
python instagram_upload.py some_video.mp4 --caption "..." --media-type STORIES
```

Titles, descriptions, and hashtags come from `posting_checklist.json` (one
entry per video — see `example_posting_checklist.json` for the schema, and
the top-level `defaults` block for shared tags/credit lines). Edit that file
to tweak copy — no code changes needed for day-to-day posting.

## Recommended first run

1. `python publish_all.py <video_id> --platforms youtube --privacy-youtube unlisted`
   and check it on your channel before ever running with `public`.
2. Do the same dry-run pattern for TikTok (`SELF_ONLY`, and the destination
   account set to Private first — see TikTok setup above) and Instagram
   before trusting any of this with a public post.
