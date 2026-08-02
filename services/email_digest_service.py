"""
Growth OS Phase 3 -- Email Engine.

Turns services/content_repurpose_service.py's already-generated
email_subject/email_body text (previously copy-paste-only, per that
file's own docstring) into an actual daily-sent email, using the SMTP
mailbox already configured for this project (services/email_service.py's
EmailService -- the same one that sends welcome/verify-email/password-
reset mail today via EMAIL_ADDRESS/EMAIL_APP_PASSWORD env vars). No new
SendGrid/Mailgun account needed.

Double opt-in by design (subscribe -> confirmation email -> click to
confirm) rather than sending cold to anyone who types an email into the
box. Sending unconfirmed marketing mail from a small personal-domain
mailbox risks spam-folder/blocklist problems that would also break the
transactional emails (registration, password reset) sharing the same
mailbox -- so double opt-in protects the whole account, not just this
feature.

Every subscriber row carries its own unsubscribe_token; every sent email
includes a one-click unsubscribe link built from it (CAN-SPAM/GDPR-
reasonable practice, and just good manners).
"""
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from services.email_service import EmailService

_HERE = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://www.xfinlab.com"
API_URL = "https://api.xfinlab.com"


def _db_path():
    return os.path.join(_HERE, "..", "xfinlab.db")


def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table():
    conn = _conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                confirmed INTEGER NOT NULL DEFAULT 0,
                confirm_token TEXT NOT NULL,
                unsubscribe_token TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                confirmed_at TEXT,
                unsubscribed_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _is_valid_email(email: str) -> bool:
    # Deliberately simple -- full RFC 5322 validation isn't the goal here,
    # just rejecting obvious junk before we try to send a confirmation
    # email to it (services/disposable_email_domains.py already handles
    # the "is this a throwaway domain" question for registration; this
    # digest opt-in is lower-stakes so isn't gated on that list too).
    return bool(email) and "@" in email and "." in email.split("@")[-1] and " " not in email


def subscribe(email: str) -> dict:
    """Idempotent: re-subscribing an already-pending or already-confirmed
    address just re-sends the confirmation (or, if already confirmed,
    tells the caller so) rather than erroring or creating a duplicate
    row."""
    ensure_table()
    email = email.strip().lower()
    if not _is_valid_email(email):
        raise ValueError("Invalid email address")

    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM email_subscribers WHERE email = ?", (email,)).fetchone()
        if row and row["confirmed"]:
            return {"status": "already_confirmed"}

        if row:
            confirm_token = row["confirm_token"]
        else:
            confirm_token = secrets.token_urlsafe(24)
            unsub_token = secrets.token_urlsafe(24)
            conn.execute(
                "INSERT INTO email_subscribers (email, confirm_token, unsubscribe_token) VALUES (?, ?, ?)",
                (email, confirm_token, unsub_token),
            )
            conn.commit()

        confirm_link = f"{API_URL}/api/email/confirm?token={confirm_token}"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
            <h1 style="color:#00d4ff;">確認訂閱 XFINLAB 每日訊號</h1>
            <p>你好，</p>
            <p>請按下面按鈕確認訂閱 XFINLAB 每日免費市場訊號（每日一封，隨時可退訂）：</p>
            <a href="{confirm_link}" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">確認訂閱</a>
            <p style="color:#64748b;font-size:0.85rem;">如果呢個唔係你本人操作，可以忽略呢封郵件。</p>
        </div>
        """
        EmailService.send(email, "請確認訂閱 XFINLAB 每日訊號", html)
        return {"status": "confirmation_sent"}
    finally:
        conn.close()


def confirm(token: str) -> bool:
    ensure_table()
    conn = _conn()
    try:
        row = conn.execute("SELECT id FROM email_subscribers WHERE confirm_token = ?", (token,)).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE email_subscribers SET confirmed = 1, confirmed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def unsubscribe(token: str) -> bool:
    ensure_table()
    conn = _conn()
    try:
        row = conn.execute("SELECT id FROM email_subscribers WHERE unsubscribe_token = ?", (token,)).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE email_subscribers SET confirmed = 0, unsubscribed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_stats() -> dict:
    ensure_table()
    conn = _conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM email_subscribers").fetchone()["c"]
        confirmed = conn.execute("SELECT COUNT(*) c FROM email_subscribers WHERE confirmed = 1").fetchone()["c"]
        return {"total": total, "confirmed": confirmed, "pending": total - confirmed}
    finally:
        conn.close()


def _wrap_html(subject: str, body_text: str, unsubscribe_link: str) -> str:
    body_html = body_text.replace("\n", "<br>")
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
        <h1 style="color:#00d4ff;font-size:1.3rem;">{subject}</h1>
        <p style="line-height:1.8;">{body_html}</p>
        <p style="color:#64748b;font-size:0.75rem;margin-top:32px;border-top:1px solid #1e2d45;padding-top:16px;">
            你收到呢封email係因為你訂閱咗XFINLAB每日訊號。
            <a href="{unsubscribe_link}" style="color:#64748b;">退訂</a>
        </p>
    </div>
    """


def send_daily_digest(subject: str, body_text: str) -> dict:
    """Sends the given subject/body to every confirmed subscriber.
    Best-effort per recipient -- one failed send (bad address, transient
    SMTP error) doesn't stop the rest of the batch. Returns a summary the
    admin panel / daily job can log."""
    ensure_table()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT email, unsubscribe_token FROM email_subscribers WHERE confirmed = 1"
        ).fetchall()
    finally:
        conn.close()

    sent, failed = 0, 0
    for row in rows:
        unsub_link = f"{API_URL}/api/email/unsubscribe?token={row['unsubscribe_token']}"
        html = _wrap_html(subject, body_text, unsub_link)
        ok = EmailService.send(row["email"], subject, html)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "total_confirmed": len(rows)}
