"""
Growth OS Phase 3 -- Email Engine API surface.

Public endpoints (subscribe/confirm/unsubscribe) need no auth -- anyone
visiting free-signals.html can opt in. Confirm/unsubscribe are GET
endpoints because they're meant to be clicked directly from an email
link, not called via fetch().
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from services.email_digest_service import subscribe, confirm, unsubscribe

router = APIRouter()


class SubscribePayload(BaseModel):
    email: str


_PAGE_STYLE = (
    "font-family:Arial,sans-serif;max-width:480px;margin:80px auto;"
    "background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;text-align:center"
)


@router.post("/email/subscribe")
def email_subscribe(payload: SubscribePayload, request: Request):
    try:
        result = subscribe(payload.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/email/confirm", response_class=HTMLResponse)
def email_confirm(token: str):
    ok = confirm(token)
    if ok:
        body = "<h1 style='color:#00d4ff'>訂閱已確認 ✓</h1><p>多謝訂閱！你會喺每日開市後收到XFINLAB嘅免費市場訊號。</p>"
    else:
        body = "<h1 style='color:#f59e0b'>連結無效或已過期</h1><p>請重新喺 xfinlab.com/free-signals.html 訂閱一次。</p>"
    return f"<div style='{_PAGE_STYLE}'>{body}<p style='margin-top:24px'><a href='https://www.xfinlab.com/free-signals.html' style='color:#00d4ff'>返回 XFINLAB</a></p></div>"


@router.get("/email/unsubscribe", response_class=HTMLResponse)
def email_unsubscribe(token: str):
    ok = unsubscribe(token)
    if ok:
        body = "<h1 style='color:#94a3b8'>已退訂</h1><p>你已成功退訂XFINLAB每日訊號email，隨時可以再訂閱返。</p>"
    else:
        body = "<h1 style='color:#f59e0b'>連結無效</h1><p>搵唔到呢個訂閱記錄。</p>"
    return f"<div style='{_PAGE_STYLE}'>{body}<p style='margin-top:24px'><a href='https://www.xfinlab.com/free-signals.html' style='color:#00d4ff'>返回 XFINLAB</a></p></div>"
