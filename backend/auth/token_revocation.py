"""
JWT revocation store (2026-09-14 security audit gap #2 -- "JWTs are fully
stateless: once issued, a token is valid for its full 7-day life with no way
to invalidate it early, even on explicit logout or a password reset").

Option A (chosen over switching to short-lived access + refresh tokens):
purely additive -- no change to the JWT payload shape any existing caller
reads (`payload["sub"]`/`payload["id"]`), no change to token lifetime, no
frontend change required. Two independent revocation paths, both checked by
jwt_handler.verify_token() -- the single choke point every one of the ~25
call sites across the codebase already funnels through:

1. Per-token revocation by `jti` (a random id now stamped on every newly
   issued token, see create_access_token) -- used by POST /auth/logout to
   kill exactly the one session that logged out, leaving the same user's
   other devices/tabs untouched.
2. Per-user revocation via an "invalidated before" cutoff timestamp keyed on
   the token's `sub` (email) -- used by the password-reset flow
   (backend/auth/password_reset.py) to invalidate EVERY session at once,
   since a password reset implies any token issued before the reset may
   have been obtained by whoever needed the reset in the first place.

Tokens issued before this change (or by a process that hasn't picked up the
new jwt_handler.py yet) simply have no `jti`/`iat` claim -- both checks below
treat that as "not revoked" rather than erroring, so nobody already logged in
gets bounced by this deploy. They still expire naturally within 7 days.

Same get_db()/CREATE TABLE IF NOT EXISTS pattern as api/admin.py's
feature_flags table -- own local sqlite3 connection, no shared DB helper
(matches the rest of this codebase's per-file convention).
"""
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_revocation_tables() -> None:
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS revoked_jtis (
            jti TEXT PRIMARY KEY,
            exp INTEGER NOT NULL,
            revoked_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_token_invalidations (
            email TEXT PRIMARY KEY,
            invalidated_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_revocation_tables()  # called once at module import, same as admin.py's feature_flags init


def revoke_jti(jti: str, exp) -> None:
    """Revoke one specific token by its jti. `exp` is the token's own unix-
    timestamp `exp` claim -- keeping it alongside lets cleanup_expired_jtis()
    drop the row once the token would have expired naturally anyway, so this
    table doesn't grow forever."""
    if not jti or exp is None:
        return
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO revoked_jtis (jti, exp) VALUES (?, ?)",
        (jti, int(exp)),
    )
    conn.commit()
    conn.close()


def is_jti_revoked(jti) -> bool:
    if not jti:
        return False
    conn = get_db()
    row = conn.execute("SELECT 1 FROM revoked_jtis WHERE jti = ?", (jti,)).fetchone()
    conn.close()
    return row is not None


def revoke_all_for_email(email: str) -> None:
    """Invalidate every token issued to this email before right now. There's
    no session table to enumerate/delete individual tokens from, so this
    instead records a per-email cutoff -- verify_token() rejects any token
    whose `iat` predates it."""
    if not email:
        return
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO user_token_invalidations (email, invalidated_at) VALUES (?, ?)",
        (email, int(time.time())),
    )
    conn.commit()
    conn.close()


def is_issued_before_invalidation(email, issued_at) -> bool:
    """True if `issued_at` (a token's `iat` claim) predates the last
    revoke_all_for_email() cutoff recorded for this email -- i.e. the token
    should now be rejected."""
    if not email or issued_at is None:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT invalidated_at FROM user_token_invalidations WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    return int(issued_at) < int(row["invalidated_at"])


def cleanup_expired_jtis() -> int:
    """Housekeeping only -- delete revoked_jtis rows whose token has already
    expired naturally (an expired jti would fail the JWT library's own `exp`
    check regardless of whether it's still listed here). Safe to call
    anytime; not required for correctness."""
    conn = get_db()
    now = int(time.time())
    cur = conn.execute("DELETE FROM revoked_jtis WHERE exp < ?", (now,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted
