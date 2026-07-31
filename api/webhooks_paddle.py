"""2026-08-01 ("自動化可做那裡" audit): the three plan-change endpoints in
api/admin.py (upgrade/downgrade/mark-annual-pro) are, by their own
docstrings, "manual stand-in[s] for a real payment webhook -- there is
no live Stripe/PayPal integration yet." Every single real sale currently
requires the founder to manually click a button in admin.html. This is
the other half: a real Paddle webhook endpoint that calls the exact same
underlying functions automatically once Paddle is actually wired up.

Follows the same "dormant until real config exists" convention as
services/broker_affiliate_config.py: with PADDLE_WEBHOOK_SECRET unset
(the default today), this endpoint safely no-ops (200, logs a warning)
instead of either crashing or -- far worse -- accepting unverified,
unsigned requests as real payments. It only becomes live once a real
Paddle account exists and its webhook secret is set as an env var.

Field names below (event_type, data.custom_data, data.items[].price.id,
etc.) follow Paddle Billing's documented webhook payload shape as of
this writing. They are NOT yet verified against a real captured payload
-- there is no live Paddle sandbox account in this session to test
against -- so treat this as "should work, verify against Paddle's
sandbox 'send test event' feature before relying on it in production."
Every field access below is defensive (.get() with fallbacks) specifically
because of that: a shape mismatch should degrade to "skipped, logged",
never a 500 or a silent wrong-user credit.
"""
import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger("xfinlab.webhooks.paddle")

PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")

# Map your real Paddle Billing price IDs here once they exist (Paddle
# dashboard -> Catalog -> Prices). Until then both are empty and every
# event's plan lookup below simply logs "unknown price_id, skipped" --
# same dormant-safe posture as the rest of this file.
PADDLE_PRICE_ID_PRO_MONTHLY = os.getenv("PADDLE_PRICE_ID_PRO_MONTHLY", "")
PADDLE_PRICE_ID_PRO_ANNUAL = os.getenv("PADDLE_PRICE_ID_PRO_ANNUAL", "")


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Paddle Billing signs webhooks as `Paddle-Signature: ts=<unix>;h1=<hex>`
    where h1 = HMAC-SHA256(secret, f"{ts}:{raw_body}"). Rejects anything
    that doesn't parse or match. A >5 minute clock-skew tolerance guards
    against replay of an old captured request."""
    if not signature_header:
        return False
    parts = dict(p.split("=", 1) for p in signature_header.split(";") if "=" in p)
    ts, h1 = parts.get("ts"), parts.get("h1")
    if not ts or not h1:
        return False
    try:
        if abs(time.time() - int(ts)) > 300:
            return False
    except ValueError:
        return False
    signed_payload = f"{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(PADDLE_WEBHOOK_SECRET.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, h1)


def _resolve_user_id(data: dict):
    """Expects the checkout to have been created with
    `custom_data: {"xfinlab_user_id": <id>}` -- this must be set on the
    checkout/transaction creation side (frontend or backend) whenever the
    real Paddle checkout is wired up, so the webhook knows which XFINLAB
    account to credit. Falls back to None (caller skips) if missing."""
    custom_data = data.get("custom_data") or {}
    uid = custom_data.get("xfinlab_user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_price_id(data: dict):
    items = data.get("items") or []
    for item in items:
        price = item.get("price") or {}
        if price.get("id"):
            return price["id"]
    return None


@router.post("/webhooks/paddle")
async def paddle_webhook(request: Request):
    raw_body = await request.body()

    if not PADDLE_WEBHOOK_SECRET:
        logger.warning(
            "[paddle_webhook] received event but PADDLE_WEBHOOK_SECRET is not "
            "set -- ignoring. Set it once a real Paddle account exists to "
            "activate automatic plan upgrades."
        )
        return {"status": "ignored", "reason": "PADDLE_WEBHOOK_SECRET not configured"}

    signature_header = request.headers.get("paddle-signature", "")
    if not _verify_signature(raw_body, signature_header):
        logger.warning("[paddle_webhook] signature verification failed, rejecting")
        return {"status": "rejected", "reason": "invalid signature"}

    try:
        payload = await request.json()
    except Exception:
        return {"status": "rejected", "reason": "invalid JSON"}

    event_type = payload.get("event_type", "")
    data = payload.get("data") or {}

    # Only act on events that represent a confirmed, paid transaction --
    # never on e.g. `subscription.created` alone (Paddle fires that on
    # trial start too, before any money has moved).
    PAID_EVENTS = {"transaction.completed", "subscription.activated"}
    if event_type not in PAID_EVENTS:
        return {"status": "ignored", "reason": f"event_type {event_type!r} not handled"}

    user_id = _resolve_user_id(data)
    if user_id is None:
        logger.warning(f"[paddle_webhook] {event_type}: no custom_data.xfinlab_user_id, skipping")
        return {"status": "skipped", "reason": "no xfinlab_user_id in custom_data"}

    price_id = _resolve_price_id(data)

    if price_id and PADDLE_PRICE_ID_PRO_ANNUAL and price_id == PADDLE_PRICE_ID_PRO_ANNUAL:
        # Exactly the function api/admin.py's mark-annual-pro endpoint
        # calls manually today -- real 1-year expiry + referral reward,
        # see services/referral_service.py's docstring on this function.
        from services.referral_service import ReferralService
        result = ReferralService.mark_annual_pro_payment(user_id)
        logger.info(f"[paddle_webhook] {event_type}: annual Pro granted to user {user_id}")
        return {"status": "ok", "action": "annual_pro_granted", "result": result}

    if price_id and PADDLE_PRICE_ID_PRO_MONTHLY and price_id == PADDLE_PRICE_ID_PRO_MONTHLY:
        # Recurring monthly: extend plan_expires_at by one billing period
        # on every successful charge (initial + each renewal), rather
        # than a single fixed date -- Paddle itself owns the recurring
        # schedule; this just keeps our local expiry-aware resolver
        # (services/quota_middleware.py resolve_real_plan()) in sync with
        # "still an active paying subscriber as of the last charge."
        import datetime
        import sqlite3

        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=35)).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE users SET plan='pro', plan_expires_at=? WHERE id=?", (expires_at, user_id))
        conn.commit()
        conn.close()
        logger.info(f"[paddle_webhook] {event_type}: monthly Pro renewed for user {user_id} until {expires_at}")
        return {"status": "ok", "action": "monthly_pro_renewed", "plan_expires_at": expires_at}

    logger.warning(f"[paddle_webhook] {event_type}: unrecognized price_id {price_id!r}, skipped")
    return {"status": "skipped", "reason": f"unrecognized price_id {price_id!r}"}
