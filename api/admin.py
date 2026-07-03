import sqlite3
import os
import time
import requests
from fastapi import APIRouter, HTTPException
from backend.auth.jwt_handler import verify_token

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
ADMIN_EMAIL = "abcoaj888@gmail.com"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def verify_admin(token: str):
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("sub") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload

@router.get("/admin/stats")
def get_stats(token: str):
    verify_admin(token)
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    pro_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE plan='pro'").fetchone()["c"]
    total_events = conn.execute("SELECT COUNT(*) as c FROM user_analytics").fetchone()["c"]
    today_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE created_at >= date('now')").fetchone()["c"]

    # DAU
    dau = conn.execute(
        "SELECT COUNT(DISTINCT user_id) as c FROM user_analytics WHERE created_at >= date('now')"
    ).fetchone()["c"]

    # MAU
    mau = conn.execute(
        "SELECT COUNT(DISTINCT user_id) as c FROM user_analytics WHERE created_at >= date('now', '-30 days')"
    ).fetchone()["c"]

    # Today events breakdown
    today_analyses = conn.execute(
        "SELECT COUNT(*) as c FROM user_analytics WHERE event_type='search' AND created_at >= date('now')"
    ).fetchone()["c"]

    today_api_calls = conn.execute(
        "SELECT COUNT(*) as c FROM user_analytics WHERE created_at >= date('now')"
    ).fetchone()["c"]

    # Top searches
    top_searches = conn.execute("""
        SELECT event_data, COUNT(*) as c FROM user_analytics
        WHERE event_type='search'
        GROUP BY event_data ORDER BY c DESC LIMIT 10
    """).fetchall()

    # Trending stocks
    top_analysis = conn.execute("""
        SELECT event_data, COUNT(*) as c FROM user_analytics
        WHERE event_type='search'
        GROUP BY event_data ORDER BY c DESC LIMIT 5
    """).fetchall()

    conn.close()

    return {
        "total_users": total_users,
        "pro_users": pro_users,
        "free_users": total_users - pro_users,
        "today_new_users": today_users,
        "total_events": total_events,
        "dau": dau,
        "mau": mau,
        "today_analyses": today_analyses,
        "today_api_calls": today_api_calls,
        "top_searches": [dict(r) for r in top_searches],
        "top_analysis": [dict(r) for r in top_analysis],
    }

@router.get("/admin/health")
def get_health(token: str):
    verify_admin(token)
    results = {}

    # Market API
    try:
        import yfinance as yf
        t = yf.Ticker("AAPL")
        price = t.info.get("regularMarketPrice") or t.fast_info.last_price
        results["market_api"] = {"status": "online", "detail": f"AAPL ${price:.2f}"}
    except Exception as e:
        results["market_api"] = {"status": "offline", "detail": str(e)[:50]}

    # News API
    try:
        news_key = os.getenv("NEWS_API_KEY", "")
        res = requests.get(f"https://newsapi.org/v2/top-headlines?country=us&apiKey={news_key}&pageSize=1", timeout=5)
        results["news_api"] = {"status": "online" if res.status_code == 200 else "offline", "detail": f"Status {res.status_code}"}
    except Exception as e:
        results["news_api"] = {"status": "offline", "detail": str(e)[:50]}

    # Crypto API
    try:
        res = requests.get("https://api.coingecko.com/api/v3/ping", timeout=5)
        results["crypto_api"] = {"status": "online" if res.status_code == 200 else "offline", "detail": "CoinGecko"}
    except Exception as e:
        results["crypto_api"] = {"status": "offline", "detail": str(e)[:50]}

    # Groq AI
    try:
        groq_key = os.getenv("GROQ_API_KEY", "")
        results["groq_ai"] = {"status": "online" if groq_key else "offline", "detail": "API Key configured" if groq_key else "No API Key"}
    except:
        results["groq_ai"] = {"status": "offline", "detail": "Error"}

    # Database
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        results["database"] = {"status": "online", "detail": "SQLite Connected"}
    except Exception as e:
        results["database"] = {"status": "offline", "detail": str(e)[:50]}

    return results

@router.get("/admin/users")
def get_users(token: str, page: int = 1, limit: int = 20):
    verify_admin(token)
    conn = get_db()
    offset = (page - 1) * limit
    users = conn.execute(
        "SELECT id, email, name, plan, email_verified, created_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    conn.close()
    return {"users": [dict(u) for u in users], "total": total, "page": page}

@router.post("/admin/users/{user_id}/upgrade")
def upgrade_user(user_id: int, token: str):
    verify_admin(token)
    conn = get_db()
    conn.execute("UPDATE users SET plan='pro' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} upgraded to Pro"}

@router.post("/admin/users/{user_id}/downgrade")
def downgrade_user(user_id: int, token: str):
    verify_admin(token)
    conn = get_db()
    conn.execute("UPDATE users SET plan='free' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} downgraded to Free"}

@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, token: str):
    verify_admin(token)
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} deleted"}

@router.post("/admin/push/telegram")
async def push_telegram(token: str, body: dict = {}):
    verify_admin(token)
    channel = body.get("channel", "en")
    try:
        import subprocess
        scripts = {
            "en": "growth/channel_push.py",
            "zh": "growth/channel_push_zh.py",
            "es": "growth/channel_push_es.py"
        }
        script = scripts.get(channel, scripts["en"])
        subprocess.Popen([
            "/Library/Developer/CommandLineTools/usr/bin/python3.9",
            f"/Users/aj/Desktop/Xfinlab-main/{script}"
        ])
        return {"status": "ok", "message": f"Pushing to {channel} channel"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/admin/feature-flags")
def get_feature_flags(token: str):
    verify_admin(token)
    return {
        "flags": {
            "research_agent": True,
            "portfolio": True,
            "anomaly": True,
            "screener": True,
            "chart_analysis": True,
            "telegram_bot": True,
            "referral": True,
        }
    }
