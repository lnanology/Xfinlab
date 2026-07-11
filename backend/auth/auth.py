
import sqlite3
import os
from fastapi import APIRouter, HTTPException, Request
from auth.user_model import UserRegister, UserLogin, UserResponse
from auth.password import hash_password, verify_password
from auth.jwt_handler import create_access_token
from services.email_service import EmailService
from services.audit_log_service import log_action
from auth.email_verification import send_verification_email

router = APIRouter()
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
        try:
            EmailService.send_welcome(user.email, user.name)
            send_verification_email(user_id, user.email, user.name)
        except:
            pass
        log_action(user_id, "register", request.client.host if request.client else None)
        return UserResponse(id=user_id, email=user.email, name=user.name, plan="free", token=token)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@router.post("/auth/login", response_model=UserResponse)
def login(user: UserLogin, request: Request):
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
    from auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload["sub"],)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": row["id"], "email": row["email"], "name": row["name"], "plan": row["plan"]}
