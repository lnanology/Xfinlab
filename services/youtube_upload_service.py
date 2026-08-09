"""
2026-08-09 (Video Engine -> YouTube auto-upload, admin chat-to-video
follow-up): uploads a just-generated Video Engine .mp4 to XFINLAB's
YouTube channel via the YouTube Data API v3, using a REST-only
implementation (no google-api-python-client / google-auth SDKs) to match
this codebase's existing minimal-dependency pattern for external Google
APIs -- see services/tts_service.py, which calls Google Cloud TTS via raw
`requests` calls instead of pulling in the heavy official SDK. No new
requirements.txt entries needed; `requests` is already a dependency.

Dormant-safe like every other not-yet-configured integration in this repo
(services/broker_affiliate_config.py, api/webhooks_paddle.py, js/ads.js,
js/support-widget.js): is_available() gates on three env vars
(GOOGLE_YT_CLIENT_ID / GOOGLE_YT_CLIENT_SECRET / GOOGLE_YT_REFRESH_TOKEN)
that are unset on every deploy until they're pasted into Railway's
environment variables. Until then this module silently no-ops and callers
get back a clean {"available": False, ...} instead of crashing.

Auth flow: the refresh_token (obtained once via a local OAuth consent
flow -- see get_youtube_refresh_token.py, shared with the admin
separately) is exchanged for a short-lived access_token on each call via
Google's token endpoint. No token is ever persisted beyond a single
upload_video() call.

IMPORTANT caveat for whoever revisits this: while the Google Cloud OAuth
app stays in "Testing" publishing status (the default until it's manually
published and passes Google's verification review for the sensitive
youtube.upload scope), refresh tokens for External-type apps expire after
7 days of *inactivity* per Google's policy. If uploads that used to work
suddenly start failing with an invalid_grant-style error after a quiet
period, that's the likely cause -- the fix is generating a fresh refresh
token, or (the permanent fix) publishing the OAuth app to Production.
"""
import json
import mimetypes
import os
import uuid
from typing import List, Optional

import requests

_CLIENT_ID_ENV = "GOOGLE_YT_CLIENT_ID"
_CLIENT_SECRET_ENV = "GOOGLE_YT_CLIENT_SECRET"
_REFRESH_TOKEN_ENV = "GOOGLE_YT_REFRESH_TOKEN"

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=multipart&part=snippet,status"


def is_available() -> bool:
    return bool(
        os.environ.get(_CLIENT_ID_ENV)
        and os.environ.get(_CLIENT_SECRET_ENV)
        and os.environ.get(_REFRESH_TOKEN_ENV)
    )


def _get_access_token() -> Optional[str]:
    try:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": os.environ[_CLIENT_ID_ENV],
                "client_secret": os.environ[_CLIENT_SECRET_ENV],
                "refresh_token": os.environ[_REFRESH_TOKEN_ENV],
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except requests.RequestException:
        return None


def upload_video(
    file_path: str,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    category_id: str = "25",
    privacy_status: str = "unlisted",
) -> dict:
    """Uploads file_path to XFINLAB's YouTube channel.

    privacy_status defaults to "unlisted" (not "private", not "public")
    deliberately -- unlisted videos are watchable via direct link (so
    output can be spot-checked/shared before a human decides to make it
    public) but don't appear in search or the channel's public video
    list, avoiding auto-publishing untested output to the world. Flip to
    "public" per-call once the pipeline's output quality has been
    manually verified a few times.

    category_id 25 = "News & Politics" (YouTube's official category
    taxonomy) -- closest fit for market-commentary content; 27 =
    "Education" is the other reasonable choice if that framing fits
    better later.
    """
    if not is_available():
        return {"available": False, "message": "YouTube upload not configured (GOOGLE_YT_* env vars missing)"}
    if not os.path.isfile(file_path):
        return {"available": False, "message": f"File not found: {file_path}"}

    access_token = _get_access_token()
    if not access_token:
        return {
            "available": False,
            "message": (
                "Could not refresh YouTube access token -- refresh_token may have expired "
                "(see module docstring: 7-day expiry while the OAuth app is in Testing status)"
            ),
        }

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    mime_type = mimetypes.guess_type(file_path)[0] or "video/mp4"
    boundary = f"xfinlab-{uuid.uuid4().hex}"

    metadata_part = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
    ).encode("utf-8")

    with open(file_path, "rb") as f:
        video_bytes = f.read()

    body = (
        metadata_part
        + f"--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8")
        + video_bytes
        + f"\r\n--{boundary}--".encode("utf-8")
    )

    try:
        resp = requests.post(
            _UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            data=body,
            timeout=180,
        )
        if resp.status_code not in (200, 201):
            return {"available": False, "message": f"YouTube API error {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        video_id = data.get("id")
        return {
            "available": True,
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}" if video_id else None,
            "privacy_status": privacy_status,
        }
    except requests.RequestException as e:
        return {"available": False, "message": f"YouTube upload request failed: {e}"}
