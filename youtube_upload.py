#!/usr/bin/env python3
"""clipper — complete YouTube upload flow (standalone, Python 3.10+ standard library only).

This is the exact flow clipper's server uses to publish a clip that the owner has reviewed and approved
to the owner's own YouTube channel (YouTube Data API v3, videos.insert, resumable upload).

Credentials (OAuth 2.0 for the owner's own account, scope https://www.googleapis.com/auth/youtube.upload)
are read from environment variables, never from source code:

    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

Usage:
    python youtube_upload.py clip.mp4 --title "Clip title" --description "Text #Shorts" --privacy private

In clipper this runs from a queue that enforces volume limits (max 3 uploads/day, 2 h apart) and only
for clips the owner approved in a private web interface.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


def http(req: urllib.request.Request, timeout: float = 60):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:400]}")


def access_token() -> str:
    """Exchange the stored refresh token for a short-lived access token."""
    body = urllib.parse.urlencode({
        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with http(urllib.request.Request(TOKEN_URL, data=body)) as r:
        return json.loads(r.read())["access_token"]


def upload(video: Path, title: str, description: str, privacy: str) -> str:
    token = access_token()
    meta = {
        "snippet": {"title": re.sub(r"[<>]", "", title)[:100], "description": description[:4900], "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    size = video.stat().st_size
    # 1) start a resumable upload session with the video metadata
    start = urllib.request.Request(UPLOAD_URL, data=json.dumps(meta).encode(), method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    with http(start) as r:
        session = r.headers["Location"]
    # 2) send the video bytes to the session URL
    put = urllib.request.Request(session, data=video.read_bytes(), method="PUT", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "video/mp4", "Content-Length": str(size)})
    with http(put, timeout=600) as r:
        video_id = json.loads(r.read())["id"]
    return f"https://youtube.com/shorts/{video_id}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload an approved clip to the owner's YouTube channel.")
    ap.add_argument("video", type=Path)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    a = ap.parse_args()
    if not a.video.is_file():
        sys.exit(f"file not found: {a.video}")
    print(upload(a.video, a.title, a.description, a.privacy))


if __name__ == "__main__":
    main()
