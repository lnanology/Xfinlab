from fastapi import APIRouter, HTTPException
from backend.auth.jwt_handler import verify_token
from services.points_service import get_status

router = APIRouter()


@router.get("/points/status")
def points_status(token: str):
    """
    Read-only status for the points badge (js/points-badge.js) and the
    account/dashboard page: current points in the active 7-day cycle,
    the 500-point target, and any active temporary Basic upgrade.
    Only meaningful for free-plan users -- paying users simply won't
    have accumulated points (services/quota_middleware.py only ever
    calls points_service.record_and_check() for genuinely free users),
    so this returns zeros for them rather than an error.
    """
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return get_status(payload["id"])
