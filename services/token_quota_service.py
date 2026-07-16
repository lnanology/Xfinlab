"""
Monthly AI-token quota engine backing pricing.html's "AI token quota: X%
of full usage" promise (Basic 30% / Pro 50% / Pro+ 70% / Professional
90%). Free tier is NOT metered here -- it keeps its existing daily
feature-count limit from services/quota_service.py (FREE_LIMITS),
unchanged. Enterprise is NOT metered here either -- pricing.html only
promises it "Custom API rate limits" (contractual, handled outside this
system), never a specific token %.

BASE_MONTHLY_TOKENS is the "100% / full usage" reference point the
marketing percentages are measured against. There is no natural ground
truth for this number (XFINLAB has never metered LLM token consumption
before), so it's a deliberately round, conservative estimate rather
than a number backed by historical data -- update it if real usage
patterns turn out to need a different scale.
"""

import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

BASE_MONTHLY_TOKENS = 500_000

# Must match pricing.html's TOKEN_PCTS object (script around line 290) --
# keep these two in sync if pricing.html's tiers/percentages ever change.
PLAN_TOKEN_PCT = {
    "basic": 30,
    "pro": 50,
    "proplus": 70,
    "professional": 90,
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_token_usage_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_usage_monthly (
            user_id INTEGER NOT NULL,
            yyyymm TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, yyyymm)
        )
    """)
    conn.commit()
    conn.close()


init_token_usage_table()


def _yyyymm() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m")


def plan_token_budget(plan: str):
    """Monthly token budget for a plan, or None if this plan isn't
    metered by this system (free / enterprise / unrecognized)."""
    pct = PLAN_TOKEN_PCT.get((plan or "").lower())
    if pct is None:
        return None
    return int(BASE_MONTHLY_TOKENS * pct / 100)


def get_monthly_usage(user_id: int) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT tokens_used FROM token_usage_monthly WHERE user_id=? AND yyyymm=?",
        (user_id, _yyyymm()),
    ).fetchone()
    conn.close()
    return row["tokens_used"] if row else 0


def record_tokens(user_id: int, tokens: int) -> None:
    """Additive: safe to call once per AI call; accumulates within the
    current UTC month."""
    if not user_id or not tokens or tokens <= 0:
        return
    conn = get_db()
    conn.execute(
        """
        INSERT INTO token_usage_monthly (user_id, yyyymm, tokens_used)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, yyyymm)
        DO UPDATE SET tokens_used = tokens_used + excluded.tokens_used
        """,
        (user_id, _yyyymm(), tokens),
    )
    conn.commit()
    conn.close()


def check_token_quota(user_id: int, plan: str) -> dict:
    """
    Returns whether `user_id` may still consume AI tokens this month
    under `plan`'s token-quota %.

    `metered=False` means this plan isn't governed by this system at
    all (free/enterprise/unrecognized) -- callers should treat that as
    "allowed, nothing to check here", not as an error.
    """
    budget = plan_token_budget(plan)
    if budget is None:
        return {"allowed": True, "metered": False, "used": 0, "budget": None, "pct_used": None}
    used = get_monthly_usage(user_id)
    pct_used = round(used / budget * 100, 1) if budget else 0.0
    return {
        "allowed": used < budget,
        "metered": True,
        "used": used,
        "budget": budget,
        "pct_used": pct_used,
    }
