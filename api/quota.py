import os
from fastapi import APIRouter, HTTPException
from services.quota_service import QuotaService
from backend.auth.jwt_handler import verify_token

router = APIRouter()

@router.get("/quota/usage")
def get_usage(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return QuotaService.get_usage(payload["id"])

@router.get("/quota/check/{feature}")
def check_quota(feature: str, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    import sqlite3
    from services.quota_middleware import resolve_real_plan
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT plan, plan_expires_at FROM users WHERE id=?", (payload["id"],)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return QuotaService.check(payload["id"], resolve_real_plan(row), feature)
