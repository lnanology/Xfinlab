"""2026-08-01 ("自動化可做那裡" -- automation audit): the plan_expires_at
column (task #479) already exists and services/quota_middleware.py's
resolve_real_plan() already demotes a user back to Free automatically
once their date passes -- but nobody ever gets told it's *about* to
happen. A paying user's Pro/annual-Pro subscription can silently lapse
with zero warning, which is a pure, avoidable churn/revenue leak: some
of those users would have renewed if reminded, and right now there is
no code path that tells them.

This closes that gap: a daily job finds users whose plan expires within
PLAN_EXPIRY_REMINDER_DAYS days, and notifies each one exactly once per
expiry date via email (always available -- every user has a verified
email) and web push (best-effort, only if they've subscribed). This is
read-only against the users/plan tables -- it never changes anyone's
plan; services/quota_middleware.py's existing expiry logic is untouched.
"""
import datetime
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# How many days out to warn. 3 days gives enough runway to renew before
# the automatic demotion in quota_middleware.resolve_real_plan() kicks in,
# without spamming people a month in advance.
PLAN_EXPIRY_REMINDER_DAYS = 3


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _already_notified(conn, notif_key: str) -> bool:
    """Dedup key is per (user_id, plan_expires_at) so each renewal cycle
    gets exactly one reminder -- distinct from push_service.py's
    already_sent_today(), which dedupes per-calendar-day instead (wrong
    shape here: we want "once per expiry", not "once per day")."""
    row = conn.execute(
        "SELECT 1 FROM push_send_log WHERE notification_key = ?", (notif_key,)
    ).fetchone()
    return row is not None


def _mark_notified(conn, notif_key: str):
    today = datetime.date.today().isoformat()
    conn.execute(
        """INSERT INTO push_send_log (notification_key, sent_date) VALUES (?, ?)
           ON CONFLICT(notification_key) DO UPDATE SET sent_date=excluded.sent_date""",
        (notif_key, today),
    )
    conn.commit()


def check_and_notify_expiring_plans():
    """Entry point for the daily scheduled job in backend/main.py. Never
    raises -- a bug here must never take down the scheduler thread or
    any request handler."""
    try:
        from services.push_service import ensure_push_table, send_push, _db_path
        import json as _json

        ensure_push_table()

        conn = _db()
        now = datetime.datetime.utcnow()
        horizon = (now + datetime.timedelta(days=PLAN_EXPIRY_REMINDER_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        rows = conn.execute(
            """SELECT id, email, name, plan, plan_expires_at FROM users
               WHERE plan != 'free' AND plan_expires_at IS NOT NULL
               AND plan_expires_at <= ? AND plan_expires_at >= ?""",
            (horizon, now_str),
        ).fetchall()

        for row in rows:
            notif_key = f"plan_expiry_reminder:{row['id']}:{row['plan_expires_at']}"
            if _already_notified(conn, notif_key):
                continue

            expires_date = row["plan_expires_at"].split(" ")[0]
            plan_label = (row["plan"] or "pro").upper()

            # Email -- always attempted, works regardless of push opt-in.
            try:
                from services.email_service import EmailService
                if row["email"]:
                    html = f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
                        <h1 style="color:#f59e0b;">你的 {plan_label} 方案即將到期 ⏰</h1>
                        <p>你好 {row['name'] or ''}，</p>
                        <p>你的 XFINLAB {plan_label} 方案將於 <strong>{expires_date}</strong> 到期，到期後帳戶會自動轉回 Free 方案。</p>
                        <a href="https://www.xfinlab.com/pricing.html" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">續期</a>
                    </div>
                    """
                    EmailService.send(row["email"], f"你的 XFINLAB {plan_label} 方案即將到期", html)
            except Exception:
                pass

            # Push -- best-effort, only if this user has a subscription
            # tied to their account (push_subscriptions.user_id).
            try:
                sub = conn.execute(
                    "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ? LIMIT 1",
                    (row["id"],),
                ).fetchone()
                if sub:
                    payload = _json.dumps({
                        "title": f"你的 {plan_label} 方案即將到期",
                        "body": f"將於 {expires_date} 到期，續期以繼續使用全部功能。",
                        "url": "/pricing.html",
                    })
                    send_push(dict(sub), payload)
            except Exception:
                pass

            _mark_notified(conn, notif_key)

        conn.close()
    except Exception:
        pass
