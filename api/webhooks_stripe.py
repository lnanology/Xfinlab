"""2026-08-19 (AJ: "Stripe同Paddle並存" -- run Stripe alongside the existing
Paddle integration, not replace it): the Stripe half of a two-provider
payment setup, sibling to api/webhooks_paddle.py. Same "dormant until real
config exists" convention throughout -- with STRIPE_SECRET_KEY unset (the
default until AJ finishes Stripe onboarding), every endpoint here safely
no-ops instead of crashing or accepting unverified requests.

Two pieces:
1. POST /stripe/create-checkout-session -- authenticated (same JWT token
   every other endpoint on this site uses), creates a real Stripe Checkout
   Session in `subscription` mode and returns the redirect URL.
   pricing.html's Upgrade buttons call this instead of the old "coming
   soon" alert.
2. POST /webhooks/stripe -- Stripe-signed webhook receiver. Listens for
   `checkout.session.completed` (first successful payment -- grants the
   plan immediately) and `invoice.paid` with
   billing_reason=="subscription_cycle" (every renewal after the first --
   extends plan_expires_at by one billing period).

Plan/price mapping is fully generic, not hardcoded to "pro": pricing.html
sells 4 real, backend-enforced tiers (basic/pro/proplus/professional --
see services/token_quota_service.py's PLAN_TOKEN_PCT), each independently
monthly or annual, so this looks up env vars by pattern
`STRIPE_PRICE_ID_{PLAN}_{CYCLE}` (e.g. STRIPE_PRICE_ID_PRO_MONTHLY,
STRIPE_PRICE_ID_PROPLUS_ANNUAL) rather than a fixed dict -- a tier goes
live the moment its price ID env var is set, no code change needed. The
one hardcoded special case is pro+annual, which reuses
services/referral_service.py's mark_annual_pro_payment() (real 1-year
expiry + referral reward) -- the exact same function api/webhooks_paddle.py
and admin.html's manual "mark annual pro" button already call, so an
annual Pro sale behaves identically no matter which of the three paths
(admin button / Paddle / Stripe) triggered it. Every other plan/cycle
combo just sets plan + a rolling plan_expires_at directly.

Field names below follow Stripe's documented Checkout/Billing API shape
as of this writing. Like webhooks_paddle.py, this has NOT been verified
against a real captured webhook payload yet -- use Stripe's dashboard
"Send test webhook" feature (Developers -> Webhooks -> your endpoint ->
Send test event) to confirm before relying on it for real charges.
"""
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from services.plan_grant_service import grant_plan, VALID_PLANS, VALID_CYCLES

router = APIRouter()
logger = logging.getLogger("xfinlab.webhooks.stripe")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SITE_URL = os.getenv("SITE_URL", "https://www.xfinlab.com")


def _price_id_for(plan: str, cycle: str) -> str:
    return os.getenv(f"STRIPE_PRICE_ID_{plan.upper()}_{cycle.upper()}", "")


def _stripe():
    """Lazy import + configure -- keeps `stripe` an optional dependency at
    module-import time (mirrors this codebase's "dormant until
    configured" posture elsewhere) rather than setting stripe.api_key at
    load time before STRIPE_SECRET_KEY is necessarily populated."""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


@router.get("/stripe/status")
def stripe_status():
    """Public, no secrets -- lets pricing.html know which plan/cycle
    combos are actually live yet, so it can show a real checkout button
    only for tiers AJ has finished configuring, and fall back to the old
    'coming soon' message for the rest instead of a confusing 503."""
    if not STRIPE_SECRET_KEY:
        return {"enabled": False, "live_price_keys": []}
    live = []
    for plan in VALID_PLANS:
        for cycle in VALID_CYCLES:
            if _price_id_for(plan, cycle):
                live.append(f"{plan}-{cycle}")
    return {"enabled": True, "live_price_keys": live}


@router.post("/stripe/create-checkout-session")
async def create_checkout_session(request: Request):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")

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
            detail=f"Stripe price ID for {plan}/{cycle} is not configured yet",
        )

    stripe = _stripe()
    meta = {"xfinlab_user_id": str(user_id), "xfinlab_plan": plan, "xfinlab_cycle": cycle}
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            # 2026-08-21 fix: AJ's account has Stripe Managed Payments
            # enabled by default, which now handles payment method
            # selection itself and REJECTS an explicit payment_method_types
            # list with a 400 ("Unsupported parameter: payment_method_types
            # ... Managed Payments ... handles this parameter for you") --
            # confirmed via Railway deploy logs during AJ's first live test
            # checkout. Omitting it lets Stripe/Managed Payments choose.
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=str(user_id),
            customer_email=email,
            subscription_data={"metadata": meta},
            metadata=meta,
            success_url=f"{SITE_URL}/pricing.html?stripe=success",
            cancel_url=f"{SITE_URL}/pricing.html?stripe=cancelled",
        )
    except Exception as e:
        logger.warning(f"[stripe_checkout] session creation failed for user {user_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not start Stripe checkout, please try again")

    return {"status": "ok", "checkout_url": session.url}


def _resolve_meta(data: dict) -> dict:
    metadata = data.get("metadata") or {}
    uid_raw = metadata.get("xfinlab_user_id") or data.get("client_reference_id")
    plan = (metadata.get("xfinlab_plan") or "").strip().lower()
    cycle = (metadata.get("xfinlab_cycle") or "monthly").strip().lower()
    try:
        user_id = int(uid_raw) if uid_raw is not None else None
    except (TypeError, ValueError):
        user_id = None
    return {"user_id": user_id, "plan": plan if plan in VALID_PLANS else None, "cycle": cycle}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    raw_body = await request.body()

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning(
            "[stripe_webhook] received event but STRIPE_WEBHOOK_SECRET is not "
            "set -- ignoring. Set it once the Stripe webhook endpoint is "
            "created in the Stripe dashboard to activate automatic plan upgrades."
        )
        return {"status": "ignored", "reason": "STRIPE_WEBHOOK_SECRET not configured"}

    sig_header = request.headers.get("stripe-signature", "")
    stripe = _stripe()
    try:
        # 2026-08-21 fix: AJ's first real webhook delivery crashed here --
        # stripe==15.5.1's construct_event() returns a stripe.Event object,
        # not a plain dict, and this SDK version's Event deliberately
        # blocks .get() ("'get' is a dict method, but a Event is not a
        # dict... Use .to_dict() to convert it" -- Railway deploy logs,
        # AttributeError at this exact line). .to_dict() up front so every
        # .get() below (already written assuming a plain dict, matching
        # webhooks_paddle.py's convention) keeps working unchanged.
        event = stripe.Webhook.construct_event(raw_body, sig_header, STRIPE_WEBHOOK_SECRET).to_dict()
    except Exception as e:
        logger.warning(f"[stripe_webhook] signature verification failed: {e}")
        return {"status": "rejected", "reason": "invalid signature"}

    event_type = event.get("type", "")
    data = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        meta = _resolve_meta(data)
        if meta["user_id"] is None or meta["plan"] is None:
            logger.warning(f"[stripe_webhook] checkout.session.completed: incomplete metadata {meta!r}, skipping")
            return {"status": "skipped", "reason": "missing xfinlab_user_id/xfinlab_plan"}
        result = grant_plan(meta["user_id"], meta["plan"], meta["cycle"])
        logger.info(f"[stripe_webhook] checkout.session.completed: {result['action']} for user {meta['user_id']}")
        return {"status": "ok", **result}

    if event_type == "invoice.paid" and data.get("billing_reason") == "subscription_cycle":
        sub_id = data.get("subscription")
        meta = {"user_id": None, "plan": None, "cycle": "monthly"}
        if sub_id:
            try:
                # Same stripe.Event .get()-blocking behavior applies to
                # every other StripeObject in this SDK version -- .to_dict()
                # here too, same reasoning as above.
                sub = stripe.Subscription.retrieve(sub_id).to_dict()
                meta = _resolve_meta({"metadata": sub.get("metadata") or {}})
            except Exception as e:
                logger.warning(f"[stripe_webhook] invoice.paid: could not resolve subscription {sub_id}: {e}")
        if meta["user_id"] is None or meta["plan"] is None:
            logger.warning("[stripe_webhook] invoice.paid renewal: no resolvable plan/user, skipping")
            return {"status": "skipped", "reason": "missing xfinlab_user_id/xfinlab_plan"}
        if meta["cycle"] == "annual":
            # Annual renewals are once/year and already got their real
            # expiry from checkout.session.completed -- no action needed,
            # and re-running it would double-fire the pro+annual referral
            # reward every year on the same subscription.
            return {"status": "ignored", "reason": "annual renewal, already handled at checkout"}
        result = grant_plan(meta["user_id"], meta["plan"], "monthly")
        logger.info(f"[stripe_webhook] invoice.paid renewal: {result['action']} for user {meta['user_id']}")
        return {"status": "ok", **result}

    return {"status": "ignored", "reason": f"event_type {event_type!r} not handled"}
