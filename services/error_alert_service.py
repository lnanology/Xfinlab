"""
Production error alerting -- 2026-09-14 addition, closing the "AJ has no way
to learn about a live error without manually opening Railway's log viewer"
gap found in that day's site-wide pain-points audit. There is still no real
APM/error-tracking service wired in (Sentry etc. would need a new account +
env var AJ hasn't set up) -- this instead reuses the exact same best-effort,
DB-backed, cooldown-deduped email pattern services/data_source_registry.py's
record_run_error() already uses for "a data source is failing" alerts, just
generalized to "an API request raised an unhandled exception."

Deliberately narrow in scope: this only fires from backend/main.py's global
`Exception` handler (see there), i.e. only for exceptions that would
otherwise have surfaced as a bare, unhelpful 500 to the caller. It does NOT
fire for `HTTPException`s any route already raises on purpose (401/404/etc)
-- those are expected control flow, not incidents, and Starlette's own
exception-handler lookup resolves them to FastAPI's existing HTTPException
handler before ever reaching this file (exact type match wins over the
general Exception handler).

Same get_db()/CREATE TABLE IF NOT EXISTS pattern as api/admin.py's
feature_flags table -- own local sqlite3 connection.
"""
import logging
import os
import sqlite3
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# One email per (route path, exception type) at most every this many hours --
# a single misbehaving endpoint failing on every request (e.g. a bad deploy)
# sends ONE email, not one per request, while still re-notifying if the same
# error keeps happening across deploys/days.
_NOTIFY_COOLDOWN_HOURS = 1


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS error_alerts (
            signature TEXT PRIMARY KEY,
            route TEXT,
            exception_type TEXT,
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT DEFAULT (datetime('now')),
            last_notified_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def notify_admin_of_error(route: str, exc: Exception) -> None:
    """Best-effort -- never raises, so a broken alert path can never turn
    one production error into two (the original error, plus a failure to
    report it). Safe to call from inside an exception handler."""
    try:
        signature = f"{route}:{type(exc).__name__}"
        conn = _get_db()
        row = conn.execute(
            "SELECT occurrence_count, last_notified_at FROM error_alerts WHERE signature = ?",
            (signature,),
        ).fetchone()

        should_notify = True
        if row and row["last_notified_at"]:
            try:
                last_notified = datetime.strptime(row["last_notified_at"], "%Y-%m-%d %H:%M:%S")
                should_notify = datetime.utcnow() - last_notified > timedelta(hours=_NOTIFY_COOLDOWN_HOURS)
            except (ValueError, TypeError):
                should_notify = True

        conn.execute(
            """
            INSERT INTO error_alerts (signature, route, exception_type, occurrence_count, last_seen_at)
            VALUES (?, ?, ?, 1, datetime('now'))
            ON CONFLICT(signature) DO UPDATE SET
                occurrence_count = occurrence_count + 1,
                last_seen_at = datetime('now')
            """,
            (signature, route, type(exc).__name__),
        )
        conn.commit()

        if should_notify:
            occurrence_count = (row["occurrence_count"] if row else 0) + 1
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:]
            try:
                from services.email_service import EmailService
                from api.admin import ADMIN_EMAIL
                html = f"""
                <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
                    <h2 style="color:#ef4444">Unhandled error on {route}</h2>
                    <p>{type(exc).__name__}: {str(exc)[:300]}</p>
                    <p>Seen {occurrence_count} time(s) so far (this signature).</p>
                    <pre style="font-family:monospace;background:#111827;padding:12px;border-radius:8px;white-space:pre-wrap;font-size:0.8rem">{tb}</pre>
                    <p style="color:#64748b;font-size:0.8rem">You won't get another one of these for this exact route+error type for {_NOTIFY_COOLDOWN_HOURS}h.</p>
                </div>
                """
                sent = EmailService.send(ADMIN_EMAIL, f"[XFINLAB] Error on {route}: {type(exc).__name__}", html)
                if sent:
                    conn.execute(
                        "UPDATE error_alerts SET last_notified_at = datetime('now') WHERE signature = ?",
                        (signature,),
                    )
                    conn.commit()
            except Exception:
                logger.exception("error_alert_service: failed to send admin alert email")
        conn.close()
    except Exception:
        logger.exception("error_alert_service: notify_admin_of_error itself failed")
