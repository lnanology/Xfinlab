import sqlite3
import os
from fastapi import HTTPException
from services.quota_service import QuotaService

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_and_increment(token: str, feature: str):
    """
    Check quota and increment if allowed.
    Raises HTTPException if quota exceeded.
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

    # Pro/Starter 用戶無限制（同services/quota_service.py::check()一致，
    # 見嗰邊註解 -- pricing.html由Starter層開始就承諾「Unlimited」）
    if plan in ("pro", "starter"):
        return True

    # 檢查 quota
    result = QuotaService.check(user_id, plan, feature)

    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "message": f"今日 {feature} 額度已用完（{result['limit']} 次/日）",
                "used": result["used"],
                "limit": result["limit"],
                "upgrade_url": "https://xfinlab.com/pricing.html",
                "feature": feature
            }
        )

    # 增加使用量
    QuotaService.increment(user_id, feature)
    return True


def check_token_budget(token: str):
    """
    Pre-flight check for the monthly AI-token quota (Basic/Pro/Pro+/
    Professional's "AI token quota: X% of full usage" promise on
    pricing.html; see services/token_quota_service.py). Free tier stays
    gated by the existing daily feature-count check_and_increment()
    above (unchanged); Enterprise/unrecognized plans aren't metered by
    this system at all (pricing.html only promises Enterprise "Custom
    API rate limits", handled outside this system).

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

    from services.token_quota_service import check_token_quota
    result = check_token_quota(user_id, user["plan"])

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
