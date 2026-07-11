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

Quota model updated 2026-07-11 (product decision): instead of a strict
1-use-per-day cap, anonymous visitors now get a 30-minute trial WINDOW
per IP (unlimited analyses inside that window), then must log in. A new
window only opens again 4 hours after the first window started. This is
safe to loosen because the underlying cost is just free-tier market-data
calls, not paid AI -- the thing actually worth protecting (AI provider
spend) was never exposed here in the first place.

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

TRIAL_WINDOW_MINUTES = 30
COOLDOWN_HOURS = 4


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_demo_usage_table():
    conn = _get_db()

    # Schema changed 2026-07-11 (daily-count -> trial-window). The old
    # table shape was (ip, usage_date, count) with a composite primary
    # key; the new one is (ip PRIMARY KEY, window_started_at, use_count).
    # This data is purely ephemeral anonymous-IP throttling state (no user
    # data, nothing worth preserving across the schema change), so if the
    # old shape is detected, just drop and recreate rather than migrate.
    cols = conn.execute("PRAGMA table_info(demo_usage)").fetchall()
    if cols and "window_started_at" not in [c["name"] for c in cols]:
        conn.execute("DROP TABLE demo_usage")

    # window_started_at: when this IP's current 30-min trial window began.
    # A fresh window only opens once COOLDOWN_HOURS have passed since the
    # previous window_started_at.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS demo_usage (
            ip TEXT PRIMARY KEY,
            window_started_at TEXT NOT NULL,
            use_count INTEGER DEFAULT 0
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

        if elapsed <= timedelta(minutes=TRIAL_WINDOW_MINUTES):
            # Still inside the free trial window -- unlimited analyses.
            new_window_start = window_started_at
            new_count = row["use_count"] + 1
        elif elapsed >= timedelta(hours=COOLDOWN_HOURS):
            # Cooldown has fully elapsed -- open a brand new window.
            new_window_start = now
            new_count = 1
        else:
            # Window expired, cooldown not yet over -- blocked.
            conn.close()
            remaining_cooldown = timedelta(hours=COOLDOWN_HOURS) - elapsed
            remaining_minutes = max(1, int(remaining_cooldown.total_seconds() // 60))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"免費試用時段（30分鐘）已經用完，請登入繼續使用。"
                    f"約{remaining_minutes}分鐘後可以再次免費試用。"
                ),
            )
    else:
        new_window_start = now
        new_count = 1

    tech = get_technical_analysis(ticker)
    if not tech or "error" in tech:
        conn.close()
        raise HTTPException(status_code=404, detail=tech.get("error", "查唔到呢隻股票") if tech else "查唔到呢隻股票")

    conn.execute(
        "INSERT INTO demo_usage (ip, window_started_at, use_count) VALUES (?, ?, ?) "
        "ON CONFLICT(ip) DO UPDATE SET window_started_at = excluded.window_started_at, "
        "use_count = excluded.use_count",
        (ip, new_window_start.isoformat(), new_count),
    )
    conn.commit()
    conn.close()

    window_remaining = timedelta(minutes=TRIAL_WINDOW_MINUTES) - (now - new_window_start)
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
