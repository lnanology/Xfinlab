import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from api.dify import router as dify_router
from auth.email_verification import router as email_verification_router


app = FastAPI(
    title="XFINLAB API",
    version="1.0.0"
)

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
app.include_router(dify_router, prefix="/api", tags=["DIFY"])
app.include_router(email_verification_router, prefix="/api", tags=["Email Verification"])


@app.get("/")
def root():
    return {
        "name": "XFINLAB API",
        "version": "1.0.0",
        "status": "running"
    }