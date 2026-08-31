"""2026-08-28 (AJ, "0成本推廣" -> free public tool pages): backs the 3
unauthenticated marketing-demo pages (free-market-regime.html,
free-stock-sentiment-api.html, free-technical-analysis-api.html) that exist
purely to prove the Intelligence API's data is real, with zero signup
friction, and funnel visitors into getting a free X-API-Key.

2026-08-31: added 3 more demo endpoints (real-estate, supply-chain,
consumer-demand) backing the same-named free-*-api.html pages, for the
cross-industry expansion that shipped 2026-08-30/31. Same no-trim
posture as vix-term-structure below (each of these is already a small,
scoped response, not a large teaser-worthy payload like sentiment/
technical) -- the only "trim" is that these 3 only have real data for a
specific whitelist of tickers (see each service's _TICKER_TO_NAME), so
unlike sentiment/technical which accept any ticker, most random tickers
here will legitimately return null. The demo pages surface the working
ticker list directly rather than let a visitor guess and hit dead ends.

NOT the same thing as api/public_demo.py (`/api/demo/analyze/{ticker}`,
the homepage's one-time 5-minute anonymous trial for the *consumer*
product) -- that one gates a full teaser report behind a strict per-IP
one-time window to push signup on the consumer funnel. This module is the
*developer/API* funnel: unlimited (rate-limited) repeat use is the point,
since a developer evaluating the API needs to try it more than once before
getting a key, and the response shape deliberately mirrors the real
`/intelligence/v1/*` endpoints rather than the consumer app's UI shape.

Deliberately distinct from api/intelligence.py's paid/free-tier `/v1/*`
endpoints:
  1. No X-API-Key required at all -- a first-time visitor tries it cold.
  2. Tightly per-IP rate-limited (shared `services.rate_limiter.limiter`)
     since there's no API key to meter usage against.
  3. Every response is a deliberately trimmed subset of what the real
     `/intelligence/v1/*` endpoint returns -- enough to prove the number is
     real and live, not enough to replace actually getting a key. (E.g. the
     technical teaser drops market_structure/patterns/decision_levels,
     which are Intelligence API selling points.)
  4. Reuses the exact same underlying service calls as the paid endpoints
     (never a separate, possibly-drifting computation) -- so what a visitor
     sees here is provably the same engine, just a smaller slice of it.
"""
from fastapi import APIRouter, Request

from services.rate_limiter import limiter

router = APIRouter()

_DEMO_LIMIT = "8/minute"
_CTA = "Get a free API key (no card required): https://www.xfinlab.com/intelligence-api.html"


@router.get("/free-tools-demo/vix-term-structure")
@limiter.limit(_DEMO_LIMIT)
def demo_vix_term_structure(request: Request):
    """Global, no ticker needed -- backs free-market-regime.html. Same
    services.cboe_vix_service.get_snapshot() the paid
    /intelligence/v1/vix-term-structure endpoint calls; nothing trimmed
    here since this one's already a single global snapshot, not
    per-ticker depth."""
    from services.cboe_vix_service import get_snapshot

    snap = get_snapshot()
    if not snap or not snap.get("available"):
        return {"success": False, "error": "VIX term structure temporarily unavailable", "cta": _CTA}
    return {
        "success": True,
        "data": {
            "as_of": snap.get("as_of"),
            "term_structure": snap.get("term_structure"),
            "structure": snap.get("structure"),
            "vix3m_minus_vix": snap.get("vix3m_minus_vix"),
            "attribution": snap.get("attribution"),
        },
        "cta": _CTA,
    }


@router.get("/free-tools-demo/sentiment")
@limiter.limit(_DEMO_LIMIT)
def demo_sentiment(request: Request, ticker: str = ""):
    """Backs free-stock-sentiment-api.html. Same FinBERT pipeline as the
    paid /intelligence/v1/sentiment endpoint (rss_news_service +
    finbert_sentiment_service), teaser-capped to 5 headlines instead of the
    paid endpoint's up-to-25."""
    from services import rss_news_service
    from services.finbert_sentiment_service import is_available as finbert_available, analyze_batch

    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "ticker query param is required", "cta": _CTA}
    if not finbert_available():
        return {"success": False, "error": "Sentiment engine temporarily unavailable", "cta": _CTA}

    headlines = rss_news_service.search_headlines(query=ticker, limit=5)
    if headlines["status"] != "ok" or not headlines["items"]:
        return {"success": True, "data": {"ticker": ticker, "articles_analyzed": 0, "results": []},
                "meta": {"message": "No recent headlines found for this ticker"}, "cta": _CTA}

    titles = [item["title"] for item in headlines["items"]]
    sentiment = analyze_batch(titles)
    if not sentiment.get("available"):
        return {"success": False, "error": sentiment.get("message", "Sentiment engine unavailable"), "cta": _CTA}

    scores = [r["score"] for r in sentiment["results"]]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    results = [
        {"headline": title, "label": r["label"], "score": r["score"]}
        for title, r in zip(titles, sentiment["results"])
    ]
    return {
        "success": True,
        "data": {"ticker": ticker, "average_score": avg_score, "results": results},
        "meta": {"articles_analyzed": len(results), "source": "finbert",
                  "note": "Preview limited to 5 headlines. The full API returns up to 25."},
        "cta": _CTA,
    }


@router.get("/free-tools-demo/technical")
@limiter.limit(_DEMO_LIMIT)
def demo_technical(request: Request, ticker: str = ""):
    """Backs free-technical-analysis-api.html. Same
    services.technical_analysis_service.get_technical_analysis() the paid
    /intelligence/v1/technical/{ticker} endpoint calls, trimmed to a small
    teaser subset (trend/RSI/confluence/support-resistance) -- deliberately
    dropping market_structure, chart patterns, decision_levels and the raw
    OHLC series, which stay Intelligence API selling points, not free-demo
    content."""
    from services.technical_analysis_service import get_technical_analysis

    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "ticker query param is required", "cta": _CTA}

    tech = get_technical_analysis(ticker, period="6mo", interval="1d", lang="en")
    if not tech or "error" in tech:
        return {"success": False, "error": (tech or {}).get("error", f"No technical data available for {ticker}"), "cta": _CTA}

    confluence = tech.get("confluence") or {}
    return {
        "success": True,
        "data": {
            "symbol": tech.get("symbol", ticker),
            "last_close": tech.get("last_close"),
            "trend": tech.get("trend"),
            "rsi": tech.get("rsi"),
            "support": tech.get("support"),
            "resistance": tech.get("resistance"),
            "confluence_direction": confluence.get("direction"),
            "confluence_score": confluence.get("score"),
            "confidence_pct": confluence.get("confidence_pct"),
        },
        "meta": {"note": "Preview only. The full API also returns MACD, market structure (BOS/CHOCH/liquidity), chart patterns and decision levels."},
        "cta": _CTA,
    }


@router.get("/free-tools-demo/real-estate")
@limiter.limit(_DEMO_LIMIT)
def demo_real_estate(request: Request, ticker: str = ""):
    """Backs free-real-estate-api.html. Same services.real_estate_service
    .get_real_estate_context_for_ticker() the paid /intelligence/v1/
    real-estate/{ticker} endpoint calls -- no trimming, this is already a
    small scoped response. Only whitelisted housing-linked tickers
    return real data; see that module's _TICKER_TO_NAME."""
    from services.real_estate_service import get_real_estate_context_for_ticker, _TICKER_TO_NAME

    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "ticker query param is required",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}

    result = get_real_estate_context_for_ticker(ticker)
    if not result:
        return {"success": False, "error": f"No housing-market linkage for {ticker}",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}
    return {"success": True, "data": result, "cta": _CTA}


@router.get("/free-tools-demo/supply-chain")
@limiter.limit(_DEMO_LIMIT)
def demo_supply_chain(request: Request, ticker: str = ""):
    """Backs free-supply-chain-api.html. Same services.supply_chain_service
    .get_supply_chain_context_for_ticker() the paid /intelligence/v1/
    supply-chain/{ticker} endpoint calls. Only whitelisted freight/
    logistics tickers return real data; see that module's
    _TICKER_TO_NAME."""
    from services.supply_chain_service import get_supply_chain_context_for_ticker, _TICKER_TO_NAME

    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "ticker query param is required",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}

    result = get_supply_chain_context_for_ticker(ticker)
    if not result:
        return {"success": False, "error": f"No supply-chain linkage for {ticker}",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}
    return {"success": True, "data": result, "cta": _CTA}


@router.get("/free-tools-demo/consumer-demand")
@limiter.limit(_DEMO_LIMIT)
def demo_consumer_demand(request: Request, ticker: str = ""):
    """Backs free-consumer-demand-api.html. Same
    services.consumer_demand_service.get_consumer_demand_context_for_
    ticker() the paid /intelligence/v1/consumer-demand/{ticker} endpoint
    calls. Only whitelisted retail/consumer tickers return real data;
    see that module's _TICKER_TO_NAME."""
    from services.consumer_demand_service import get_consumer_demand_context_for_ticker, _TICKER_TO_NAME

    ticker = ticker.upper().strip()
    if not ticker:
        return {"success": False, "error": "ticker query param is required",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}

    result = get_consumer_demand_context_for_ticker(ticker)
    if not result:
        return {"success": False, "error": f"No consumer-spending linkage for {ticker}",
                "meta": {"tickers": sorted(_TICKER_TO_NAME.keys())}, "cta": _CTA}
    return {"success": True, "data": result, "cta": _CTA}


@router.get("/free-tools-demo/opportunity-radar")
@limiter.limit(_DEMO_LIMIT)
def demo_opportunity_radar(request: Request):
    """Backs opportunity-radar.html. Same services.opportunity_radar_
    service.get_opportunity_radar() the paid /intelligence/v1/
    opportunity-radar endpoint calls -- global, no ticker, no trimming
    (this is already the full honest computation, not a large payload
    with selling-point fields to hold back)."""
    from services.opportunity_radar_service import get_opportunity_radar

    result = get_opportunity_radar()
    if not result or not result.get("available"):
        return {"success": False, "error": (result or {}).get("message", "Opportunity Radar temporarily unavailable"), "cta": _CTA}
    return {"success": True, "data": result, "cta": _CTA}
