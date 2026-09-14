"""
Recall Alert -- no-code public signup/unsubscribe endpoints -- 2026-09-15
(see services/recall_alert_service.py's module docstring for the full
"why this is separate from the developer API+webhook version" story).

Deliberately mirrors api/feedback.py's shape: a public POST with no API
key required, a Pydantic body, tolerant of bad input (returns a
{"ok": False, "error": ...} shape rather than a 4xx for the common
"forgot to fill in a field" case), never raises past this router.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from services import recall_alert_service

router = APIRouter()


class RecallAlertSubscribeRequest(BaseModel):
    email: str
    keyword: str


@router.post("/recall-alerts/subscribe")
async def subscribe_recall_alert(body: RecallAlertSubscribeRequest):
    result = recall_alert_service.subscribe(body.email, body.keyword)
    if not result.get("ok"):
        return result

    # Best-effort admin notification, same "never let a notification
    # failure break the actual signup" posture as api/feedback.py.
    try:
        from services.email_service import EmailService
        html = f"""
        <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
            <h2 style="color:#00d4ff">New Recall Alert signup</h2>
            <p><strong>Email:</strong> {body.email}</p>
            <p><strong>Keyword:</strong> {body.keyword}</p>
        </div>
        """
        EmailService.send("abcoaj888@gmail.com", "[XFINLAB] New Recall Alert signup", html)
    except Exception:
        pass

    if result.get("already_subscribed"):
        return {"ok": True, "message": "You're already subscribed to alerts for this keyword."}
    return {"ok": True, "message": "Subscribed. We'll email you when a new CPSC or FDA recall matches this keyword."}


@router.get("/recall-alerts/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_recall_alert(token: Optional[str] = None):
    ok = recall_alert_service.unsubscribe(token) if token else False
    if ok:
        body = "<h2>Unsubscribed</h2><p>You won't receive any more recall alert emails for this subscription.</p>"
    else:
        body = "<h2>Link not valid</h2><p>This unsubscribe link is invalid or was already used.</p>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>XFINLAB Recall Alerts</title></head>
    <body style="font-family:Arial,sans-serif;max-width:480px;margin:80px auto;background:#080c14;color:#e2e8f0;padding:32px;border-radius:12px;">
    {body}
    <p><a href="https://www.xfinlab.com/recall-alerts.html" style="color:#00d4ff;">Back to Recall Alerts</a></p>
    </body></html>"""
