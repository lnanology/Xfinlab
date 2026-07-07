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

    # Pro 用戶無限制
    if plan == "pro":
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
