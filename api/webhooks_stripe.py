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

# 2026-08-24 (AJ: "AI辯論 à la carte解鎖" -- Basic/Free用戶唔使跳去成個
# Pro+,一口價/月費就解鎖單一個advanced engine): a SEPARATE, much smaller
# monthly-recurring product line, sibling to the plan checkout above but
# granting a single services/feature_addon_service.py feature instead of
# an entire plan tier. Same "dormant until a real price ID env var
# exists" posture as the plan prices -- only agent_debate is wired up so
# far (api/agent_debate.py), more can be added here later (smart_beta,
# scenario_lab, market_regime, multi_timeframe) without touching the
# checkout/webhook plumbing below, just adding the key here.
VALID_ADDON_FEATURES = {"agent_debate", "advanced_engines_bundle"}
ADDON_GRANT_DAYS = 35  # matches plan_grant_service's monthly-plan grant window

# 2026-08-24 (AJ: "未落code嘅大嘢" -- Intelligence API self-serve Pro
# checkout, the one big undelivered code item from this session's earlier
# audit): a THIRD product line, sibling to the plan and addon checkouts
# above, but selling a self-serve Intelligence API key (see
# services/api_key_service.issue_self_serve_paid_key) instead of a
# consumer plan or feature unlock. Deliberately public/unauthenticated --
# unlike the two checkouts above, there's no JWT token here, because the
# whole point of the Intelligence API self-serve flow (intelligence-api.html)
# is that it never required a logged-in XFINLAB account (see
# api/intelligence.py's /intelligence/v1/signup free-tier path, which this
# mirrors). Identity is just the email address, same as the free tier.
# Enterprise deliberately stays on the manual /intelligence/early-access
# path -- out of scope here, per AJ's earlier scoping of that tier as
# sales-negotiated.
VALID_API_TIERS = {"pro"}
API_KEY_GRANT_DAYS = 35  # matches ADDON_GRANT_DAYS -- one billing month's buffer


def _price_id_for(plan: str, cycle: str) -> str:
    return os.getenv(f"STRIPE_PRICE_ID_{plan.upper()}_{cycle.upper()}", "")


def _addon_price_id_for(feature: str) -> str:
    return os.getenv(f"STRIPE_PRICE_ID_ADDON_{feature.upper()}", "")


def _api_price_id_for(tier: str) -> str:
    return os.getenv(f"STRIPE_PRICE_ID_API_{tier.upper()}", "")


def get_account_status() -> dict:
    """2026-08-24 (AJ: "點知面家個STRIPE係咪完全可收款提款無問題" -- how do
    I know the Stripe setup can actually accept payments and pay out
    with no issues). GET /stripe/status above only reports whether
    STRIPE_SECRET_KEY and price ID env vars are SET -- it never asks
    Stripe whether the underlying account has actually cleared
    onboarding/KYC. This calls stripe.Account.retrieve() (no account id
    -- returns whatever account the configured API key belongs to) for
    the real, live answer: charges_enabled/payouts_enabled plus exactly
    what Stripe is still waiting on (requirements.currently_due), the
    same data shown on the Dashboard's "Activate your account" banner.
    Admin-only consumer: api/admin.py's GET /admin/stripe-account-status.
    Read-only, never raises -- a failed/misconfigured key must not break
    the admin panel, just report the failure honestly."""
    if not STRIPE_SECRET_KEY:
        return {"configured": False, "message": "STRIPE_SECRET_KEY not set"}

    key_mode = (
        "live" if STRIPE_SECRET_KEY.startswith("sk_live_")
        else "test" if STRIPE_SECRET_KEY.startswith("sk_test_")
        else "unknown"
    )
    try:
        stripe = _stripe()
        # 2026-08-24 fix: stripe.Account.retrieve() returns a StripeObject,
        # not a plain dict -- .get() isn't supported on it in this
        # stripe-python version (raised "'get' is a dict method, but a
        # Account is not a dict" in production). .to_dict() converts it
        # (recursively, so nested `requirements` becomes a real dict too)
        # before any .get() calls below.
        acct = stripe.Account.retrieve().to_dict()
        requirements = acct.get("requirements", {}) or {}
        return {
            "configured": True,
            "key_mode": key_mode,
            "charges_enabled": acct.get("charges_enabled"),
            "payouts_enabled": acct.get("payouts_enabled"),
            "details_submitted": acct.get("details_submitted"),
            "currently_due": requirements.get("currently_due", []),
            "past_due": requirements.get("past_due", []),
            "pending_verification": requirements.get("pending_verification", []),
            "disabled_reason": requirements.get("disabled_reason"),
            "current_deadline": requirements.get("current_deadline"),
            "country": acct.get("country"),
            "default_currency": acct.get("default_currency"),
        }
    except Exception as e:
        logger.exception("stripe.get_account_status: Account.retrieve() failed")
        return {"configured": True, "key_mode": key_mode, "error": str(e)}


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
        return {"enabled": False, "live_price_keys": [], "live_addon_keys": []}
    live = []
    for plan in VALID_PLANS:
        for cycle in VALID_CYCLES:
            if _price_id_for(plan, cycle):
                live.append(f"{plan}-{cycle}")
    # 2026-08-24: lets ai-analysis.html's debate-locked state know whether
    # to offer a standalone "unlock AI辯論" button at all -- same "only
    # show a real, configured checkout, never a coming-soon dead button"
    # posture as the plan checkout above.
    live_addons = [f for f in VALID_ADDON_FEATURES if _addon_price_id_for(f)]
    # 2026-08-24: lets intelligence-api.html's Pro plan card know whether to
    # offer real Stripe checkout yet or fall back to the old manual
    # "Request Early Access" path -- same dormant-safe posture as the plan
    # and addon lists above.
    live_api_tiers = [t for t in VALID_API_TIERS if _api_price_id_for(t)]
    return {"enabled": True, "live_price_keys": live, "live_addon_keys": live_addons, "live_api_tiers": live_api_tiers}


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


@router.post("/stripe/create-addon-checkout-session")
async def create_addon_checkout_session(request: Request):
    """2026-08-24: sibling to create_checkout_session() above, but for a
    single à la carte feature unlock (see services/feature_addon_service.py)
    instead of a full plan. Deliberately its own endpoint rather than a
    branch inside the plan one -- the two sell fundamentally different
    things (a whole plan vs one feature) and mixing their request/response
    shapes would make both harder to read."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")

    body = await request.json()
    token = body.get("token", "")
    feature = (body.get("feature") or "").strip().lower()

    if feature not in VALID_ADDON_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unknown addon feature {feature!r}")

    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("id")
    email = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    price_id = _addon_price_id_for(feature)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Stripe price ID for addon {feature!r} is not configured yet",
        )

    stripe = _stripe()
    meta = {"xfinlab_user_id": str(user_id), "xfinlab_addon_feature": feature}
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=str(user_id),
            customer_email=email,
            subscription_data={"metadata": meta},
            metadata=meta,
            success_url=f"{SITE_URL}/ai-analysis.html?stripe=addon_success&feature={feature}",
            cancel_url=f"{SITE_URL}/ai-analysis.html?stripe=addon_cancelled",
        )
    except Exception as e:
        logger.warning(f"[stripe_addon_checkout] session creation failed for user {user_id}/{feature}: {e}")
        raise HTTPException(status_code=502, detail="Could not start Stripe checkout, please try again")

    return {"status": "ok", "checkout_url": session.url}


@router.post("/stripe/create-api-checkout-session")
async def create_api_checkout_session(request: Request):
    """2026-08-24: Intelligence API self-serve Pro checkout -- see the
    VALID_API_TIERS block above for why this is public/unauthenticated
    (email-keyed, not JWT-keyed) unlike the two checkout endpoints above
    it. Body: {"email": "...", "tier": "pro"}. On success the webhook
    handler below issues a real API key and emails it -- this endpoint
    itself never returns a key, same "never in a JSON response" posture as
    every other key-issuance path in this codebase."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured yet")

    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    tier = (body.get("tier") or "").strip().lower()

    if "@" not in email or "." not in email.split("@")[-1] or len(email) < 5:
        raise HTTPException(status_code=400, detail="Please provide a valid email address")
    if tier not in VALID_API_TIERS:
        raise HTTPException(status_code=400, detail=f"Unknown API tier {tier!r}")

    from services.disposable_email_domains import is_disposable_email
    if is_disposable_email(email):
        raise HTTPException(status_code=400, detail="Please use a non-disposable email address")

    price_id = _api_price_id_for(tier)
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Stripe price ID for API tier {tier!r} is not configured yet",
        )

    stripe = _stripe()
    meta = {"xfinlab_api_email": email, "xfinlab_api_tier": tier}
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email,
            subscription_data={"metadata": meta},
            metadata=meta,
            success_url=f"{SITE_URL}/intelligence-api.html?stripe=api_success",
            cancel_url=f"{SITE_URL}/intelligence-api.html?stripe=api_cancelled",
        )
    except Exception as e:
        logger.warning(f"[stripe_api_checkout] session creation failed for {email}/{tier}: {e}")
        raise HTTPException(status_code=502, detail="Could not start Stripe checkout, please try again")

    return {"status": "ok", "checkout_url": session.url}


def _resolve_meta(data: dict) -> dict:
    metadata = data.get("metadata") or {}
    uid_raw = metadata.get("xfinlab_user_id") or data.get("client_reference_id")
    plan = (metadata.get("xfinlab_plan") or "").strip().lower()
    cycle = (metadata.get("xfinlab_cycle") or "monthly").strip().lower()
    # 2026-08-24: addon checkouts (create_addon_checkout_session above) set
    # xfinlab_addon_feature instead of xfinlab_plan -- surfaced here too so
    # the webhook handler below can tell the two kinds of purchase apart
    # from the same _resolve_meta() call rather than re-parsing metadata.
    addon_feature = (metadata.get("xfinlab_addon_feature") or "").strip().lower()
    # 2026-08-24: Intelligence API self-serve checkout sets
    # xfinlab_api_email/xfinlab_api_tier instead of a user_id (this flow is
    # unauthenticated -- see create_api_checkout_session above), so it's
    # surfaced as its own pair rather than forced into the user_id shape.
    api_email = (metadata.get("xfinlab_api_email") or "").strip().lower()
    api_tier = (metadata.get("xfinlab_api_tier") or "").strip().lower()
    try:
        user_id = int(uid_raw) if uid_raw is not None else None
    except (TypeError, ValueError):
        user_id = None
    return {
        "user_id": user_id,
        "plan": plan if plan in VALID_PLANS else None,
        "cycle": cycle,
        "addon_feature": addon_feature if addon_feature in VALID_ADDON_FEATURES else None,
        "api_email": api_email if (api_email and api_tier in VALID_API_TIERS) else None,
        "api_tier": api_tier if api_tier in VALID_API_TIERS else None,
    }


def _grant_api_key_and_notify(email: str, tier: str, renewal: bool) -> dict:
    """Shared by both webhook branches below -- issues/re-issues a paid
    self-serve API key and emails it. Mirrors api/intelligence.py's
    /intelligence/v1/signup email template and 'never in the JSON response'
    posture. A send failure is logged, not raised -- unlike the synchronous
    signup endpoint, there's no request to fail back to the customer here,
    this runs from an async webhook."""
    from services.api_key_service import issue_self_serve_paid_key
    from services.email_service import EmailService

    result = issue_self_serve_paid_key(email, tier, API_KEY_GRANT_DAYS)
    verb = "renewed" if renewal else "issued"
    html = f"""
    <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
        <h2 style="color:#00d4ff">Your XFINLAB Intelligence API key ({tier.capitalize()} tier)</h2>
        <p>Your Pro subscription is active. This key replaces any previous key on this email -- keep it secret; it will not be shown again.</p>
        <p style="font-family:monospace;background:#111827;padding:12px;border-radius:8px;word-break:break-all">{result['key']}</p>
        <p>Valid through: {result['expires_at']} (auto-renews with your subscription)</p>
        <p>Docs: <a href="https://www.xfinlab.com/intelligence-api.html" style="color:#00d4ff">xfinlab.com/intelligence-api.html</a> &middot; Terms: <a href="https://www.xfinlab.com/api-terms.html" style="color:#00d4ff">api-terms.html</a></p>
    </div>
    """
    try:
        EmailService.send(email, f"[XFINLAB] Your Intelligence API key ({verb})", html)
    except Exception as e:
        logger.warning(f"[stripe_webhook] API key email failed for {email}: {e}")
    return result


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
        if meta["api_email"] is not None and meta["api_tier"] is not None:
            # 2026-08-24: Intelligence API self-serve purchase -- see
            # create_api_checkout_session above. Checked first since this
            # metadata shape has no user_id at all.
            result = _grant_api_key_and_notify(meta["api_email"], meta["api_tier"], renewal=False)
            logger.info(f"[stripe_webhook] checkout.session.completed: API key issued for {meta['api_email']} ({meta['api_tier']}) until {result['expires_at']}")
            return {"status": "ok", "action": "api_key_issued", "tier": meta["api_tier"], "expires_at": result["expires_at"]}
        if meta["user_id"] is not None and meta["addon_feature"] is not None:
            # 2026-08-24: à la carte feature unlock, not a plan purchase --
            # see create_addon_checkout_session() above.
            from services.feature_addon_service import grant_addon
            expires_at = grant_addon(meta["user_id"], meta["addon_feature"], ADDON_GRANT_DAYS)
            logger.info(f"[stripe_webhook] checkout.session.completed: addon {meta['addon_feature']} granted for user {meta['user_id']} until {expires_at}")
            return {"status": "ok", "action": "addon_granted", "feature": meta["addon_feature"], "expires_at": expires_at}
        if meta["user_id"] is None or meta["plan"] is None:
            logger.warning(f"[stripe_webhook] checkout.session.completed: incomplete metadata {meta!r}, skipping")
            return {"status": "skipped", "reason": "missing xfinlab_user_id/xfinlab_plan"}
        result = grant_plan(meta["user_id"], meta["plan"], meta["cycle"])
        logger.info(f"[stripe_webhook] checkout.session.completed: {result['action']} for user {meta['user_id']}")
        return {"status": "ok", **result}

    if event_type == "invoice.paid" and data.get("billing_reason") == "subscription_cycle":
        sub_id = data.get("subscription")
        meta = {"user_id": None, "plan": None, "cycle": "monthly", "addon_feature": None, "api_email": None, "api_tier": None}
        if sub_id:
            try:
                # Same stripe.Event .get()-blocking behavior applies to
                # every other StripeObject in this SDK version -- .to_dict()
                # here too, same reasoning as above.
                sub = stripe.Subscription.retrieve(sub_id).to_dict()
                meta = _resolve_meta({"metadata": sub.get("metadata") or {}})
            except Exception as e:
                logger.warning(f"[stripe_webhook] invoice.paid: could not resolve subscription {sub_id}: {e}")
        if meta["api_email"] is not None and meta["api_tier"] is not None:
            # Intelligence API subscription renewal -- re-issue a fresh key
            # with a new expires_at, same "no rotation nagging" posture
            # documented on issue_self_serve_paid_key().
            result = _grant_api_key_and_notify(meta["api_email"], meta["api_tier"], renewal=True)
            logger.info(f"[stripe_webhook] invoice.paid renewal: API key renewed for {meta['api_email']} ({meta['api_tier']}) until {result['expires_at']}")
            return {"status": "ok", "action": "api_key_renewed", "tier": meta["api_tier"], "expires_at": result["expires_at"]}
        if meta["user_id"] is not None and meta["addon_feature"] is not None:
            # Addon renewal -- extend by the same window as the initial
            # grant (see grant_addon()'s stacking behavior).
            from services.feature_addon_service import grant_addon
            expires_at = grant_addon(meta["user_id"], meta["addon_feature"], ADDON_GRANT_DAYS)
            logger.info(f"[stripe_webhook] invoice.paid renewal: addon {meta['addon_feature']} extended for user {meta['user_id']} until {expires_at}")
            return {"status": "ok", "action": "addon_renewed", "feature": meta["addon_feature"], "expires_at": expires_at}
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
