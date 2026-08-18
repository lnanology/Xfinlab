import sqlite3
import os
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_feedback_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            email TEXT,
            user_id INTEGER,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_feedback_table()


class FeedbackRequest(BaseModel):
    type: str
    message: str
    email: Optional[str] = None
    token: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    user_id = None
    if body.token:
        from backend.auth.jwt_handler import verify_token
        payload = verify_token(body.token)
        if payload:
            user_id = payload.get("id")

    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (type, message, email, user_id) VALUES (?, ?, ?, ?)",
        (body.type, body.message, body.email, user_id)
    )
    conn.commit()
    conn.close()

    # 發送通知 email 給 admin
    try:
        from services.email_service import EmailService
        html = f"""
        <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
            <h2 style="color:#00d4ff">新用戶反饋 [{body.type}]</h2>
            <p><strong>類型：</strong>{body.type}</p>
            <p><strong>內容：</strong>{body.message}</p>
            <p><strong>Email：</strong>{body.email or 'N/A'}</p>
            <p><strong>用戶ID：</strong>{user_id or 'Guest'}</p>
        </div>
        """
        EmailService.send("abcoaj888@gmail.com", f"[XFINLAB] 新反饋: {body.type}", html)
    except Exception:
        pass

    return {"status": "ok", "message": "感謝你的反饋！我們會盡快回覆。"}


@router.get("/feedback/list")
def get_feedback(token: str, request: Request, type: Optional[str] = None):
    """
    2026-07-30 addition: optional `type` filter, backward compatible --
    omitting it returns every row exactly as before. Added so the
    Intelligence API "Request Early Access" form (which inserts rows here
    with type="intelligence_early_access", see api/intelligence.py) can be
    listed separately from general bug-report/feature-request feedback in
    admin.html, without needing its own dedicated table.

    2026-08-18 fix (AJ saw inconsistent errors on admin.html -- Feature
    Flags panel said "401: Invalid token" while this panel said "403:
    Admin only" for what turned out to be the exact same expired
    adminToken): this endpoint used to do its own ad-hoc
    verify_token()+sub-email check, collapsing "token doesn't decode at
    all" and "token decodes but isn't the admin" into a single 403 --
    unlike every other admin endpoint in api/admin.py, which uses the
    shared verify_admin() helper and reports those as 401 vs 403
    respectively. Switched to verify_admin() so the error code/message is
    consistent with the rest of the admin panel, and so this endpoint
    also gets the IP-allowlist check and audit-log entry every other
    admin action already gets (it was silently skipping both before).
    The actual root cause of AJ's specific 401/403s is unrelated to this
    inconsistency -- see backend/auth/jwt_handler.py: JWT_SECRET isn't
    set in the deployment env, so a fresh random signing secret is
    generated on every backend restart, invalidating every existing
    token (including the admin session) until it's set permanently.
    """
    from api.admin import verify_admin
    verify_admin(token, "get_feedback", request)

    conn = get_db()
    if type:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE type = ? ORDER BY created_at DESC LIMIT 50",
            (type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    conn.close()
    return {"feedback": [dict(r) for r in rows]}
