"""YouTube Data API v3 upload — resumable upload via OAuth2 user credentials.

Setup (one-time):
  1. console.cloud.google.com -> new project -> enable "YouTube Data API v3".
  2. APIs & Services -> OAuth consent screen -> External -> add your own Google
     account under "Test users" (lets you use the app without Google's review,
     since you're only ever authorizing your own channel).
  3. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID ->
     "Desktop app" -> download the JSON -> save it next to this script as
     client_secret.json (or point YOUTUBE_CLIENT_SECRET in .env at it).
  4. First run opens a browser to sign in and approve; after that a token is
     cached to token_youtube.json so you won't need to re-auth each time.

No app review needed for this flow — uploading to your own channel with a
"testing" OAuth consent screen is explicitly allowed indefinitely.
"""
import os

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_FILE = os.path.join(HERE, os.environ.get("YOUTUBE_CLIENT_SECRET", "client_secret.json"))
TOKEN_FILE = os.path.join(HERE, "token_youtube.json")
GAMING_CATEGORY_ID = "20"


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def upload_video(file_path, title, description, tags=None, privacy_status="public",
                  made_for_kids=False, category_id=GAMING_CATEGORY_ID):
    service = get_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    media = googleapiclient.http.MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  uploading... {int(status.progress() * 100)}%")

    video_id = response["id"]
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"YouTube: {url}")
    return video_id, url


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Upload one video to YouTube as a Short.")
    p.add_argument("file")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--tags", default="", help="comma-separated")
    p.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    args = p.parse_args()

    tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload_video(args.file, args.title, args.description, tag_list, privacy_status=args.privacy)
