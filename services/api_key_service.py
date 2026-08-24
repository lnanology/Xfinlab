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

V1 is admin-issued only for paid tiers (see api/intelligence.py's
/intelligence/admin/issue-key, gated by api.admin.verify_admin) -- no
Stripe/Paddle billing wired up yet, so Pro/Enterprise stay manual.

2026-07-31: Free tier now has automated self-serve issuance (see
issue_self_serve_free_key below), added to close that specific gap while
paid-tier billing is still unbuilt. It deliberately lives in its own
self_serve_api_keys table rather than reusing api_keys/users -- a public,
unauthenticated signup shouldn't require (or silently create) a full
XFINLAB consumer account, and keeping it in a separate table means this
change is purely additive: zero schema changes to the tables the
admin-issued flow already depends on in production.
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
        if row:
            conn.execute(
                "UPDATE api_keys SET last_used_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), row["id"]),
            )
            conn.commit()
            return {"valid": True, "user_id": row["user_id"], "tier": row["tier"]}

        # 2026-07-31: fallback to the self-serve free-tier table (see
        # issue_self_serve_free_key below) -- kept as a second lookup here
        # rather than merging tables, so this stays the single
        # verification entrypoint api/intelligence.py calls regardless of
        # which flow issued the key.
        row2 = conn.execute(
            "SELECT * FROM self_serve_api_keys WHERE key=? AND active=1", (key,)
        ).fetchone()
        if row2:
            # 2026-08-24 (self-serve Pro API billing): paid self-serve keys
            # carry an expires_at (subscription period end, refreshed by
            # the Stripe webhook on renewal -- see issue_self_serve_paid_key
            # below). Free-tier keys keep expires_at NULL and never hit
            # this branch. An expired row is treated like no row at all --
            # we don't flip active=0 here (a renewal can still land later
            # and should just extend expires_at), just refuse to verify it.
            if row2["expires_at"]:
                try:
                    expired = datetime.fromisoformat(row2["expires_at"]) < datetime.utcnow()
                except Exception:
                    expired = False
                if expired:
                    return {"valid": False}
            conn.execute(
                "UPDATE self_serve_api_keys SET last_used_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), row2["id"]),
            )
            conn.commit()
            return {"valid": True, "user_id": None, "tier": row2["tier"]}

        return {"valid": False}
    finally:
        conn.close()


def get_email_for_key(key: str) -> "str | None":
    """2026-08-18 (quota-exceeded upgrade nudge): the one lookup neither
    verify_key() nor anything else in this file exposes -- given a raw key,
    return the email to notify, or None if the key is unknown/inactive.
    Checks self_serve_api_keys first (email is stored directly there),
    then falls back to api_keys -> users (admin-issued keys only carry a
    user_id, so this needs the join). Never raises; a lookup failure just
    means no nudge gets sent, not a broken request."""
    if not key:
        return None
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT email FROM self_serve_api_keys WHERE key=? AND active=1", (key,)
        ).fetchone()
        if row:
            return row["email"]

        row2 = conn.execute(
            """
            SELECT u.email AS email
            FROM api_keys k JOIN users u ON u.id = k.user_id
            WHERE k.key=? AND k.active=1
            """,
            (key,),
        ).fetchone()
        if row2:
            return row2["email"]

        return None
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


# ---------------------------------------------------------------------------
# 2026-08-09 (task #724, AJ "全做" batch): logged-in-user self-service key
# view/regenerate for dashboard.html's account area. Reuses the same
# api_keys table + "raw key shown once" posture as issue_key()/revoke_key()
# above -- this is NOT a new issuance flow, just a user-facing wrapper: a
# regenerate is "revoke my own active key(s), then issue_key() a fresh one",
# scoped strictly to the caller's own user_id (never touches other users'
# rows, unlike the admin endpoints which take an arbitrary email).
# ---------------------------------------------------------------------------

def get_my_key_status(email: str) -> dict:
    """For the dashboard account panel: never returns a raw key (none of
    the existing rows have it retained -- see issue_key()'s docstring), just
    whether the user has one and its masked preview/tier/dates."""
    keys = list_keys_for_email(email)
    active = [k for k in keys if k["active"]]
    if not active:
        return {"has_key": False}
    k = active[0]
    return {
        "has_key": True,
        "key_preview": k["key_preview"],
        "tier": k["tier"],
        "created_at": k["created_at"],
        "last_used_at": k["last_used_at"],
    }


def regenerate_key_for_user(email: str, tier: str = "free") -> dict:
    """Revokes every active api_keys row owned by `email`'s user_id, then
    issues a brand new one. Returns the same shape as issue_key() (raw key
    included -- shown once, exactly like every other issuance path in this
    file)."""
    conn = _get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            return {"error": f"No user found with email {email}"}
        conn.execute(
            "UPDATE api_keys SET active=0 WHERE user_id=? AND active=1", (user["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    return issue_key(email, tier)


# ---------------------------------------------------------------------------
# 2026-07-31: Self-serve Free-tier automation (Task #575).
#
# Separate table on purpose -- see module docstring. Nothing above this
# line is touched or altered; verify_key() below gets one additive
# fallback check so api/intelligence.py keeps calling a single
# verify_key() regardless of which table actually issued the key.
# ---------------------------------------------------------------------------

SELF_SERVE_SIGNUP_DAILY_LIMIT_PER_IP = 5


def _init_self_serve_tables():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_serve_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            tier TEXT DEFAULT 'free',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            last_used_at TEXT
        )
    """)
    # 2026-08-24 (self-serve Pro API billing): NULL for the Free tier (no
    # expiry, same as before), set to a real timestamp for a paid tier --
    # see issue_self_serve_paid_key() below. Guarded ALTER so this is a
    # no-op on a DB that already has the column, same convention as every
    # other incremental-column addition in this codebase.
    try:
        conn.execute("ALTER TABLE self_serve_api_keys ADD COLUMN expires_at TEXT")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_serve_signup_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            UNIQUE(ip, date)
        )
    """)
    conn.commit()
    conn.close()


_init_self_serve_tables()


def check_self_serve_signup_rate(ip: str) -> bool:
    """Read-only -- True if `ip` still has budget to request a free
    self-serve key today. Call record_self_serve_signup_attempt()
    separately after an actual attempt (check-then-increment split, same
    convention as services/intelligence_quota_service.py), so this doesn't
    burn budget on a request that fails validation before ever reaching
    here."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT count FROM self_serve_signup_attempts WHERE ip=? AND date=?",
            (ip, today),
        ).fetchone()
        used = row["count"] if row else 0
        return used < SELF_SERVE_SIGNUP_DAILY_LIMIT_PER_IP
    finally:
        conn.close()


def record_self_serve_signup_attempt(ip: str):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    conn = _get_db()
    conn.execute(
        """
        INSERT INTO self_serve_signup_attempts (ip, date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(ip, date) DO UPDATE SET count = count + 1
        """,
        (ip, today),
    )
    conn.commit()
    conn.close()


def issue_self_serve_free_key(email: str) -> dict:
    """Public, unauthenticated free-tier issuance -- does NOT require a
    pre-existing `users` row (unlike issue_key() above, which is for
    admin-issued keys tied to a full XFINLAB consumer account). Tracked in
    self_serve_api_keys, keyed directly by email.

    Exactly one active self-serve key per email: a repeat signup silently
    deactivates any prior self-serve key(s) for that email before issuing a
    fresh one. The raw key is only ever shown once (emailed at issuance,
    same "never retrievable later" posture as issue_key()) -- re-signup is
    the recovery path for a lost key, there's nothing to "re-show"."""
    email = (email or "").strip().lower()
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE self_serve_api_keys SET active=0 WHERE email=? AND active=1",
            (email,),
        )
        key = generate_key()
        conn.execute(
            "INSERT INTO self_serve_api_keys (email, key, tier, active) VALUES (?, ?, 'free', 1)",
            (email, key),
        )
        conn.commit()
        return {"key": key, "tier": "free", "email": email}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2026-08-24: Self-serve PAID-tier issuance (Intelligence API Pro checkout).
#
# Mirrors issue_self_serve_free_key() above -- same table, same "one active
# self-serve key per email" posture -- but carries an expires_at so the key
# stops working if the Stripe subscription lapses. Called from the
# checkout.session.completed / invoice.paid webhook branches in
# api/webhooks_stripe.py, same as every other paid-grant path in that file.
# On renewal (invoice.paid on an existing subscription), the webhook calls
# this again with the same email/tier -- it re-issues a fresh key each time,
# same as a Free re-signup would. That's a deliberate simplification (no key
# rotation nagging for a renewal), not an oversight.
# ---------------------------------------------------------------------------

def issue_self_serve_paid_key(email: str, tier: str, days: int) -> dict:
    """Public issuance for a Stripe-paid Intelligence API tier (currently
    just 'pro'). Deactivates any prior self-serve key(s) for that email
    first, exactly like issue_self_serve_free_key(), then issues a fresh
    key with expires_at = now + days."""
    email = (email or "").strip().lower()
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE self_serve_api_keys SET active=0 WHERE email=? AND active=1",
            (email,),
        )
        key = generate_key()
        from datetime import timedelta
        expires_at = (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat()
        conn.execute(
            "INSERT INTO self_serve_api_keys (email, key, tier, active, expires_at) VALUES (?, ?, ?, 1, ?)",
            (email, key, tier, expires_at),
        )
        conn.commit()
        return {"key": key, "tier": tier, "email": email, "expires_at": expires_at}
    finally:
        conn.close()
