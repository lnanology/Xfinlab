from fastapi import APIRouter, HTTPException
from backend.auth.jwt_handler import verify_token
from services.achievement_service import get_achievements

router = APIRouter()


@router.get("/achievements/status")
def achievements_status(token: str):
    """
    Read-only status for the achievements/badges UI (account/dashboard
    page): total active days, current/longest streak, unlocked badges,
    and the single nearest not-yet-unlocked badge. Works for every plan
    (free and paid) -- see services/quota_middleware.py's record_activity()
    call sites for how usage gets counted regardless of tier.
    """
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return get_achievements(payload["id"])
