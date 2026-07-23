import sqlite3
import os
from fastapi import APIRouter
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
def get_feedback(token: str):
    from backend.auth.jwt_handler import verify_token
    from fastapi import HTTPException
    payload = verify_token(token)
    if not payload or payload.get("sub") != "abcoaj888@gmail.com":
        raise HTTPException(status_code=403, detail="Admin only")

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return {"feedback": [dict(r) for r in rows]}
