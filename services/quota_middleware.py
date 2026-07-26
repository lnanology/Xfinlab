import sqlite3
import os
from fastapi import HTTPException

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_and_increment(token: str, feature: str):
    """
    2026-07-16 product decision: the old flat "5 analyses/day" style cap
    this function used to enforce for free-plan users has been REPLACED
    by the site-wide points system (services/points_service.py) -- a
    logged-in free user is never hard-blocked by this function anymore;
    every call just earns a point toward a temporary Basic upgrade.
    Kept the same function name/signature (still called from
    api/full_analysis_v3.py, api/research.py, api/report.py) so no
    caller needed to change, and still raises the exact same
    HTTPException shape as before if this is ever re-tightened -- but
    under the current design that branch is unreachable for free users.
    """
    if not token:
        # 未登入用戶 → 允許但唔記錄
        return True

    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        return True

    user_id = payload.get("id")

    # 取得用戶 plan
    conn = get_db()
    user = conn.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if not user:
        return True

    plan = user["plan"]

    from services.points_service import get_effective_plan, record_and_check
    effective_plan = get_effective_plan(user_id, plan)

    if effective_plan != "free":
        # Paid plan (real Basic/Pro/Pro+/Professional, OR a free user
        # currently on a points-earned temporary Basic boost) --
        # unlimited on this old per-feature daily-count system, same as
        # the pre-existing pro/starter-unlimited convention.
        return True

    # Still genuinely free with no active boost -- record the point,
    # never block.
    record_and_check(user_id)
    return True


def check_token_budget(token: str):
    """
    Pre-flight check for the monthly AI-token quota (Basic/Pro/Pro+/
    Professional's real per-plan monthly token budget; see
    services/token_quota_service.py). Enterprise/unrecognized plans
    aren't metered by this system at all (pricing.html only promises
    Enterprise "Custom API rate limits", handled outside this system).

    Free-plan users are normally not metered here at all (their usage
    is governed by the points system instead -- see
    services/points_service.py and check_and_increment() above), UNLESS
    they currently have an active points-earned temporary Basic
    upgrade, in which case they're metered exactly like a real paying
    Basic subscriber for the duration of that upgrade -- earning the
    upgrade grants the real thing, budget included.

    Returns the user_id to credit tokens to afterwards via
    record_ai_token_usage(), or None if this call isn't metered here
    (no/invalid token, or a plan this system doesn't gate). Raises
    HTTPException(429) if the plan's monthly token budget is already
    exhausted -- same {"error": "quota_exceeded", ...} shape as
    check_and_increment() so js/quota.js's existing 429 handler covers
    this without any frontend changes.
    """
    if not token:
        return None

    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        return None

    user_id = payload.get("id")

    conn = get_db()
    user = conn.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if not user:
        return None

    plan = user["plan"]
    from services.points_service import get_effective_plan, record_and_check
    effective_plan = get_effective_plan(user_id, plan)

    if plan == "free" and effective_plan == "free":
        # Still genuinely free with no active boost -- this call isn't
        # token-metered, but it does earn a point.
        record_and_check(user_id)
        return None

    from services.token_quota_service import check_token_quota
    result = check_token_quota(user_id, effective_plan)

    if not result["metered"]:
        return None

    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "message": f"本月 AI token 額度已用完（已用 {result['pct_used']}%）",
                "used": result["used"],
                "budget": result["budget"],
                "upgrade_url": "https://xfinlab.com/pricing.html",
                "feature": "ai_tokens",
            },
        )

    return user_id


def record_ai_token_usage(user_id) -> None:
    """Call once, right after a get_ai_response()/get_vision_response()
    call, with the user_id check_token_budget() returned (may be None,
    in which case this is a no-op)."""
    if not user_id:
        return
    from ai.ai_router import get_last_usage_tokens
    from services.token_quota_service import record_tokens
    record_tokens(user_id, get_last_usage_tokens())


# 2026-07-26 product decision (Basic-tier psychological limitation): 7
# "advanced engine" features -- Agent Debate, Decision Journal, Smart Beta,
# Backtest stats, Scenario Lab, Market Regime probability, Multi-Timeframe/
# Market Structure -- are reserved for Pro tier and above. Free and Basic
# (including a free user's temporary points-earned Basic boost) do not
# qualify; this is deliberate, matching the pricing-psychology request to
# make Basic "obviously lighter" than Pro so it drives upgrades.
ADVANCED_ENGINE_PLANS = {"pro", "proplus", "professional"}


def _resolve_effective_plan(token: str):
    """Shared helper -- returns (user_id, effective_plan). Never raises;
    an invalid/missing token or unknown user resolves to (None, "free")."""
    if not token:
        return None, "free"
    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        return None, "free"
    user_id = payload.get("id")
    conn = get_db()
    user = conn.execute("SELECT plan FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None, "free"
    from services.points_service import get_effective_plan
    return user_id, get_effective_plan(user_id, user["plan"])


def is_advanced_engine_plan(token: str) -> bool:
    """Soft check (never raises) -- True only for real Pro/Pro+/Professional
    (a temporary points-earned Basic boost does NOT count). Use this where a
    locked/upgrade-teaser placeholder is preferable to a hard error, e.g.
    redacting just the smart_beta/scenario/regime fields inside
    api/ai_analysis.py's combined response instead of failing the whole
    request for Basic users."""
    _, effective_plan = _resolve_effective_plan(token)
    return effective_plan in ADVANCED_ENGINE_PLANS


def require_advanced_engine_plan(token: str):
    """Hard gate -- raises HTTPException(403) if the caller isn't on a
    real Pro/Pro+/Professional plan. Use for standalone advanced-engine
    endpoints (Agent Debate, Decision Journal) where there's no partial
    response to fall back to. Same upgrade_url shape as
    check_token_budget()'s 429 so the frontend can handle both with one
    upgrade-prompt path."""
    if not is_advanced_engine_plan(token):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_upgrade_required",
                "message": "此功能需要 Pro 或以上方案",
                "upgrade_url": "https://xfinlab.com/pricing.html",
                "required_plan": "pro",
            },
        )
