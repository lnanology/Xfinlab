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
