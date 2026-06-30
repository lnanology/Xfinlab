from fastapi import APIRouter, Request
from services.user_analytics import UserAnalytics
from backend.auth.jwt_handler import verify_token

router = APIRouter()

@router.post("/analytics/track")
async def track_event(request: Request):
    body = await request.json()
    token = body.get("token")
    user_id = None

    if token:
        payload = verify_token(token)
        if payload:
            user_id = payload.get("id")

    UserAnalytics.track(
        event_type=body.get("event_type", "unknown"),
        event_data=body.get("event_data"),
        user_id=user_id,
        session_id=body.get("session_id"),
        page=body.get("page"),
        ip=request.client.host
    )
    return {"status": "ok"}

@router.get("/analytics/stats")
def get_stats(token: str):
    payload = verify_token(token)
    if not payload:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    return UserAnalytics.get_stats()
