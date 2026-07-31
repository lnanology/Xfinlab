"""2026-07-30: usage counter for the new Intelligence API (api/intelligence.py).

Deliberately mirrors services/quota_service.py's sqlite counter pattern
(separate table, same INSERT ... ON CONFLICT DO UPDATE idiom) rather than
reusing it directly -- that service's FREE_LIMITS/plan strings are specific
to the logged-in-user AI-feature quotas (full_analysis/research/report) and
shouldn't be overloaded with an unrelated per-API-key concept.

TIER_LIMITS below reflect a RECOMMENDED pricing structure (2026-07-31),
reasoned from each endpoint's real relative cost (see ENDPOINT_WEIGHT
below -- events/sentiment are cheap RSS+one-model-call lookups, debate is
4 sequential LLM calls, intel is up to 2 LLM calls plus real OHLC/quant/
cross-asset lookups per cluster, the most expensive path in this router).
The corresponding $ prices are shown on intelligence-api.html (Free $0 /
Pro $49/mo / Enterprise custom) -- this is a RECOMMENDATION pending the
business owner's actual approval, not a unilaterally finalized decision;
adjust both this dict and intelligence-api.html's plan cards together if
the approved numbers differ.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "xfinlab.db")

# RECOMMENDED (2026-07-31) -- maps to intelligence-api.html: Free $0,
# Pro $49/month, Enterprise custom. "unlimited" tiers are represented as
# -1 (checked explicitly below), matching services/quota_service.py's
# convention for pro/starter. This is a recommendation, not a unilateral
# final decision -- see this module's docstring.
TIER_LIMITS = {
    "free": 100,
    "pro": 5000,
    "enterprise": -1,
}

# Debate is 4 sequential LLM calls per run (see services/agent_debate_service.py)
# -- far more expensive than a headline/sentiment lookup. Weight it heavier
# in the counter so a free-tier key can't cheaply exhaust the same "100
# calls" budget on the priciest endpoint. Recommended weighting, same
# pending-approval caveat as TIER_LIMITS above.
ENDPOINT_WEIGHT = {
    "events": 1,
    "sentiment": 1,
    "debate": 5,
    # 2026-07-31: AI Intelligence Engine feed (api/intelligence.py's
    # /v1/intel/latest + /v1/intel/{ticker}) -- each call can cluster
    # several headlines into up to `max_clusters` AI_NEWS_OBJECTs, and
    # each cluster may trigger up to 2 AI calls (Phase 1 summary + Phase 3
    # narrative) plus real OHLC/market-structure/historical-analog lookups
    # per affected ticker (Phase 2). Weighted heavier than `debate` (which
    # is a fixed 4-call cost) since this endpoint's cost scales with
    # max_clusters -- still a placeholder pending real cost-based pricing,
    # same caveat as every other number in this dict.
    "intel": 8,
    # 2026-07-31 (monetization batch, task #598): two more endpoints
    # exposing already-built engines as the "Decision/Market-Structure API"
    # direction from chat. No new AI calls -- `technical` is one yfinance/
    # Alpaca OHLC fetch + pure numpy/pandas computation (confluence, MACD,
    # market structure, chart patterns), `stress_test` is one OHLC fetch +
    # a vectorized numpy Monte Carlo resample (services/monte_carlo_service
    # .py already caps cost via MAX_HORIZON_DAYS/MAX_N_SIMULATIONS). Both
    # cheaper than `debate`/`intel` (no LLM call) but heavier than a plain
    # RSS lookup, since they do a real network fetch + nontrivial compute.
    "technical": 3,
    "stress_test": 3,
}


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intelligence_api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            UNIQUE(api_key, date)
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def check(api_key: str, tier: str) -> dict:
    """Read-only check -- does NOT increment. Call increment() separately
    after the request actually succeeds, mirroring quota_service.py's
    check()-then-increment() split (so a failed upstream call doesn't burn
    the caller's quota)."""
    limit = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    if limit == -1:
        return {"allowed": True, "used": 0, "limit": -1, "remaining": -1, "tier": tier}

    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_db()
    row = conn.execute(
        "SELECT count FROM intelligence_api_usage WHERE api_key=? AND date=?",
        (api_key, today),
    ).fetchone()
    conn.close()

    used = row["count"] if row else 0
    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "tier": tier,
    }


def increment(api_key: str, weight: int = 1):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _get_db()
    conn.execute(
        """
        INSERT INTO intelligence_api_usage (api_key, date, count)
        VALUES (?, ?, ?)
        ON CONFLICT(api_key, date)
        DO UPDATE SET count = count + excluded.count
        """,
        (api_key, today, weight),
    )
    conn.commit()
    conn.close()


def weight_for(endpoint: str) -> int:
    return ENDPOINT_WEIGHT.get(endpoint, 1)
