"""2026-07-30: Intelligence API v1 -- the first externally-sellable API
product for XFINLAB, built entirely on top of existing, already-working
services (rss_news_service/finbert_sentiment_service/agent_debate_service).
No new AI calls, no new data sources -- this is a packaging layer.

Positioning (per the "sell structured research, not raw news" direction
discussed in chat): every endpoint returns AI-structured JSON, never raw
article text -- consistent with rss_news_service.py's existing minimal-
retention policy (title/source/link/published_at only, never full body).

Auth: X-API-Key header, verified against a raw-sqlite api_keys table (see
services/api_key_service.py for why this isn't database/db.py's unused
SQLAlchemy layer). V1 has no self-serve signup/Stripe billing --
keys are issued manually by the admin via /intelligence/admin/issue-key
(gated by api.admin.verify_admin, same convention as every other admin
endpoint). This is a deliberate, honest stopgap: don't build a billing
system before there's a single paying customer to bill.

Versioned under /api/v1/intelligence/* -- the rest of this app's ~50
routers are unversioned flat /api/*; this is a clean-slate decision for
this one new product line, not a retrofit of the existing 50 endpoints
(that would be a large, separate, unnecessary migration).
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from services import api_key_service, intelligence_quota_service
from services import rss_news_service
from services.finbert_sentiment_service import is_available as finbert_available, analyze_batch
from services.agent_debate_service import is_available as debate_available, run_debate
from services.intelligence_pipeline_service import build_intelligence_feed
from api.admin import verify_admin

router = APIRouter()


def _envelope(data=None, error: Optional[str] = None, meta: Optional[dict] = None) -> dict:
    """Unified response shape for every endpoint in this router -- see chat
    discussion: half the value of an external API is that every response
    looks the same regardless of endpoint, so a developer's client code
    doesn't special-case each one."""
    return {"success": error is None, "data": data, "meta": meta or {}, "error": error}


def _require_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> dict:
    """Returns {"user_id":..., "tier":...} or raises 401/403. Not a FastAPI
    Depends() convention elsewhere in this codebase (see api/agent_debate.py
    -- everything here manually verifies a token param instead), so this
    stays consistent: called explicitly at the top of each endpoint, not
    injected via Depends."""
    result = api_key_service.verify_key(x_api_key)
    if not result["valid"]:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
    return result


def _check_and_spend_quota(api_key: str, tier: str, endpoint: str) -> dict:
    weight = intelligence_quota_service.weight_for(endpoint)
    quota = intelligence_quota_service.check(api_key, tier)
    if not quota["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded ({quota['used']}/{quota['limit']} calls used today for tier '{tier}')",
        )
    intelligence_quota_service.increment(api_key, weight=weight)
    return quota


@router.get("/intelligence/status")
def intelligence_status():
    """Public, unauthenticated -- lets a prospective developer check what's
    live before they even have a key, same pattern as
    GET /api/agent-debate/status."""
    return _envelope(data={
        "events": True,  # rss_news_service has no external gate
        "sentiment": finbert_available(),
        "debate": debate_available(),
    })


# ---------------------------------------------------------------------------
# "Request Early Access" landing page support (intelligence-api.html).
# V1 has no self-serve signup -- this is the conversation-first funnel:
# a prospective developer submits interest, the admin follows up manually
# and issues a key via /intelligence/admin/issue-key above once there's an
# actual conversation about pricing (per the 2026-07-30 "唔急住公開定價,
# 先用對話式定價" decision -- see chat history).
# ---------------------------------------------------------------------------
from pydantic import BaseModel, field_validator


class EarlyAccessRequest(BaseModel):
    # Plain str, not pydantic's EmailStr -- that type requires the
    # "email-validator" package, which isn't in requirements.txt (nothing
    # else in this codebase pulls it in either; api/feedback.py's own
    # `email` field is a plain Optional[str] for the same reason). A
    # lightweight manual check below is enough for a lead-capture form --
    # this isn't gating anything security-sensitive, just filtering
    # obviously-malformed submissions before they reach the admin inbox.
    email: str
    company: Optional[str] = None
    tier_interest: Optional[str] = None  # "free" / "pro" / "enterprise"
    message: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, v: str) -> str:
        v = (v or "").strip()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("Please provide a valid email address")
        return v


@router.get("/intelligence/plan-visibility")
def intelligence_plan_visibility():
    """Public, unauthenticated -- intelligence-api.html calls this on load
    to decide which of the 3 pricing tier cards to render. Backed by the
    same feature_flags table/admin.html toggle UI every other flag in this
    app already uses (api/admin.py's _DEFAULT_FLAGS: intel_plan_free_visible/
    intel_plan_pro_visible/intel_plan_enterprise_visible) -- the admin can
    hide any tier from the landing page without a redeploy, e.g. hiding
    Enterprise until there's a real reason to show it."""
    from api.admin import get_db as _admin_get_db

    conn = _admin_get_db()
    rows = conn.execute(
        "SELECT key, enabled FROM feature_flags WHERE key IN "
        "('intel_plan_free_visible','intel_plan_pro_visible','intel_plan_enterprise_visible')"
    ).fetchall()
    conn.close()
    flags = {r["key"]: bool(r["enabled"]) for r in rows}
    return _envelope(data={
        "free": flags.get("intel_plan_free_visible", True),
        "pro": flags.get("intel_plan_pro_visible", True),
        "enterprise": flags.get("intel_plan_enterprise_visible", True),
    })


@router.post("/intelligence/early-access")
def intelligence_early_access(body: EarlyAccessRequest):
    """Public -- the landing page's "Request Early Access" form posts here.
    Reuses api/feedback.py's existing `feedback` table (type=
    "intelligence_early_access") rather than a new bespoke table -- same
    insert-then-notify-admin shape that module already has, just a
    different `type` value so admin.html can list these separately (see
    GET /feedback/list's optional `type` filter)."""
    import sqlite3
    import os as _os

    db_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "xfinlab.db")
    conn = sqlite3.connect(db_path)
    message_parts = [f"tier_interest={body.tier_interest or 'unspecified'}"]
    if body.company:
        message_parts.append(f"company={body.company}")
    if body.message:
        message_parts.append(f"message={body.message}")
    message = " | ".join(message_parts)
    conn.execute(
        "INSERT INTO feedback (type, message, email) VALUES (?, ?, ?)",
        ("intelligence_early_access", message, body.email),
    )
    conn.commit()
    conn.close()

    try:
        from services.email_service import EmailService
        html = f"""
        <div style="font-family:Arial,sans-serif;padding:20px;background:#080c14;color:#e2e8f0">
            <h2 style="color:#00d4ff">Intelligence API -- Early Access Request</h2>
            <p><strong>Email:</strong> {body.email}</p>
            <p><strong>Company:</strong> {body.company or 'N/A'}</p>
            <p><strong>Tier interest:</strong> {body.tier_interest or 'unspecified'}</p>
            <p><strong>Message:</strong> {body.message or 'N/A'}</p>
        </div>
        """
        EmailService.send("abcoaj888@gmail.com", "[XFINLAB] Intelligence API early-access request", html)
    except Exception:
        pass

    return _envelope(data={"received": True})


@router.get("/intelligence/v1/events")
def intelligence_events(
    request: Request,
    ticker: Optional[str] = None,
    limit: int = 20,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "events")

    limit = max(1, min(limit, 100))
    if ticker:
        result = rss_news_service.search_headlines(query=ticker, limit=limit)
    else:
        result = rss_news_service.get_all_headlines(limit=limit)

    if result["status"] != "ok":
        return _envelope(data=[], error=result.get("message") or "No matching events found")

    events = [
        {
            "title": item["title"],
            "source": item["source"],
            "kind": item["kind"],
            "published_at": item["published_at"],
            "url": item["link"],
        }
        for item in result["items"]
    ]
    return _envelope(data=events, meta={"count": len(events), "ticker": ticker})


@router.get("/intelligence/v1/sentiment")
def intelligence_sentiment(
    ticker: str,
    limit: int = 10,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "sentiment")

    if not finbert_available():
        raise HTTPException(status_code=503, detail="Sentiment engine temporarily unavailable")

    limit = max(1, min(limit, 25))
    headlines = rss_news_service.search_headlines(query=ticker, limit=limit)
    if headlines["status"] != "ok" or not headlines["items"]:
        return _envelope(data={"ticker": ticker, "articles_analyzed": 0, "results": []},
                          meta={"message": "No recent headlines found for this ticker"})

    titles = [item["title"] for item in headlines["items"]]
    sentiment = analyze_batch(titles)
    if not sentiment.get("available"):
        raise HTTPException(status_code=503, detail=sentiment.get("message", "Sentiment engine unavailable"))

    scores = [r["score"] for r in sentiment["results"]]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    results = [
        {
            "headline": title,
            "label": r["label"],
            "confidence_pct": r["confidence_pct"],
            "score": r["score"],
        }
        for title, r in zip(titles, sentiment["results"])
    ]
    return _envelope(
        data={"ticker": ticker, "average_score": avg_score, "results": results},
        meta={"articles_analyzed": len(results), "source": "finbert"},
    )


@router.get("/intelligence/v1/debate")
def intelligence_debate(
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Wraps the existing 4-call Bull/Bear/Risk-Manager debate. This is the
    single most expensive endpoint in this router (see
    services/agent_debate_service.py) -- weighted 5x in the quota counter,
    same reasoning api/agent_debate.py already applies to logged-in users."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "debate")

    if not debate_available():
        raise HTTPException(status_code=503, detail="Debate engine temporarily unavailable")

    ticker = ticker.upper()
    context = {}
    try:
        from services.technical_analysis_service import get_technical_analysis
        tech = get_technical_analysis(ticker)
        if tech and "error" not in tech:
            context = {
                "confluence": tech.get("confluence"),
                "decision_levels": tech.get("decision_levels"),
            }
    except Exception:
        context = {}

    result = run_debate(ticker, context)
    if not result.get("available"):
        raise HTTPException(status_code=503, detail=result.get("message", "Debate engine unavailable"))

    return _envelope(data=result, meta={"ticker": ticker})


# ---------------------------------------------------------------------------
# Phase 4 (2026-07-31): AI Intelligence Engine feed -- the "AI_NEWS_OBJECT"
# product from the user's proposal (see services/intelligence_pipeline_service
# .py's docstring for the full Phase 1-3 pipeline this wraps). Unlike
# /v1/events above (raw per-article headlines), these two endpoints return
# ORIGINAL structured analysis: same-event headline clusters with real
# entity/sentiment/quant fields and an AI-written narrative -- the
# "fact extraction, not republishing" product the user's proposal asked
# for. Weighted heavily in the quota counter (see
# intelligence_quota_service.ENDPOINT_WEIGHT["intel"]) since it's the most
# expensive endpoint in this router.
#
# Route ordering matters: /intel/latest must be registered BEFORE
# /intel/{ticker} so FastAPI doesn't match "latest" as a ticker path param.
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/intel/latest")
def intelligence_latest(
    limit: int = 5,
    lang: str = "zh-HK",
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "intel")

    # Caps how many event-clusters get the full (up to 2-AI-call +
    # per-ticker quant lookup) treatment per request -- see
    # build_intelligence_feed()'s own cost-note docstring.
    limit = max(1, min(limit, 10))

    result = rss_news_service.get_all_headlines(limit=60)
    if result["status"] != "ok" or not result["items"]:
        return _envelope(data=[], error=result.get("message") or "No recent events found")

    feed = build_intelligence_feed(result["items"], max_clusters=limit, lang=lang)
    return _envelope(data=feed, meta={"count": len(feed)})


@router.get("/intelligence/v1/intel/{ticker}")
def intelligence_ticker(
    ticker: str,
    limit: int = 5,
    lang: str = "zh-HK",
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "intel")

    limit = max(1, min(limit, 10))
    ticker = ticker.upper()

    result = rss_news_service.search_headlines(query=ticker, limit=60)
    if result["status"] != "ok" or not result["items"]:
        return _envelope(data=[], error=result.get("message") or f"No recent events found for {ticker}")

    feed = build_intelligence_feed(result["items"], max_clusters=limit, lang=lang)
    return _envelope(data=feed, meta={"ticker": ticker, "count": len(feed)})


# ---------------------------------------------------------------------------
# Admin: key issuance. V1 stopgap only -- no self-serve signup, no billing.
# ---------------------------------------------------------------------------

@router.post("/intelligence/admin/issue-key")
def issue_key(email: str, tier: str = "free", token: str = None, request: Request = None):
    verify_admin(token, action="issue_intelligence_api_key", request=request)
    result = api_key_service.issue_key(email, tier)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return _envelope(data=result)


@router.get("/intelligence/admin/keys")
def list_keys(email: str, token: str = None, request: Request = None):
    verify_admin(token, action="list_intelligence_api_keys", request=request)
    return _envelope(data=api_key_service.list_keys_for_email(email))


@router.post("/intelligence/admin/revoke-key")
def revoke_key(key_id: int, token: str = None, request: Request = None):
    verify_admin(token, action="revoke_intelligence_api_key", request=request)
    ok = api_key_service.revoke_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return _envelope(data={"revoked": key_id})
