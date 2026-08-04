"""
Growth OS Phase 7 -- Video Engine API surface.

GET /video/status is a public status check (mirrors api/widgets.py's and
api/intelligence.py's own status-endpoint convention) -- lets the
frontend (and the admin panel) show whether the feature is actually
configured (TTS key + ffmpeg present) without exposing any admin-only
data. GET /video/latest streams back the most recent generated video
file if one exists, so a logged-in page (or the admin panel) can offer a
"preview/download" link. Both gated by the video_engine feature flag
just like every other Growth OS engine's public surface.

The actual generation trigger lives in api/admin.py (admin-token gated,
since ffmpeg+TTS calls are the heaviest single operation in Growth OS --
this must never be a public, unauthenticated action).
"""
import os
import sqlite3

from fastapi import APIRouter
from fastapi.responses import FileResponse

from services.video_engine_service import get_status, _OUTPUT_DIR, _OUTPUT_FILENAME

router = APIRouter()

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _video_engine_enabled() -> bool:
    try:
        conn = sqlite3.connect(_DB_PATH)
        row = conn.execute("SELECT enabled FROM feature_flags WHERE key='video_engine'").fetchone()
        conn.close()
        if row is None:
            return False
        return bool(row[0])
    except Exception:
        return False


@router.get("/video/status")
def video_status():
    if not _video_engine_enabled():
        return {"available": False, "reason": "video_engine flag is off"}
    return get_status()


@router.get("/video/latest")
def video_latest():
    if not _video_engine_enabled():
        return {"available": False, "reason": "video_engine flag is off"}
    path = os.path.join(_OUTPUT_DIR, _OUTPUT_FILENAME)
    if not os.path.exists(path):
        return {"available": False, "reason": "No video generated yet"}
    return FileResponse(path, media_type="video/mp4", filename=_OUTPUT_FILENAME)
