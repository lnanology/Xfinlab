"""
2026-09-14 (security/architecture audit follow-up): shared read-only
accessor for the `feature_flags` table that api/admin.py's toggle UI
already writes to. Until now, only a handful of flags (content_engine_
multilang, seo_auto_engine, video_engine, google_login/line_login/
whatsapp_otp) were actually checked before serving a request -- each
via its own inline `SELECT enabled FROM feature_flags WHERE key=...`
copy-pasted in api/admin.py. The other 7 flags AJ can toggle in the
admin panel (research_agent, portfolio, anomaly, screener,
chart_analysis, telegram_bot, referral) were persisted but never
enforced anywhere -- flipping one off in the UI looked like it worked
but silently did nothing.

This module exists so every api/*.py file can enforce a flag with one
import + one line, instead of each file needing its own sqlite3
connection/query (and instead of importing from api/admin.py, which
would be an api-module-importing-another-api-module dependency).

Fails OPEN (returns True) on any DB error or unknown key, matching the
existing inline-check pattern in api/admin.py (e.g. the
content_engine_multilang / seo_auto_engine checks there) -- a flags-
table outage should never itself take down the whole site.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def is_feature_enabled(key: str, default: bool = True) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT enabled FROM feature_flags WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        if row is None:
            return default
        return bool(row["enabled"])
    except Exception:
        return default


def require_feature_enabled(key: str, message: str = None, default: bool = True):
    """Raises HTTPException(503) if the flag is off. Import lazily inside
    callers that don't already depend on FastAPI's HTTPException to avoid
    an unnecessary import for callers that only need the plain bool
    (is_feature_enabled above)."""
    from fastapi import HTTPException

    if not is_feature_enabled(key, default=default):
        raise HTTPException(
            status_code=503,
            detail=message or f"This feature ('{key}') is temporarily disabled by the admin.",
        )
