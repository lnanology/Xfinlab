"""
Anonymous, no-login-required "taste" demo for the homepage.

Product decision (2026-07-11): homepage should let a visitor try a real
analysis before signing up (higher conversion than "register first").
XFINLAB's actual business model is login-gated (10 free analyses/day per
account), and this endpoint has NO identity to rate-limit against except
IP -- so it deliberately uses ONLY the free, already-computed technical
analysis (services/technical_analysis_service.py -- real market data,
real RSI/Confluence math, zero AI-provider cost) rather than calling any
paid AI model. This means even if someone hammers this endpoint, the
worst case is extra Alpaca/yfinance calls (free tier, and still capped by
the blanket 100/min-per-IP limiter in backend/main.py), never a
Groq/Gemini bill.

Quota model updated 2026-07-13, revised again same day (product decision):
each IP gets exactly ONE 15-minute trial window, ever -- unlimited queries
inside that single window, tracked server-side so it can't be reset by
reloading/reopening the page (no cookie or localStorage state involved,
purely IP-keyed in demo_usage). Once the 15 minutes elapse, that IP is
permanently locked out of this endpoint -- there is no cooldown that
reopens a new window later (unlike the original 2026-07-11 design, which
allowed a fresh 30-minute window every 4 hours). The visitor must log in
to continue using the product after their one window closes.

Explicitly NOT the same as the full /api/chart-analysis or
/api/full-analysis endpoints -- this returns a deliberately smaller
"teaser" shape to encourage signing up for the complete report.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request

from services.technical_analysis_service import get_technical_analysis

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

TRIAL_WINDOW_MINUTES = 15


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_demo_usage_table():
    conn = _get_db()

    # Schema changed again same day (strict-single-use -> single 15-min
    # window). The previous table shape was (ip PRIMARY KEY, used_at); the
    # new one needs (ip PRIMARY KEY, window_started_at) so we can tell
    # whether the visitor is still inside their one-time window. This data
    # is purely ephemeral anonymous-IP throttling state (no user data,
    # nothing worth preserving across the schema change), so if the old
    # shape is detected, just drop and recreate rather than migrate.
    cols = conn.execute("PRAGMA table_info(demo_usage)").fetchall()
    col_names = [c["name"] for c in cols]
    if cols and "window_started_at" not in col_names:
        conn.execute("DROP TABLE demo_usage")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS demo_usage (
            ip TEXT PRIMARY KEY,
            window_started_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_demo_usage_table()


@router.get("/demo/analyze/{ticker}")
def demo_analyze(ticker: str, request: Request):
    ip = request.client.host if request.client else "unknown"
    now = datetime.utcnow()

    conn = _get_db()
    row = conn.execute("SELECT * FROM demo_usage WHERE ip = ?", (ip,)).fetchone()

    if row:
        window_started_at = datetime.fromisoformat(row["window_started_at"])
        elapsed = now - window_started_at
        if elapsed > timedelta(minutes=TRIAL_WINDOW_MINUTES):
            # This IP's one-time window has already closed -- no auto-reset,
            # must log in to continue.
            conn.close()
            raise HTTPException(
                status_code=429,
                detail="你嘅15分鐘免費體驗時段已經完結，請登入繼續使用。",
            )
        # Still inside the one-time window -- unlimited queries allowed,
        # don't touch window_started_at (it must not extend the window).
    else:
        window_started_at = now
        conn.execute(
            "INSERT INTO demo_usage (ip, window_started_at) VALUES (?, ?) "
            "ON CONFLICT(ip) DO NOTHING",
            (ip, window_started_at.isoformat()),
        )
        conn.commit()

    tech = get_technical_analysis(ticker)
    if not tech or "error" in tech:
        conn.close()
        raise HTTPException(status_code=404, detail=tech.get("error", "查唔到呢隻股票") if tech else "查唔到呢隻股票")

    conn.close()

    window_remaining = timedelta(minutes=TRIAL_WINDOW_MINUTES) - (now - window_started_at)
    window_remaining_minutes = max(0, int(window_remaining.total_seconds() // 60))

    # 刻意精簡嘅teaser shape -- 唔係全套/api/chart-analysis嗰個完整報告，
    # 引導用戶註冊睇齊全部（支撐/阻力/Fibonacci/型態辨識等）。
    return {
        "ticker": tech["symbol"],
        "price": tech["last_close"],
        "trend": tech["trend"],
        "rsi": tech["rsi"],
        "confluence_direction": tech["confluence"]["direction"],
        "confluence_confidence": tech["confluence"]["confidence"],
        "trial_window_minutes_remaining": window_remaining_minutes,
    }
