import sqlite3
import os
import time
import requests
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from backend.auth.jwt_handler import verify_token
from services.audit_log_service import log_action, get_recent_logs
from services.request_ip import get_client_ip

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
ADMIN_EMAIL = "abcoaj888@gmail.com"

# Optional defense-in-depth: if ADMIN_IP_ALLOWLIST is set (comma-separated
# IPs, e.g. "1.2.3.4,5.6.7.8"), admin endpoints reject any caller whose IP
# isn't on the list -- even with a valid, correctly-signed admin token.
# This protects against the scenario where JWT_SECRET or a live admin
# token leaks (e.g. via a compromised browser/device) but the attacker
# isn't calling from one of your own known IPs. Backwards compatible:
# unset (the default) means no restriction at all, matching prior
# behavior exactly -- this only activates if you opt in.
_ADMIN_IP_ALLOWLIST = [
    ip.strip() for ip in os.getenv("ADMIN_IP_ALLOWLIST", "").split(",") if ip.strip()
]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Default flag set + state. admin.html's toggle previously did nothing but
# flip a CSS class client-side -- looked functional, wasn't. This makes it
# real: values are persisted in a feature_flags table, seeded with these
# defaults the first time the table is touched. NOTE: persisting the value
# is as far as this goes for now -- none of the 7 actual endpoints
# (research_agent/portfolio/anomaly/screener/chart_analysis/telegram_bot/
# referral) currently check this table before serving a request, so
# toggling a flag off here does NOT yet disable the feature. Wiring real
# enforcement into each endpoint is separate, larger-scope work.
_DEFAULT_FLAGS = {
    "research_agent": True,
    "portfolio": True,
    "anomaly": True,
    "screener": True,
    "chart_analysis": True,
    "telegram_bot": True,
    "referral": True,
}

def init_feature_flags_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_flags (
            key TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    existing = {r["key"] for r in conn.execute("SELECT key FROM feature_flags").fetchall()}
    for key, default_enabled in _DEFAULT_FLAGS.items():
        if key not in existing:
            conn.execute(
                "INSERT INTO feature_flags (key, enabled) VALUES (?, ?)",
                (key, 1 if default_enabled else 0),
            )
    conn.commit()
    conn.close()

init_feature_flags_table()

def verify_admin(token: str, action: str = None, request: Request = None):
    """
    Verifies the caller is the admin. When `action` is supplied, also
    writes an audit_logs entry for it -- every admin endpoint below passes
    its own action name so there's a full trail of what the admin did.
    """
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("sub") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    ip = get_client_ip(request) if request else None
    if _ADMIN_IP_ALLOWLIST and ip not in _ADMIN_IP_ALLOWLIST:
        # Logged with user_id=None (like login_failed) so blocked attempts
        # are visible in the audit trail even though they never got in.
        log_action(None, f"admin_ip_blocked:{action or 'unknown'}", ip)
        raise HTTPException(status_code=403, detail="Admin access not permitted from this network")

    if action:
        log_action(payload.get("id"), f"admin:{action}", ip)
    return payload

@router.get("/admin/stats")
def get_stats(token: str, request: Request):
    verify_admin(token, "get_stats", request)
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
def get_health(token: str, request: Request):
    verify_admin(token, "get_health", request)
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

    # Litestream / WAL diagnostics (2026-07-11) -- added while debugging why
    # the admin account kept disappearing after Railway redeploys. Litestream
    # can only replicate writes to R2 when the DB is in WAL journal mode
    # (see services/db_migration.py's ensure_wal_mode() for the full story).
    # This surfaces that state directly instead of having to infer it
    # indirectly from total_users counts after the fact.
    try:
        conn = get_db()
        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        journal_mode = mode_row[0] if mode_row else "unknown"
        conn.close()

        wal_path = DB_PATH + "-wal"
        wal_exists = os.path.exists(wal_path)
        wal_size = os.path.getsize(wal_path) if wal_exists else 0
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        db_mtime = (
            datetime.fromtimestamp(os.path.getmtime(DB_PATH), tz=timezone.utc).isoformat()
            if os.path.exists(DB_PATH)
            else None
        )

        results["litestream_wal"] = {
            "status": "online" if journal_mode.lower() == "wal" else "offline",
            "detail": (
                f"journal_mode={journal_mode}, wal_file_exists={wal_exists}, "
                f"wal_size_bytes={wal_size}, db_size_bytes={db_size}, "
                f"db_last_modified={db_mtime}"
            ),
        }
    except Exception as e:
        results["litestream_wal"] = {"status": "offline", "detail": str(e)[:100]}

    return results

@router.get("/admin/users")
def get_users(token: str, request: Request, page: int = 1, limit: int = 20):
    verify_admin(token, "get_users", request)
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
def upgrade_user(user_id: int, token: str, request: Request):
    verify_admin(token, f"upgrade_user:{user_id}", request)
    conn = get_db()
    conn.execute("UPDATE users SET plan='pro' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} upgraded to Pro"}

@router.post("/admin/users/{user_id}/downgrade")
def downgrade_user(user_id: int, token: str, request: Request):
    verify_admin(token, f"downgrade_user:{user_id}", request)
    conn = get_db()
    conn.execute("UPDATE users SET plan='free' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} downgraded to Free"}

@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, token: str, request: Request):
    verify_admin(token, f"delete_user:{user_id}", request)
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": f"User {user_id} deleted"}

@router.post("/admin/push/telegram")
async def push_telegram(token: str, request: Request, body: dict = {}):
    channel = body.get("channel", "en")
    verify_admin(token, f"push_telegram:{channel}", request)
    try:
        import subprocess
        import sys
        scripts = {
            "en": "growth/channel_push.py",
            "zh": "growth/channel_push_zh.py",
            "es": "growth/channel_push_es.py"
        }
        script = scripts.get(channel, scripts["en"])
        # Was hardcoded to a local Mac path (/Users/aj/... + a specific
        # python3.9 binary) that only exists on the dev machine -- this
        # would fail silently in Railway's container. Use sys.executable
        # (whatever interpreter is actually running this app) and resolve
        # the script path relative to the repo root, same pattern as
        # DB_PATH elsewhere in this file.
        repo_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        script_path = os.path.join(repo_root, script)
        subprocess.Popen([sys.executable, script_path])
        return {"status": "ok", "message": f"Pushing to {channel} channel"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/admin/audit-logs")
def get_audit_logs(token: str, request: Request, limit: int = 100):
    """
    Security & Operations Layer, Phase 2 -- surfaces the audit_logs table
    (login/register/admin actions, written by services/audit_log_service.py)
    in the admin dashboard. Capped at 200 to keep the response light.
    """
    verify_admin(token, "get_audit_logs", request)
    return {"logs": get_recent_logs(limit=min(limit, 200))}

@router.get("/admin/feature-flags")
def get_feature_flags(token: str, request: Request):
    verify_admin(token, "get_feature_flags", request)
    conn = get_db()
    rows = conn.execute("SELECT key, enabled FROM feature_flags").fetchall()
    conn.close()
    return {"flags": {r["key"]: bool(r["enabled"]) for r in rows}}

@router.post("/admin/feature-flags/{key}")
def set_feature_flag(key: str, token: str, request: Request, body: dict = {}):
    verify_admin(token, f"set_feature_flag:{key}", request)
    if key not in _DEFAULT_FLAGS:
        raise HTTPException(status_code=404, detail=f"Unknown flag: {key}")
    enabled = bool(body.get("enabled", True))
    conn = get_db()
    conn.execute(
        "UPDATE feature_flags SET enabled = ?, updated_at = datetime('now') WHERE key = ?",
        (1 if enabled else 0, key),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "key": key, "enabled": enabled}


@router.get("/admin/security-scan")
def get_security_scan(token: str, request: Request):
    """
    Task #326: surfaces the security watch (scripts/security_scan.py /
    services/security_scan_service.py) in the admin panel, instead of it
    only ever existing as terminal output from the external 6-hourly
    scheduled task. Returns the most recent scan result already
    persisted into xfinlab.db by the in-process APScheduler job
    (backend/main.py) or a prior manual run -- this is intentionally
    fast/read-only, it does NOT run a fresh scan on every page load.
    """
    verify_admin(token, "get_security_scan", request)
    from services.security_scan_service import get_latest_scan_result, get_scan_history
    latest = get_latest_scan_result()
    if latest is None:
        return {"status": "no_data", "result": None, "history": []}
    return {"status": "ok", "result": latest, "history": get_scan_history(limit=10)}


@router.post("/admin/security-scan/run")
def run_security_scan_now(token: str, request: Request):
    """
    Manual "Run Scan Now" trigger for the admin panel. Runs synchronously
    (skips the slow pip-audit dependency scan so this stays fast enough
    for a single HTTP request -- the in-process 6-hourly job still runs
    the full scan including dependency CVEs) and persists the result
    like every other run, so it immediately shows up in get_security_scan
    and in the history list too.
    """
    verify_admin(token, "run_security_scan_now", request)
    from services.security_scan_service import run_and_save
    result = run_and_save(skip_dependency_scan=True)
    return {"status": "ok", "result": result}
