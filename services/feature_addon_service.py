"""2026-08-24 (AJ: "AI辯論 à la carte解鎖" -- Basic/Free用戶唔使跳去成個Pro+
plan,一口價/月費就解鎖單一個Pro+ advanced engine): a per-user, per-feature
grant, sibling to services/points_service.py's `temp_upgrades` table but
scoped to ONE feature_key instead of an entire plan tier. temp_upgrades
can't be reused directly here -- it's PRIMARY KEY(user_id), one row per
user, because it always grants a whole plan; a user could plausibly buy
TWO different addons (e.g. agent_debate AND smart_beta) at once, so this
needs one row per (user, feature) instead.

feature_key values match services/quota_middleware.py's
ADVANCED_ENGINE_PLANS-gated features (agent_debate is the first one wired
up -- see api/agent_debate.py -- others can be added the same way later:
smart_beta, scenario_lab, market_regime, multi_timeframe, decision_journal,
backtest_stats).

Billing side: api/webhooks_stripe.py's addon checkout path calls
grant_addon() from its checkout.session.completed / invoice.paid handlers,
exactly mirroring how services/plan_grant_service.py's grant_plan() is
called for real plan purchases -- same "dormant until a real price ID is
configured" posture, see that file's docstring.
"""
import os
import sqlite3
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_feature_addon_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_addons (
            user_id INTEGER NOT NULL,
            feature_key TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            granted_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, feature_key)
        )
    """)
    conn.commit()
    conn.close()


init_feature_addon_table()


def _now():
    return datetime.datetime.utcnow()


def _parse(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def has_active_addon(user_id, feature_key: str) -> bool:
    """Soft check, never raises -- False for any missing/expired/invalid
    row, same "fail closed" posture as points_service's active-upgrade
    check."""
    if not user_id:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT expires_at FROM feature_addons WHERE user_id=? AND feature_key=?",
        (user_id, feature_key),
    ).fetchone()
    conn.close()
    if not row:
        return False
    try:
        return _parse(row["expires_at"]) > _now()
    except (ValueError, TypeError):
        return False


def grant_addon(user_id: int, feature_key: str, days: int) -> str:
    """Grant/extend a single-feature unlock. Same stacking behavior as
    points_service.grant_temp_upgrade(): if there's an active grant for
    this exact feature already, extends from its current expiry (a
    renewal payment adds another `days` on top) rather than resetting the
    clock; otherwise starts counting from now. Returns the resulting
    expires_at string."""
    conn = get_db()
    now = _now()
    existing = conn.execute(
        "SELECT expires_at FROM feature_addons WHERE user_id=? AND feature_key=?",
        (user_id, feature_key),
    ).fetchone()

    base_from = now
    if existing:
        try:
            cur_expiry = _parse(existing["expires_at"])
            if cur_expiry > now:
                base_from = cur_expiry
        except (ValueError, TypeError):
            pass

    expires_at = _fmt(base_from + datetime.timedelta(days=days))
    conn.execute("""
        INSERT INTO feature_addons (user_id, feature_key, expires_at, granted_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, feature_key) DO UPDATE SET
            expires_at = excluded.expires_at, granted_at = excluded.granted_at
    """, (user_id, feature_key, expires_at, _fmt(now)))
    conn.commit()
    conn.close()
    return expires_at


def get_user_addons(user_id: int) -> list:
    """All of this user's currently-active addons -- used by the frontend
    to show "already unlocked" state instead of the buy button."""
    if not user_id:
        return []
    conn = get_db()
    rows = conn.execute(
        "SELECT feature_key, expires_at FROM feature_addons WHERE user_id=?",
        (user_id,),
    ).fetchall()
    conn.close()
    now = _now()
    out = []
    for r in rows:
        try:
            if _parse(r["expires_at"]) > now:
                out.append({"feature_key": r["feature_key"], "expires_at": r["expires_at"]})
        except (ValueError, TypeError):
            continue
    return out
