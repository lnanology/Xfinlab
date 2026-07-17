import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.market import router as market_router
from api.analyze import router as analyze_router
from api.event import router as event_router
from api.full_analysis_v3 import router as full_analysis_router
from api.screener import router as screener_router
from api.portfolio import router as portfolio_router
from api.anomaly import router as anomaly_router
from api.research import router as research_router
from api.report import router as report_router
from auth.auth import router as auth_router
from api.quota import router as quota_router
from api.points import router as points_router
from api.referral import router as referral_router
from api.analytics import router as analytics_router
from api.ai_analysis import router as ai_analysis_router
from api.news_denoise import router as news_denoise_router
from api.company_compare import router as company_compare_router
from api.stress_lab import router as stress_lab_router
from api.chart_analysis import router as chart_analysis_router
from api.chat import router as chat_router
from auth.password_reset import router as password_reset_router
from api.watchlist import router as watchlist_router
from api.admin import router as admin_router
from api.pipeline_api import router as pipeline_router
from api.feedback import router as feedback_router
from api.onboarding import router as onboarding_router
from api.i18n import router as i18n_router
from auth.email_verification import router as email_verification_router
from api.public_stats import router as public_stats_router
from api.public_demo import router as public_demo_router
from api.market_pulse import router as market_pulse_router
from api.hero_showcase import router as hero_showcase_router
from api.push import router as push_router


app = FastAPI(
    title="XFINLAB API",
    version="1.0.0"
)

# One-time, idempotent: merges any users stranded in the legacy
# backend/xfinlab.db (a DB_PATH bug, now fixed) into the canonical,
# Litestream-backed root xfinlab.db. See services/db_migration.py.
from services.db_migration import (
    ensure_wal_mode,
    migrate_legacy_backend_db,
    migrate_audit_logs_nullable_user_id,
    reset_admin_password_if_requested,
)
# Must run first — Litestream can only replicate writes once the DB is in
# WAL mode. See ensure_wal_mode()'s docstring in services/db_migration.py.
ensure_wal_mode()
migrate_legacy_backend_db()
migrate_audit_logs_nullable_user_id()
reset_admin_password_if_requested()

# --- Rate limiting (Security & Operations Layer, Phase 2) ---
# Blanket per-IP safety net against abuse/scraping bursts. This is separate
# from services/quota_middleware.py, which limits per-user *feature* usage
# by subscription plan — this limits raw request volume regardless of who's
# calling. In-memory backend is fine for our current single-instance Railway
# deployment; would need a Redis backend if we ever scale to multiple
# instances (limits would then be per-instance, not global).
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    # Must stay synchronous (not async def) — slowapi's SlowAPIMiddleware
    # calls exception handlers from a sync context and silently falls back
    # to its own default (English) message if the handler is a coroutine.
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "請求太頻繁，請稍後再試。",
        },
    )


# Starlette's add_middleware() inserts at position 0, so the middleware
# added LAST ends up processing requests FIRST (outermost). We need CORS to
# be outermost so it still sees/decorates the 429 response that
# SlowAPIMiddleware returns early (without calling further inward) — so
# SlowAPIMiddleware must be added BEFORE CORSMiddleware here.
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://xfinlab.com", "https://www.xfinlab.com", "http://localhost:3001", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Market
app.include_router(market_router, prefix="/api", tags=["Market"])

# Analysis
app.include_router(analyze_router, prefix="/api", tags=["Analysis"])

# Event
app.include_router(event_router, prefix="/api", tags=["Event"])

# Full AI Analysis (P0 Core)
app.include_router(full_analysis_router, prefix="/api", tags=["Full Analysis"])

# P1 Screener Engine
app.include_router(screener_router, prefix="/api", tags=["Screener"])

# P1 Portfolio Engine
app.include_router(portfolio_router, prefix="/api", tags=["Portfolio"])

# P1 Anomaly Engine
app.include_router(anomaly_router, prefix="/api", tags=["Anomaly"])
app.include_router(research_router, prefix="/api", tags=["Research"])
app.include_router(report_router, prefix="/api", tags=["Report"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(quota_router, prefix="/api", tags=["Quota"])
app.include_router(points_router, prefix="/api", tags=["Points"])
app.include_router(referral_router, prefix="/api", tags=["Referral"])
app.include_router(analytics_router, prefix="/api", tags=["Analytics"])
app.include_router(ai_analysis_router, prefix="/api", tags=["AI Analysis"])
app.include_router(news_denoise_router, prefix="/api", tags=["News"])
app.include_router(company_compare_router, prefix="/api", tags=["Compare"])
app.include_router(stress_lab_router, prefix="/api", tags=["Stress Lab"])
app.include_router(chart_analysis_router, prefix="/api", tags=["Chart Analysis"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(password_reset_router, prefix="/api", tags=["Password Reset"])
app.include_router(watchlist_router, prefix="/api", tags=["Watchlist"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])
app.include_router(pipeline_router, prefix="/api", tags=["Pipeline"])
app.include_router(feedback_router, prefix="/api", tags=["Feedback"])
app.include_router(onboarding_router, prefix="/api", tags=["Onboarding"])
app.include_router(i18n_router, prefix="/api", tags=["i18n"])
app.include_router(email_verification_router, prefix="/api", tags=["Email Verification"])
app.include_router(public_stats_router, prefix="/api", tags=["Public Stats"])
app.include_router(public_demo_router, prefix="/api", tags=["Public Demo"])
app.include_router(market_pulse_router, prefix="/api", tags=["Market Pulse"])
app.include_router(hero_showcase_router, prefix="/api", tags=["Hero Showcase"])
app.include_router(push_router, prefix="/api", tags=["Push"])


@app.get("/")
def root():
    return {
        "name": "XFINLAB API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
@limiter.exempt
def health(request: Request):
    """
    Lightweight, unauthenticated health check for Railway / uptime
    monitors. Deliberately separate from /api/admin/health, which needs an
    admin token and makes slow external network calls (market/news/crypto
    APIs) — not something a monitor should be hitting every 30 seconds.
    This one just confirms the process is up and the database is reachable.
    Exempt from rate limiting so frequent automated pings never 429.
    """
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)[:100]}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
    }