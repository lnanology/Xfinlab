"""
Web Push notification helper (pywebpush + VAPID).

MVP scope: only one notification type exists today -- "today's free
signals are ready" (see api/market_pulse.py's free_signals() cache
refresh hook). Kept intentionally generic (send_push / send_push_to_all
take an arbitrary payload dict) so future alert types (price alerts,
anomaly alerts, etc.) can reuse the same subscription table and send
path without changes here.

VAPID keypair lives in services/vapid_keys/{private_key,public_key}.pem
(checked into the repo for now, same "fail open to a working default"
pragmatism as backend/auth/jwt_handler.py's JWT_SECRET fallback -- this
is an MVP; rotate to env-var-supplied keys before this matters for
production security hardening). VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY_B64
env vars override the checked-in files when present.
"""
import os
import sqlite3
import base64

from pywebpush import webpush, WebPushException

_HERE = os.path.dirname(os.path.abspath(__file__))
_PRIVATE_KEY_PATH = os.path.join(_HERE, "vapid_keys", "private_key.pem")

# Raw uncompressed EC point (0x04 || X || Y), base64url, matching the
# checked-in private_key.pem -- this is what the frontend passes as
# PushManager.subscribe()'s applicationServerKey, and it's also served
# back verbatim via GET /api/push/vapid-public-key so the frontend never
# has to hardcode it.
VAPID_PUBLIC_KEY_B64 = os.getenv(
    "VAPID_PUBLIC_KEY_B64",
    "BIUZmWx1A6AzP4yjbqPxFegxJYC5zAT0HJyK_6HsHJN2XAcIZvFjefMrttkRGAKwFLfJSerNNXWb0Pzft9KwkVc",
)
VAPID_CLAIMS = {"sub": "mailto:support@xfinlab.com"}


def _private_key_source():
    env_key = os.getenv("VAPID_PRIVATE_KEY")
    if env_key:
        return env_key
    return _PRIVATE_KEY_PATH


def _db_path():
    return os.path.join(_HERE, "..", "xfinlab.db")


def ensure_push_table():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        # Tiny persisted marker so "send once per calendar day" survives
        # process restarts/redeploys -- the in-memory free-signals cache
        # (_free_signals_cache_date in api/market_pulse.py) does NOT
        # survive restarts, so relying on that alone would re-fire a
        # push every time the process restarts on the same day.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS push_send_log (
                notification_key TEXT PRIMARY KEY,
                sent_date TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def already_sent_today(notification_key: str, today: str) -> bool:
    ensure_push_table()
    conn = sqlite3.connect(_db_path())
    try:
        row = conn.execute(
            "SELECT sent_date FROM push_send_log WHERE notification_key = ?",
            (notification_key,),
        ).fetchone()
        return bool(row) and row[0] == today
    finally:
        conn.close()


def mark_sent_today(notification_key: str, today: str):
    ensure_push_table()
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            INSERT INTO push_send_log (notification_key, sent_date) VALUES (?, ?)
            ON CONFLICT(notification_key) DO UPDATE SET sent_date=excluded.sent_date
            """,
            (notification_key, today),
        )
        conn.commit()
    finally:
        conn.close()


def save_subscription(subscription_info: dict, user_id=None):
    ensure_push_table()
    endpoint = subscription_info.get("endpoint")
    keys = subscription_info.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not endpoint or not p256dh or not auth:
        raise ValueError("Incomplete subscription payload")

    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth
            """,
            (user_id, endpoint, p256dh, auth),
        )
        conn.commit()
    finally:
        conn.close()


def remove_subscription(endpoint: str):
    ensure_push_table()
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        conn.commit()
    finally:
        conn.close()


def _all_subscriptions():
    ensure_push_table()
    conn = sqlite3.connect(_db_path())
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def send_push(subscription_row: dict, payload_json: str) -> bool:
    """Send one push message. Returns False (and cleans up the row) if
    the endpoint is gone (410/404), True on success, True on other
    transient failures (best-effort, don't want a flaky push provider
    to look like a broken feature)."""
    subscription_info = {
        "endpoint": subscription_row["endpoint"],
        "keys": {"p256dh": subscription_row["p256dh"], "auth": subscription_row["auth"]},
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=payload_json,
            vapid_private_key=_private_key_source(),
            vapid_claims=dict(VAPID_CLAIMS),
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            remove_subscription(subscription_row["endpoint"])
            return False
        return True
    except Exception:
        return True


def send_push_to_all(payload: dict):
    """Best-effort fan-out. Never raises -- a push-send failure must
    never break the /api/free-signals response it's piggybacking on."""
    import json

    payload_json = json.dumps(payload)
    for row in _all_subscriptions():
        try:
            send_push(row, payload_json)
        except Exception:
            continue
