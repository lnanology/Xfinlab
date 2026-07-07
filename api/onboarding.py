import os
import sqlite3
from fastapi import APIRouter
from backend.auth.jwt_handler import verify_token
from fastapi import HTTPException

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_onboarding_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onboarding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            step INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            bonus_given INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_onboarding_table()


@router.get("/onboarding/status")
def get_onboarding_status(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload["id"]

    conn = get_db()
    record = conn.execute("SELECT * FROM onboarding WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    if not record:
        # 新用戶，建立 onboarding 記錄
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO onboarding (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        return {"step": 0, "completed": False, "bonus_given": False}

    return {
        "step": record["step"],
        "completed": bool(record["completed"]),
        "bonus_given": bool(record["bonus_given"])
    }


@router.post("/onboarding/complete-step/{step}")
def complete_step(step: int, token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload["id"]

    conn = get_db()
    conn.execute("""
        INSERT INTO onboarding (user_id, step) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET step=MAX(step, ?)
    """, (user_id, step, step))
    conn.commit()

    # 完成所有步驟 (3步) → 送獎勵
    record = conn.execute("SELECT * FROM onboarding WHERE user_id=?", (user_id,)).fetchone()

    bonus_message = None
    if record["step"] >= 3 and not record["completed"]:
        conn.execute("UPDATE onboarding SET completed=1 WHERE user_id=?", (user_id,))

        # 送額外 3 次分析 bonus
        if not record["bonus_given"]:
            from services.quota_service import QuotaService
            # 加入 bonus quota
            for _ in range(3):
                try:
                    conn.execute("""
                        INSERT INTO quota_usage (user_id, feature, date, count)
                        VALUES (?, 'full_analysis_bonus', date('now'), 0)
                        ON CONFLICT DO NOTHING
                    """, (user_id,))
                except:
                    pass
            conn.execute("UPDATE onboarding SET bonus_given=1 WHERE user_id=?", (user_id,))
            bonus_message = "🎉 Onboarding 完成！獲得額外 3 次分析獎勵！"

        conn.commit()

    conn.close()

    return {
        "step": step,
        "completed": step >= 3,
        "bonus_message": bonus_message or f"Step {step} completed!"
    }
