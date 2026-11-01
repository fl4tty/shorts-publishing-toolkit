"""Delete rendered shorts from the media-hosting repo once
Instagram no longer needs them.

Instagram's publishing API fetches a video from a public URL once, during
upload; it doesn't need that URL again afterward. media_log.json (written by
publish_all.py each time an Instagram post succeeds) tracks when each file
was posted. This script removes any file whose post is more than
PRUNE_AFTER_HOURS old from the local media-repo clone (MEDIA_REPO_DIR, or a
sibling "my-media-repo" folder by default), commits, and pushes - so the file
stops being publicly hosted shortly after Instagram no longer needs it,
without touching rendered output or any other platform.

Run manually, or (the normal case) automatically: publish_all.py calls this
right after every Instagram post, so pruning happens each time new media is
hosted rather than on an always-on timer.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA_LOG_FILE = os.path.join(HERE, "media_log.json")
MEDIA_REPO = os.environ.get(
    "MEDIA_REPO_DIR", os.path.join(os.path.dirname(os.path.dirname(HERE)), "my-media-repo"))
PRUNE_AFTER_HOURS = 12


def run(cmd, **kw):
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=MEDIA_REPO, **kw)


def main():
    if not os.path.exists(MEDIA_LOG_FILE):
        print("No media_log.json yet - nothing to prune.")
        return
    with open(MEDIA_LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)

    now = datetime.now(timezone.utc)
    due = []
    for entry in log:
        if entry.get("pruned"):
            continue
        posted_at = datetime.fromisoformat(entry["posted_at"])
        if now - posted_at >= timedelta(hours=PRUNE_AFTER_HOURS):
            due.append(entry)

    if not due:
        print("Nothing due for pruning yet.")
        return

    removed = []
    for entry in due:
        path = os.path.join(MEDIA_REPO, entry["file"])
        if os.path.exists(path):
            run(["git", "rm", "--quiet", entry["file"]])
            removed.append(entry["file"])
        else:
            print(f"  (already gone: {entry['file']})")
        entry["pruned"] = True

    if removed:
        message = "Prune " + ", ".join(removed) + " (posted >12h ago, no longer needed by Instagram)"
        run(["git", "commit", "--quiet", "-m", message])
        run(["git", "push", "--quiet"])
        print(f"Pruned {len(removed)} file(s): {', '.join(removed)}")
    else:
        print("All due entries were already removed from the repo; marking them pruned.")

    with open(MEDIA_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    main()
