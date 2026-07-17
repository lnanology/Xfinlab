from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.auth.jwt_handler import verify_token
from services.push_service import (
    VAPID_PUBLIC_KEY_B64,
    save_subscription,
    remove_subscription,
)

router = APIRouter()


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionPayload(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribePayload(BaseModel):
    endpoint: str


@router.get("/push/vapid-public-key")
def get_vapid_public_key():
    return {"key": VAPID_PUBLIC_KEY_B64}


@router.post("/push/subscribe")
def subscribe(payload: SubscriptionPayload, token: Optional[str] = None):
    # Free Signals is guest-visible too, so subscribing doesn't require
    # login -- token is optional. If a valid token IS supplied, we tie
    # the subscription to the user id (mainly for future per-user alert
    # types); anonymous subscriptions still get pushed the daily
    # broadcast the same as everyone else.
    user_id = None
    if token:
        verified = verify_token(token)
        if verified:
            user_id = verified.get("id")

    try:
        save_subscription(payload.dict(), user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "subscribed"}


@router.post("/push/unsubscribe")
def unsubscribe(payload: UnsubscribePayload):
    remove_subscription(payload.endpoint)
    return {"status": "unsubscribed"}
