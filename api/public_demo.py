"""
Anonymous, no-login-required "taste" demo for the homepage.

Product decision (2026-07-11): homepage should let a visitor try a real
analysis before signing up (higher conversion than "register first").
But XFINLAB's actual business model is login-gated (10 free analyses/day
per account), and this endpoint has NO identity to rate-limit against
except IP -- so it's deliberately kept to exactly 1 use per IP per day,
and deliberately uses ONLY the free, already-computed technical analysis
(services/technical_analysis_service.py -- real market data, real RSI/
Confluence math, zero AI-provider cost) rather than calling any paid AI
model. This means even if someone hammers this endpoint, the worst case
is extra Alpaca/yfinance calls (free tier), never a Groq/Gemini bill.

Explicitly NOT the same as the full /api/chart-analysis or
/api/full-analysis endpoints -- this returns a deliberately smaller
"teaser" shape to encourage signing up for the complete report.
"""

import os
import sqlite3
from datetime import date
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS demo_usage (
            ip TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (ip, usage_date)
        )
    """)
    conn.commit()
    conn.close()


init_demo_usage_table()

DEMO_DAILY_LIMIT_PER_IP = 1


@router.get("/demo/analyze/{ticker}")
def demo_analyze(ticker: str, request: Request):
    ip = request.client.host if request.client else "unknown"
    today = date.today().isoformat()

    conn = _get_db()
    row = conn.execute(
        "SELECT count FROM demo_usage WHERE ip = ? AND usage_date = ?", (ip, today)
    ).fetchone()
    used = row["count"] if row else 0

    if used >= DEMO_DAILY_LIMIT_PER_IP:
        conn.close()
        raise HTTPException(
            status_code=429,
            detail="今日免費體驗已用完，註冊帳號享受每日10次完整AI分析。",
        )

    tech = get_technical_analysis(ticker)
    if not tech or "error" in tech:
        conn.close()
        raise HTTPException(status_code=404, detail=tech.get("error", "查唔到呢隻股票") if tech else "查唔到呢隻股票")

    if row:
        conn.execute(
            "UPDATE demo_usage SET count = count + 1 WHERE ip = ? AND usage_date = ?",
            (ip, today),
        )
    else:
        conn.execute(
            "INSERT INTO demo_usage (ip, usage_date, count) VALUES (?, ?, 1)",
            (ip, today),
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
        "remaining_free_demo_today": max(0, DEMO_DAILY_LIMIT_PER_IP - used - 1),
    }
