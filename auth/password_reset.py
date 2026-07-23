# 2026-07-23 note (platform audit finding, found via ruff): this repo-root
# auth/password_reset.py is an orphaned duplicate of the real, live
# backend/auth/password_reset.py. backend/main.py's `sys.path.insert(0,
# os.path.dirname(os.path.abspath(__file__)))` adds backend/ itself to
# sys.path, so its `from auth.password_reset import router` resolves to
# backend/auth/password_reset.py, never this file -- confirmed via
# `python3 -c "import auth.password_reset as pr; print(pr.__file__)"`,
# which resolves to backend/auth/password_reset.py, not this one. This
# file was also missing `import os` (DB_PATH below used os.path.join
# without importing os -- would NameError if this file were ever actually
# imported/run on its own). Fixed the missing import for hygiene, but this
# file is not part of the live app -- left in place per this project's
# convention of not deleting files without asking.
import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.email_service import EmailService
from auth.password import hash_password

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_reset_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_reset_table()


class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (body.email,)).fetchone()

    if not user:
        conn.close()
        # 唔透露用戶是否存在，安全考慮
        return {"status": "ok", "message": "如果帳號存在，重設連結已發送到你的信箱"}

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()

    conn.execute(
        "INSERT INTO password_resets (email, token, expires_at) VALUES (?, ?, ?)",
        (body.email, token, expires_at)
    )
    conn.commit()
    conn.close()

    reset_link = f"https://xfinlab.com/reset-password.html?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
        <h1 style="color:#00d4ff;">重設密碼</h1>
        <p>你好 {user['name']}，</p>
        <p>我們收到你的密碼重設請求。點擊以下連結重設密碼（連結將在1小時後失效）：</p>
        <a href="{reset_link}" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">重設密碼</a>
        <p style="color:#64748b;font-size:0.85rem;">如果你沒有請求重設密碼，請忽略此郵件。</p>
    </div>
    """
    try:
        EmailService.send(body.email, "重設密碼 - XFINLAB", html)
    except Exception:
        pass

    return {"status": "ok", "message": "如果帳號存在，重設連結已發送到你的信箱"}


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest):
    conn = get_db()
    reset = conn.execute(
        "SELECT * FROM password_resets WHERE token=? AND used=0",
        (body.token,)
    ).fetchone()

    if not reset:
        conn.close()
        raise HTTPException(status_code=400, detail="無效或已過期的重設連結")

    expires_at = datetime.fromisoformat(reset["expires_at"])
    if datetime.now() > expires_at:
        conn.close()
        raise HTTPException(status_code=400, detail="重設連結已過期，請重新申請")

    if len(body.new_password) < 6:
        conn.close()
        raise HTTPException(status_code=400, detail="密碼至少需要6個字符")

    hashed = hash_password(body.new_password)
    conn.execute("UPDATE users SET password=? WHERE email=?", (hashed, reset["email"]))
    conn.execute("UPDATE password_resets SET used=1 WHERE token=?", (body.token,))
    conn.commit()
    conn.close()

    return {"status": "ok", "message": "密碼已成功重設，請使用新密碼登入"}
