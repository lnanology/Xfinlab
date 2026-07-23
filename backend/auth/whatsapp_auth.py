"""
WhatsApp OTP login (task #332).

Uses the WhatsApp Cloud API directly (Meta's own endpoint, not a paid
BSP wrapper like Twilio) -- consistent with this project's established
"call the real API directly instead of paying a markup middleman"
pattern already used for Telegram (services/telegram_push_service.py).

IMPORTANT -- this needs manual one-time setup in Meta Business Manager
before it can actually send anything (code alone isn't enough, same as
the Telegram bot needing to be manually added as a channel admin):
  1. A WhatsApp Business Account + a phone number added to it.
  2. An "Authentication" category message template created and APPROVED
     by Meta (usually approved within minutes to a few hours). Meta
     requires the exact shape: one body variable for the code, e.g.
     body text "{{1}} is your XFINLAB verification code."
  3. A permanent System User access token with whatsapp_business_messaging
     permission.
  4. Env vars: WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN,
     WHATSAPP_OTP_TEMPLATE_NAME, WHATSAPP_OTP_TEMPLATE_LANG (e.g. "en").

Until those are set, /api/auth/whatsapp/send-otp returns 503 rather than
silently failing.
"""
import os
import sqlite3
import secrets
import requests
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Request

from backend.auth.jwt_handler import create_access_token
from auth.password import hash_password
from services.audit_log_service import log_action
from services.request_ip import get_client_ip

router = APIRouter()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "xfinlab.db")

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5

WHATSAPP_API_BASE = "https://graph.facebook.com/v20.0"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_otps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # Same additive, idempotent ALTER TABLE pattern as
    # backend/auth/social_login.py's _ensure_oauth_columns() -- duplicated
    # (rather than imported) so this file works standalone regardless of
    # which of the two modules happens to get imported first.
    for stmt in (
        "ALTER TABLE users ADD COLUMN oauth_provider TEXT",
        "ALTER TABLE users ADD COLUMN oauth_id TEXT",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()


_ensure_table()


def _normalize_phone(phone: str) -> str:
    # WhatsApp Cloud API wants digits only, country code included, no
    # leading "+"/spaces/dashes (e.g. "85212345678", not "+852 1234 5678").
    return "".join(ch for ch in phone if ch.isdigit())


def _send_whatsapp_template(phone_digits: str, code: str) -> bool:
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    template_name = os.getenv("WHATSAPP_OTP_TEMPLATE_NAME")
    template_lang = os.getenv("WHATSAPP_OTP_TEMPLATE_LANG", "en")

    if not (phone_number_id and access_token and template_name):
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_digits,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
            ],
        },
    }
    try:
        res = requests.post(
            f"{WHATSAPP_API_BASE}/{phone_number_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        return res.status_code == 200
    except Exception:
        return False


@router.post("/auth/whatsapp/send-otp")
def send_whatsapp_otp(body: dict):
    phone = body.get("phone", "")
    phone_digits = _normalize_phone(phone)
    if len(phone_digits) < 8:
        raise HTTPException(status_code=400, detail="Please enter a valid phone number with country code.")

    if not (os.getenv("WHATSAPP_PHONE_NUMBER_ID") and os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_OTP_TEMPLATE_NAME")):
        raise HTTPException(status_code=503, detail="WhatsApp login is not configured on this server yet.")

    conn = get_db()
    # Cooldown: block resending within OTP_RESEND_COOLDOWN_SECONDS so a
    # button-mash can't spam-send (and burn through Meta's per-message
    # cost) for the same phone number.
    recent = conn.execute(
        "SELECT created_at FROM phone_otps WHERE phone = ? ORDER BY id DESC LIMIT 1",
        (phone_digits,),
    ).fetchone()
    if recent:
        created_at = datetime.fromisoformat(recent["created_at"].replace(" ", "T")).replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
            conn.close()
            raise HTTPException(status_code=429, detail="Please wait before requesting another code.")

    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()

    sent = _send_whatsapp_template(phone_digits, code)
    if not sent:
        conn.close()
        raise HTTPException(status_code=502, detail="Could not send WhatsApp message. Please try again later.")

    conn.execute(
        "INSERT INTO phone_otps (phone, code, expires_at) VALUES (?, ?, ?)",
        (phone_digits, code, expires_at),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Verification code sent via WhatsApp."}


@router.post("/auth/whatsapp/verify-otp")
def verify_whatsapp_otp(body: dict, request: Request):
    phone = body.get("phone", "")
    code = (body.get("code") or "").strip()
    phone_digits = _normalize_phone(phone)
    if not phone_digits or not code:
        raise HTTPException(status_code=400, detail="Phone and code are required.")

    conn = get_db()
    record = conn.execute(
        "SELECT * FROM phone_otps WHERE phone = ? AND verified = 0 ORDER BY id DESC LIMIT 1",
        (phone_digits,),
    ).fetchone()

    if not record:
        conn.close()
        raise HTTPException(status_code=400, detail="No pending verification for this number. Please request a new code.")

    if record["attempts"] >= OTP_MAX_ATTEMPTS:
        conn.close()
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new code.")

    expires_at = datetime.fromisoformat(record["expires_at"].replace(" ", "T")).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        conn.close()
        raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")

    if record["code"] != code:
        conn.execute("UPDATE phone_otps SET attempts = attempts + 1 WHERE id = ?", (record["id"],))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect code.")

    conn.execute("UPDATE phone_otps SET verified = 1 WHERE id = ?", (record["id"],))

    # Find-or-create a user keyed by phone. Reuses the same
    # "synthetic-but-stable placeholder email" technique as LINE accounts
    # without an email scope grant (see backend/auth/social_login.py) --
    # keeps the existing users.email UNIQUE NOT NULL constraint untouched.
    placeholder_email = f"whatsapp_{phone_digits}@phone.xfinlab.internal"
    row = conn.execute("SELECT * FROM users WHERE phone = ? OR email = ?", (phone_digits, placeholder_email)).fetchone()
    if row:
        if not row["phone_verified"]:
            conn.execute("UPDATE users SET phone_verified = 1, phone = ? WHERE id = ?", (phone_digits, row["id"]))
            conn.commit()
    else:
        placeholder_password = hash_password(secrets.token_urlsafe(32))
        cursor = conn.execute(
            "INSERT INTO users (email, password, name, phone, phone_verified) VALUES (?, ?, ?, ?, 1)",
            (placeholder_email, placeholder_password, f"User {phone_digits[-4:]}", phone_digits),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()

    conn.close()

    token = create_access_token({"sub": row["email"], "id": row["id"]})
    log_action(row["id"], "login:whatsapp", get_client_ip(request))
    return {
        "status": "ok",
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "plan": row["plan"],
        "token": token,
    }
