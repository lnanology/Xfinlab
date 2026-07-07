import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from services.email_service import EmailService

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_verification_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            verified INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    # 加 verified 欄位入 users table
    try:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
    except:
        pass
    conn.commit()
    conn.close()

init_verification_table()


def send_verification_email(user_id: int, email: str, name: str):
    """產生驗證 token 並發送驗證郵件"""
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        "INSERT INTO email_verifications (user_id, token) VALUES (?, ?)",
        (user_id, token)
    )
    conn.commit()
    conn.close()

    verify_link = f"https://xfinlab.com/verify-email.html?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#080c14;color:#e2e8f0;padding:40px;border-radius:12px;">
        <h1 style="color:#00d4ff;">驗證你的電郵</h1>
        <p>你好 {name}，</p>
        <p>感謝你註冊 XFINLAB！請點擊以下連結驗證你的電郵地址：</p>
        <a href="{verify_link}" style="background:#00d4ff;color:#000;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;margin:16px 0;">驗證電郵</a>
        <p style="color:#64748b;font-size:0.85rem;">如果你沒有註冊 XFINLAB，請忽略此郵件。</p>
    </div>
    """
    try:
        EmailService.send(email, "驗證你的 XFINLAB 帳號", html)
    except:
        pass


@router.get("/auth/verify-email")
def verify_email(token: str):
    conn = get_db()
    record = conn.execute(
        "SELECT * FROM email_verifications WHERE token=? AND verified=0",
        (token,)
    ).fetchone()

    if not record:
        conn.close()
        raise HTTPException(status_code=400, detail="無效或已使用的驗證連結")

    conn.execute("UPDATE email_verifications SET verified=1 WHERE token=?", (token,))
    conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (record["user_id"],))
    conn.commit()
    conn.close()

    return {"status": "ok", "message": "電郵驗證成功！"}


@router.post("/auth/resend-verification")
def resend_verification(body: dict):
    email = body.get("email")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()

    if not user:
        return {"status": "ok", "message": "如果帳號存在，驗證郵件已發送"}

    if user["email_verified"]:
        return {"status": "ok", "message": "電郵已經驗證過了"}

    send_verification_email(user["id"], user["email"], user["name"])
    return {"status": "ok", "message": "驗證郵件已發送"}
