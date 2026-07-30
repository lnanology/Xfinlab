"""2026-07-30: issuance/verification for Intelligence API keys.

IMPORTANT correction made while building this: database/db.py (a
SQLAlchemy `User`/declarative-Base layer) is NOT what the live app
actually uses -- sqlalchemy isn't even in requirements.txt, and the real
`users` table is created/managed via raw sqlite3 in
backend/auth/auth.py (schema: id, email, password, name, plan,
created_at, risk_flagged, plan_expires_at). database/db.py is dead
scaffolding nothing imports (confirmed via grep before writing this --
only tests/test_level1.py references it). This module follows the real,
live convention instead: raw sqlite3 against the same xfinlab.db file
services/quota_service.py and backend/auth/auth.py already use.

V1 is admin-issued only (see api/intelligence.py's
/intelligence/admin/issue-key, gated by api.admin.verify_admin) -- no
self-serve developer signup/Stripe billing yet.
"""
import sqlite3
import os
import secrets
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            key TEXT UNIQUE NOT NULL,
            tier TEXT DEFAULT 'free',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_used_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def generate_key() -> str:
    # "xfl_" prefix makes leaked keys greppable/identifiable in logs, same
    # idea as Stripe's "sk_live_"/GitHub's "ghp_" prefixes.
    return "xfl_" + secrets.token_urlsafe(32)


def issue_key(email: str, tier: str = "free") -> dict:
    """Returns {"error": "..."} on failure, else {"key": "...", "tier": ...,
    "user_id": ...}. The raw key is only ever returned here, at issuance
    time -- show it to the admin/developer immediately, it isn't
    retrievable later (only a preview is, via list_keys_for_email)."""
    conn = _get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            return {"error": f"No user found with email {email}"}

        key = generate_key()
        conn.execute(
            "INSERT INTO api_keys (user_id, key, tier, active) VALUES (?, ?, ?, 1)",
            (user["id"], key, tier),
        )
        conn.commit()
        return {"key": key, "tier": tier, "user_id": user["id"]}
    finally:
        conn.close()


def verify_key(key: str) -> dict:
    """Returns {"valid": False} if missing/inactive/unknown, else
    {"valid": True, "user_id":..., "tier":...}. Never raises -- callers
    (api/intelligence.py) turn a False result into a 401 themselves."""
    if not key:
        return {"valid": False}

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key=? AND active=1", (key,)
        ).fetchone()
        if not row:
            return {"valid": False}

        conn.execute(
            "UPDATE api_keys SET last_used_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
        conn.commit()
        return {"valid": True, "user_id": row["user_id"], "tier": row["tier"]}
    finally:
        conn.close()


def list_keys_for_email(email: str) -> list:
    conn = _get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            return []
        rows = conn.execute(
            "SELECT * FROM api_keys WHERE user_id=?", (user["id"],)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "tier": r["tier"],
                "active": bool(r["active"]),
                "created_at": r["created_at"],
                "last_used_at": r["last_used_at"],
                "key_preview": r["key"][:8] + "..." + r["key"][-4:],
            }
            for r in rows
        ]
    finally:
        conn.close()


def revoke_key(key_id: int) -> bool:
    conn = _get_db()
    try:
        cur = conn.execute("UPDATE api_keys SET active=0 WHERE id=?", (key_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
