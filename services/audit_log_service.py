"""
Audit Log Service — Security & Operations Layer, Phase 2.

Writes to the `audit_logs` table (already present in the live xfinlab.db —
see database/schema.sql). Covers the actions the roadmap called out as
must-have: login, admin modifications. AI-analysis and payment actions
aren't wired in yet because those endpoints don't currently carry an
authenticated user_id through to the point where the action happens (see
NOTE below) — logging them meaningfully needs that plumbed through first.

Design choices:
- Never raises. A failed audit write should never take down the request
  it's observing — we log a warning and move on.
- audit_logs.user_id is NOT NULL in the live schema, so we can only log
  actions that have a real, known user_id (e.g. a successful login, an
  authenticated admin action) — not anonymous/failed attempts. That's a
  real limitation, not an oversight; loosening the NOT NULL constraint is
  a separate migration if we want anonymous/failed-attempt logging later.
"""

import logging
import os
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_action(user_id: int, action: str, ip_address: Optional[str] = None) -> None:
    """
    Record a security-relevant action. Examples of `action` values in use:
    "login", "register", "admin:get_stats", "admin:upgrade_user",
    "admin:downgrade_user", "admin:delete_user", "admin:push_telegram".
    """
    try:
        conn = _get_db()
        # The live audit_logs.created_at column has no DEFAULT set (unlike
        # the aspirational one in database/schema.sql), so it stays NULL
        # unless we supply it ourselves here.
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, ip_address, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (user_id, action, ip_address),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Audit log write failed for action=%s user_id=%s: %s", action, user_id, e)


def get_recent_logs(limit: int = 100):
    """Used by the admin dashboard to show a recent audit trail."""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, user_id, action, ip_address, created_at "
            "FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("Audit log read failed: %s", e)
        return []
