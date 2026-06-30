
import sqlite3
import os
from fastapi import APIRouter, HTTPException
from auth.user_model import UserRegister, UserLogin, UserResponse
from auth.password import hash_password, verify_password
from auth.jwt_handler import create_access_token
from services.email_service import EmailService
from auth.email_verification import send_verification_email

router = APIRouter()
DB_PATH = "/Users/aj/Desktop/Xfinlab-main/xfinlab.db"

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
def register(user: UserRegister):
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
        return UserResponse(id=user_id, email=user.email, name=user.name, plan="free", token=token)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@router.post("/auth/login", response_model=UserResponse)
def login(user: UserLogin):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (user.email,)).fetchone()
    conn.close()
    if not row or not verify_password(user.password, row["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": row["email"], "id": row["id"]})
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
