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

2026-08-19 (AJ: "Stripe同Paddle並存"): added the checkout-creation half
(POST /paddle/create-checkout-session, mirroring api/webhooks_stripe.py's
endpoint of the same name) and generalized the webhook's plan resolution
from a hardcoded "pro" to any of pricing.html's 4 real, backend-enforced
tiers (basic/pro/proplus/professional -- see services/token_quota_service
.py's PLAN_TOKEN_PCT), sharing the exact same grant logic as Stripe via
services/plan_grant_service.py. The env var names for the pro tier
(PADDLE_PRICE_ID_PRO_MONTHLY/PADDLE_PRICE_ID_PRO_ANNUAL) are unchanged --
they already matched the new generalized `PADDLE_PRICE_ID_{PLAN}_{CYCLE}`
pattern, so this is a non-breaking extension, not a migration.

Field names below (event_type, data.custom_data, data.items[].price.id,
etc.) follow Paddle Billing's documented webhook/Transactions API shape
as of this writing. They are NOT yet verified against a real captured
payload -- there is no live Paddle sandbox account in this session to
test against -- so treat this as "should work, verify against Paddle's
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

import requests
from fastapi import APIRouter, HTTPException, Request

from services.plan_grant_service import grant_plan, VALID_PLANS, VALID_CYCLES

router = APIRouter()
logger = logging.getLogger("xfinlab.webhooks.paddle")

PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")

# Server-side API key for CREATING transactions (Paddle dashboard ->
# Developer Tools -> Authentication) -- distinct from PADDLE_WEBHOOK_SECRET
# above, which only verifies INCOMING webhook signatures. Also dormant:
# /paddle/create-checkout-session 503s until this is set.
PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_ENV = os.getenv("PADDLE_ENV", "sandbox")  # "sandbox" or "production"
PADDLE_API_BASE = (
    "https://api.paddle.com" if PADDLE_ENV == "production" else "https://sandbox-api.paddle.com"
)
SITE_URL = os.getenv("SITE_URL", "https://www.xfinlab.com")

# Map your real Paddle Billing price IDs here once they exist (Paddle
# dashboard -> Catalog -> Prices). Generalized pattern
# PADDLE_PRICE_ID_{PLAN}_{CYCLE} -- PADDLE_PRICE_ID_PRO_MONTHLY/
# PADDLE_PRICE_ID_PRO_ANNUAL are the same two names this file has always
# used, the other 6 (basic/proplus/professional x monthly/annual) are new
# and equally dormant-safe (empty by default). Until a given combo's env
# var is set, that tier simply isn't offered/recognized yet -- same
# posture as the rest of this file.


def _price_id_for(plan: str, cycle: str) -> str:
    return os.getenv(f"PADDLE_PRICE_ID_{plan.upper()}_{cycle.upper()}", "")


def _reverse_price_lookup(price_id: str):
    """Fallback for webhook events that don't carry custom_data.xfinlab_plan
    (e.g. a transaction created manually in the Paddle dashboard rather
    than via /paddle/create-checkout-session below) -- matches the raw
    Paddle price_id back to a (plan, cycle) pair by checking every real
    tier's configured env var."""
    for plan in VALID_PLANS:
        for cycle in VALID_CYCLES:
            if price_id and _price_id_for(plan, cycle) == price_id:
                return plan, cycle
    return None, None


@router.get("/paddle/status")
def paddle_status():
    """Public, no secrets -- mirrors /stripe/status so pricing.html can
    show a real checkout button only for tiers AJ has actually configured
    in both PADDLE_API_KEY and that tier's price ID env var."""
    if not PADDLE_API_KEY:
        return {"enabled": False, "live_price_keys": []}
    live = []
    for plan in VALID_PLANS:
        for cycle in VALID_CYCLES:
            if _price_id_for(plan, cycle):
                live.append(f"{plan}-{cycle}")
    return {"enabled": True, "live_price_keys": live}


@router.post("/paddle/create-checkout-session")
async def create_checkout_session(request: Request):
    """Creates a real Paddle transaction via the REST API and returns its
    hosted checkout.url -- same "create server-side, redirect the browser"
    shape as api/webhooks_stripe.py's endpoint of the same name, so
    pricing.html's frontend code can treat both providers identically."""
    if not PADDLE_API_KEY:
        raise HTTPException(status_code=503, detail="Paddle is not configured yet")

    body = await request.json()
    token = body.get("token", "")
    plan = (body.get("plan") or "").strip().lower()
    cycle = (body.get("cycle") or "monthly").strip().lower()

    if plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan {plan!r}")
    if cycle not in VALID_CYCLES:
        raise HTTPException(status_code=400, detail=f"Unknown billing cycle {cycle!r}")

    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("id")
    email = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    price_id = _price_id_for(plan, cycle)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Paddle price ID for {plan}/{cycle} is not configured yet",
        )

    custom_data = {"xfinlab_user_id": str(user_id), "xfinlab_plan": plan, "xfinlab_cycle": cycle}
    try:
        resp = requests.post(
            f"{PADDLE_API_BASE}/transactions",
            headers={
                "Authorization": f"Bearer {PADDLE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "items": [{"price_id": price_id, "quantity": 1}],
                "customer": {"email": email} if email else None,
                "custom_data": custom_data,
                "checkout": {"url": f"{SITE_URL}/pricing.html?paddle=return"},
            },
            timeout=15,
        )
        resp.raise_for_status()
        checkout_url = (resp.json().get("data") or {}).get("checkout", {}).get("url")
    except Exception as e:
        logger.warning(f"[paddle_checkout] transaction creation failed for user {user_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not start Paddle checkout, please try again")

    if not checkout_url:
        logger.warning(f"[paddle_checkout] transaction created but no checkout.url in response for user {user_id}")
        raise HTTPException(status_code=502, detail="Could not start Paddle checkout, please try again")

    return {"status": "ok", "checkout_url": checkout_url}


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
    `custom_data: {"xfinlab_user_id": <id>}` -- set automatically by
    /paddle/create-checkout-session above for every real checkout this
    site initiates. Falls back to None (caller skips) if missing."""
    custom_data = data.get("custom_data") or {}
    uid = custom_data.get("xfinlab_user_id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_plan_cycle(data: dict):
    """Prefers custom_data.xfinlab_plan/xfinlab_cycle (set by this file's
    own checkout endpoint above) -- falls back to reverse-matching the raw
    Paddle price_id against the configured env vars for any transaction
    that didn't go through /paddle/create-checkout-session (e.g. one
    created manually in the Paddle dashboard for testing)."""
    custom_data = data.get("custom_data") or {}
    plan = (custom_data.get("xfinlab_plan") or "").strip().lower()
    cycle = (custom_data.get("xfinlab_cycle") or "monthly").strip().lower()
    if plan in VALID_PLANS and cycle in VALID_CYCLES:
        return plan, cycle

    items = data.get("items") or []
    for item in items:
        price = item.get("price") or {}
        price_id = price.get("id")
        if price_id:
            plan, cycle = _reverse_price_lookup(price_id)
            if plan:
                return plan, cycle
    return None, None


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

    plan, cycle = _resolve_plan_cycle(data)
    if plan is None:
        logger.warning(f"[paddle_webhook] {event_type}: could not resolve plan/cycle, skipping")
        return {"status": "skipped", "reason": "unrecognized plan/price_id"}

    # Paddle fires transaction.completed/subscription.activated on both the
    # initial sale AND every renewal (no separate "renewal" event type like
    # Stripe's invoice.paid) -- calling grant_plan() again on a real annual
    # renewal a year later is correct, not a bug: for pro+annual it re-runs
    # ReferralService.mark_annual_pro_payment(), which extends plan_expires_at
    # another year (exactly what a renewal should do) while its own
    # mark_paid_conversion() call stays idempotent per referred user, so the
    # one-time referral reward can never be double-granted. For monthly
    # combos, grant_plan() always sets a fresh rolling ~35-day expiry, which
    # is the intended behavior on every single charge, initial or renewal.
    result = grant_plan(user_id, plan, cycle)
    logger.info(f"[paddle_webhook] {event_type}: {result['action']} for user {user_id}")
    return {"status": "ok", "action": result["action"], **{k: v for k, v in result.items() if k != "action"}}
