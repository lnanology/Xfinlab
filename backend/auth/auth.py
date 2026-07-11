
import sqlite3
import os
from fastapi import APIRouter, HTTPException, Request
from auth.user_model import UserRegister, UserLogin, UserResponse
from auth.password import hash_password, verify_password
# 2026-07-11 fix: 呢度之前用緊短路徑 `from auth.jwt_handler import ...`，
# 但codebase入面第9個地方（quota_middleware/referral/quota/analytics/
# onboarding/feedback/admin/watchlist）全部用緊長路徑
# `from backend.auth.jwt_handler import ...`。Python嘅import系統將呢兩條
# 路徑當做兩個唔同嘅module object，各自獨立執行一次jwt_handler.py嘅
# top-level code——如果JWT_SECRET env var冇set，兩個instance會各自
# 生成一個唔同嘅random secret，導致喺呢度create嘅token喺其他地方
# verify唔到（反之亦然）。生產環境因為JWT_SECRET有set，兩個instance
# 讀返同一個env var值，暫時冇壞，但呢個fragility喺local testing已經
# 引致混淆，值得徹底消除。統一用返長路徑。
from backend.auth.jwt_handler import create_access_token
from services.email_service import EmailService
from services.audit_log_service import log_action, count_recent_failed_logins
from auth.email_verification import send_verification_email
from infrastructure.event_bus import EventBus

router = APIRouter()

# --- "user_registered" subscribers (Phase 3, Event Bus first real use) ---
# Previously these three were three separate, tightly-coupled calls inside
# register() itself. Splitting them into independent subscribers means
# adding a fourth "on register" behavior later (e.g. a Slack ping to admin,
# seeding the onboarding table) is a new subscribe() call, not an edit to
# the registration endpoint. Behavior is unchanged -- same three actions,
# same silent-failure-doesn't-block-registration guarantee, now enforced
# by EventBus.publish()'s per-subscriber exception isolation instead of a
# manual try/except.


def _on_user_registered_send_welcome_email(data):
    EmailService.send_welcome(data["email"], data["name"])


def _on_user_registered_send_verification_email(data):
    send_verification_email(data["user_id"], data["email"], data["name"])


def _on_user_registered_audit_log(data):
    log_action(data["user_id"], "register", data.get("ip"))


EventBus.subscribe("user_registered", _on_user_registered_send_welcome_email)
EventBus.subscribe("user_registered", _on_user_registered_send_verification_email)
EventBus.subscribe("user_registered", _on_user_registered_audit_log)
# NOTE: this file lives at backend/auth/auth.py, so it needs to go up TWO
# levels (auth/ -> backend/ -> repo root) to reach the canonical, Litestream
# -backed xfinlab.db that every other service reads/writes. A previous
# version of this path only went up one level, silently writing to
# backend/xfinlab.db instead -- see services/db_migration.py for the
# one-time fix that recovers any users stranded there.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "xfinlab.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_users_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_users_table()

@router.post("/auth/register", response_model=UserResponse)
def register(user: UserRegister, request: Request):
    conn = get_db()
    try:
        hashed = hash_password(user.password)
        cursor = conn.execute(
            "INSERT INTO users (email, password, name) VALUES (?, ?, ?)",
            (user.email, hashed, user.name)
        )
        conn.commit()
        user_id = cursor.lastrowid
        token = create_access_token({"sub": user.email, "id": user_id})
        EventBus.publish("user_registered", {
            "user_id": user_id,
            "email": user.email,
            "name": user.name,
            "ip": request.client.host if request.client else None,
        })
        return UserResponse(id=user_id, email=user.email, name=user.name, plan="free", token=token)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

LOGIN_LOCKOUT_THRESHOLD = 5   # failed attempts
LOGIN_LOCKOUT_WINDOW_MINUTES = 15

@router.post("/auth/login", response_model=UserResponse)
def login(user: UserLogin, request: Request):
    # Brute-force / credential-stuffing guard: block further attempts for
    # this email once it's racked up too many recent failures, using the
    # login_failed audit trail added earlier. Checked before touching the
    # users table at all, so a locked-out email can't be used to keep
    # probing passwords. Fails open (never locks anyone out) if the audit
    # log query itself errors -- see count_recent_failed_logins().
    recent_failures = count_recent_failed_logins(user.email, minutes=LOGIN_LOCKOUT_WINDOW_MINUTES)
    if recent_failures >= LOGIN_LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=429,
            detail=f"登入失敗次數過多，請{LOGIN_LOCKOUT_WINDOW_MINUTES}分鐘後再試。",
        )

    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (user.email,)).fetchone()
    conn.close()
    if not row or not verify_password(user.password, row["password"]):
        # user_id=None is now allowed (see services/db_migration.py --
        # audit_logs.user_id nullable migration) so failed attempts are
        # visible for brute-force/credential-stuffing monitoring, not just
        # successful logins.
        log_action(None, f"login_failed:{user.email}", request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": row["email"], "id": row["id"]})
    log_action(row["id"], "login", request.client.host if request.client else None)
    return UserResponse(id=row["id"], email=row["email"], name=row["name"], plan=row["plan"], token=token)

@router.get("/auth/me")
def get_me(token: str):
    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload["sub"],)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": row["id"], "email": row["email"], "name": row["name"], "plan": row["plan"]}
