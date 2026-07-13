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

Quota model updated 2026-07-13 (product decision): the free trial is now
a strict SINGLE USE per IP -- one free analysis, ever, tracked server-side
so it can't be reset by simply reloading/reopening the page (no cookie or
localStorage state involved, purely IP-keyed in demo_usage). After that
one use, the visitor must log in to continue. There is no automatic
window/cooldown reset any more (previously: 30-minute unlimited window +
4-hour cooldown before a new window opened) -- that model is replaced
because the ask is now "1 free try, then sign up," not "keep trying every
few hours without an account."

Explicitly NOT the same as the full /api/chart-analysis or
/api/full-analysis endpoints -- this returns a deliberately smaller
"teaser" shape to encourage signing up for the complete report.
"""

import os
import sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request

from services.technical_analysis_service import get_technical_analysis

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_demo_usage_table():
    conn = _get_db()

    # Schema changed 2026-07-13 (30-min-window -> strict single-use). The
    # previous table shape was (ip PRIMARY KEY, window_started_at,
    # use_count); the new one just needs (ip PRIMARY KEY, used_at). This
    # data is purely ephemeral anonymous-IP throttling state (no user data,
    # nothing worth preserving across the schema change), so if the old
    # shape is detected, just drop and recreate rather than migrate.
    cols = conn.execute("PRAGMA table_info(demo_usage)").fetchall()
    col_names = [c["name"] for c in cols]
    if cols and "used_at" not in col_names:
        conn.execute("DROP TABLE demo_usage")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS demo_usage (
            ip TEXT PRIMARY KEY,
            used_at TEXT NOT NULL
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
        # This IP has already used its one free trial -- no auto-reset,
        # must log in to continue.
        conn.close()
        raise HTTPException(
            status_code=429,
            detail="你已經用咗呢個IP嘅免費體驗機會，請登入繼續使用。",
        )

    tech = get_technical_analysis(ticker)
    if not tech or "error" in tech:
        conn.close()
        raise HTTPException(status_code=404, detail=tech.get("error", "查唔到呢隻股票") if tech else "查唔到呢隻股票")

    conn.execute(
        "INSERT INTO demo_usage (ip, used_at) VALUES (?, ?) "
        "ON CONFLICT(ip) DO NOTHING",
        (ip, now.isoformat()),
    )
    conn.commit()
    conn.close()

    # 刻意精簡嘅teaser shape -- 唔係全套/api/chart-analysis嗰個完整報告，
    # 引導用戶註冊睇齊全部（支撐/阻力/Fibonacci/型態辨識等）。
    return {
        "ticker": tech["symbol"],
        "price": tech["last_close"],
        "trend": tech["trend"],
        "rsi": tech["rsi"],
        "confluence_direction": tech["confluence"]["direction"],
        "confluence_confidence": tech["confluence"]["confidence"],
    }
