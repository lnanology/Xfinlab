"""
One-time startup migration — fixes a real production bug found 2026-07-11.

backend/auth/auth.py, backend/auth/email_verification.py, and
backend/auth/password_reset.py all computed their DB_PATH as:

    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

For a file at backend/auth/auth.py, that resolves to backend/xfinlab.db —
NOT the repo-root xfinlab.db that litestream.yml backs up to Cloudflare R2
(`/app/xfinlab.db`) and that api/admin.py, services/quota_middleware.py,
services/audit_log_service.py etc. all read/write. Since backend/auth/* is
the module that actually handles the live /api/auth/register and
/api/auth/login endpoints (confirmed via import resolution — backend/auth/
has its own __init__.py, so it shadows the root-level auth/ package
entirely), every user who registered before this fix was live only exists
in backend/xfinlab.db:
    - invisible to the admin dashboard (api/admin.py reads root xfinlab.db)
    - NOT covered by the Litestream backup (which only watches root xfinlab.db)

This migration merges any `users` rows that exist in the legacy
backend/xfinlab.db but not in the canonical root xfinlab.db, matched by
email, so nobody who already registered loses the ability to log in once
the DB_PATH bug itself is fixed. Idempotent and safe to run on every
startup: no-ops entirely if the legacy file doesn't exist or has nothing
new to merge.
"""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DB = os.path.join(_HERE, "..", "xfinlab.db")
LEGACY_BACKEND_DB = os.path.join(_HERE, "..", "backend", "xfinlab.db")


def migrate_legacy_backend_db() -> None:
    if not os.path.exists(LEGACY_BACKEND_DB):
        return

    try:
        legacy = sqlite3.connect(LEGACY_BACKEND_DB)
        legacy.row_factory = sqlite3.Row
        root = sqlite3.connect(ROOT_DB)
        root.row_factory = sqlite3.Row

        try:
            legacy_users = legacy.execute("SELECT * FROM users").fetchall()
        except sqlite3.OperationalError:
            legacy.close()
            root.close()
            return  # no users table in the legacy file — nothing to do

        migrated = 0
        for u in legacy_users:
            existing = root.execute(
                "SELECT id FROM users WHERE email = ?", (u["email"],)
            ).fetchone()
            if existing:
                continue
            root.execute(
                "INSERT INTO users (email, password, name, plan, created_at, email_verified) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    u["email"],
                    u["password"],
                    u["name"],
                    u["plan"] if "plan" in u.keys() else "free",
                    u["created_at"] if "created_at" in u.keys() else None,
                    u["email_verified"] if "email_verified" in u.keys() else 0,
                ),
            )
            migrated += 1

        root.commit()
        if migrated:
            logger.warning(
                "db_migration: merged %d user(s) from legacy backend/xfinlab.db "
                "into canonical root xfinlab.db (see services/db_migration.py "
                "docstring for why this exists)",
                migrated,
            )
        legacy.close()
        root.close()
    except Exception as e:
        # Never let a migration hiccup take down app startup.
        logger.warning("db_migration: legacy user merge failed (non-fatal): %s", e)


def migrate_audit_logs_nullable_user_id() -> None:
    """
    Security & Operations Layer, Phase 2 follow-up (2026-07-11).

    audit_logs.user_id was NOT NULL, which meant services/audit_log_service.py
    could only log actions with a known, authenticated user -- successful
    logins, registrations, admin actions. The single most useful security
    signal (repeated FAILED login attempts, i.e. brute-force / credential
    stuffing) couldn't be recorded at all, because there's no user_id for a
    failed login.

    SQLite has no ALTER COLUMN, so relaxing a NOT NULL constraint means
    rebuilding the table: create a new one with the same columns but
    user_id nullable, copy all rows across, drop the old one, rename.
    Idempotent -- checks PRAGMA table_info first and no-ops if user_id is
    already nullable, so it's safe to call on every startup.
    """
    try:
        conn = sqlite3.connect(ROOT_DB)
        cols = conn.execute("PRAGMA table_info(audit_logs)").fetchall()
        if not cols:
            conn.close()
            return  # table doesn't exist yet -- nothing to migrate

        user_id_col = next((c for c in cols if c[1] == "user_id"), None)
        if user_id_col is None or user_id_col[3] == 0:
            # notnull flag (index 3) already 0, or column missing entirely
            conn.close()
            return

        conn.execute("""
            CREATE TABLE audit_logs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                ip_address TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO audit_logs_new (id, user_id, action, ip_address, created_at) "
            "SELECT id, user_id, action, ip_address, created_at FROM audit_logs"
        )
        conn.execute("DROP TABLE audit_logs")
        conn.execute("ALTER TABLE audit_logs_new RENAME TO audit_logs")
        conn.commit()
        conn.close()
        logger.warning(
            "db_migration: audit_logs.user_id relaxed to nullable -- "
            "failed login attempts can now be logged (see "
            "services/db_migration.py docstring)"
        )
    except Exception as e:
        logger.warning("db_migration: audit_logs nullable-user_id migration failed (non-fatal): %s", e)
