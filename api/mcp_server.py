"""2026-08-09 (XFINLAB_Final_Strategy.md section 5: MCP Server) -- exposes a
subset of api/intelligence.py's v1 endpoints as MCP (Model Context
Protocol) tools, so AI agents (Claude, Cursor, and other MCP-aware
clients) can call them directly as tool calls instead of a developer
hand-writing HTTP client code against the REST API.

Why this exists: this was the one genuinely useful idea extracted from
several large, AI-generated "Financial Intelligence Factory" proposals
pasted into chat over a few rounds -- everything else in those proposals
either re-proposed selling AI-generated directional stock probability
data (the standing compliance red line this codebase avoids, see
XFINLAB_Final_Strategy.md section 3) or duplicated engines that already
exist. This one is different: it is a distribution layer over data that
is already real, already structured, and already sold via the REST API
-- it just makes that data reachable the way AI agents actually consume
tools in 2026, and it fits the B2B-API-first pivot directly.

Auth and quota: identical to the REST endpoints. Every tool call requires
the same X-API-Key issued by /intelligence/v1/signup or the admin panel,
and spends the same daily quota via services/intelligence_quota_service
-- there is no separate free ride through MCP. The key can be supplied
either as the `X-API-Key` HTTP header (preferred -- most MCP clients that
support "remote server with custom headers" configs, e.g. Claude Desktop,
can set this once) or as an `api_key` argument on the tool call itself,
for clients that can't set custom headers.

2026-09-15: a caller may additionally present an mcp-marketplace.io
license key for this listing (`X-Marketplace-License-Key` header or a
`marketplace_license_key`/`license_key` tool argument or query param --
see _resolve_marketplace_license_key() below). If it verifies against the
mcp-marketplace-license SDK, the caller's free-tier XFINLAB key is treated
as Pro-tier for that call's quota check only -- this is additive only, it
can never block or downgrade a request that was already valid.

Implementation note: hand-rolled JSON-RPC 2.0 over a single stateless
POST endpoint (the MCP "Streamable HTTP" transport's non-SSE mode)
instead of adding the `mcp` PyPI SDK as a new dependency -- consistent
with this codebase's established pattern for external protocols/SDKs
(services/tts_service.py and services/youtube_upload_service.py both use
raw `requests` calls instead of the official Google SDKs, for the same
reason: fewer moving parts that can break a Railway deploy, see the
project's standing "keep go build" rule). The protocol surface actually
needed here (`initialize`, `tools/list`, `tools/call`, and tolerating the
`notifications/initialized` notification) is small enough that hand-
rolling it is the more honest choice than pulling in an SDK for it.

No server-initiated messages, no elicitation, no sampling, no streaming
tool output -- every tool call here is a simple synchronous request that
returns one JSON result, so the simpler single-JSON-response mode of the
Streamable HTTP spec is sufficient. No Mcp-Session-Id session tracking is
needed for a stateless server like this one.
"""
import json
import os
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services import api_key_service, intelligence_quota_service
from services import rss_news_service
from services.finbert_sentiment_service import is_available as finbert_available, analyze_batch
from services.intelligence_pipeline_service import build_intelligence_feed

# 2026-09-15 (AJ: "你做左先" -- go ahead and wire up the real license-key
# gating now, so a future "Monthly" price on the mcp-marketplace.io listing
# actually means something instead of charging for what a free XFINLAB key
# already unlocks). Import is best-effort: the whole point of this SDK
# integration is additive (it can only ever UPGRADE a caller's effective
# tier, never block one that's already valid) so a missing package or a
# network hiccup against the marketplace's verification API must never
# break the existing X-API-Key auth path this server already had. Same
# "dormant until configured" posture as EIA_API_KEY/RESEND_API_KEY
# elsewhere in this codebase.
try:
    from mcp_marketplace_license import verify_license as _verify_marketplace_license
except Exception:
    _verify_marketplace_license = None

# The slug mcp-marketplace.io assigned to this listing. Defaults to the
# server's own name (what was actually submitted in the Submit form's
# Source step) but is overridable via env var without a redeploy, since
# the real assigned slug wasn't confirmed at integration time -- if it
# turns out to differ, set MCP_MARKETPLACE_SLUG in Railway rather than
# editing this file.
_MARKETPLACE_SLUG = os.getenv("MCP_MARKETPLACE_SLUG", "xfinlab-intelligence")

router = APIRouter()

_PROTOCOL_VERSION = "2025-06-18"
_SERVER_INFO = {"name": "xfinlab-intelligence", "version": "1.0.0"}

# ---------------------------------------------------------------------------
# Tool definitions -- kept in one place so tools/list and tools/call can't
# drift out of sync with each other.
# ---------------------------------------------------------------------------
_TOOLS = [
    {
        "name": "get_market_events",
        "description": (
            "Get recent market/company news headlines from XFINLAB's aggregated "
            "real-time news feed (RSS-sourced, deduplicated). Optionally filter by "
            "ticker/company name. Returns title, source, kind, published_at, url "
            "for each item -- no article body text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "XFINLAB Intelligence API key (X-API-Key). Omit if supplied via HTTP header instead."},
                "marketplace_license_key": {"type": "string", "description": "Optional: an mcp-marketplace.io license key for this listing's paid tier. If valid, upgrades a free XFINLAB API key's daily quota to Pro for this call. Omit if supplied via the X-Marketplace-License-Key header instead, or if not using a marketplace license."},
                "ticker": {"type": "string", "description": "Optional ticker or company name to filter by, e.g. 'NVDA'."},
                "limit": {"type": "integer", "description": "Max results, 1-100.", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_sentiment",
        "description": (
            "Get FinBERT-based sentiment analysis of recent headlines for a ticker. "
            "Returns per-headline label/confidence/score plus an average score. "
            "Real model inference, not a fabricated estimate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "XFINLAB Intelligence API key (X-API-Key). Omit if supplied via HTTP header instead."},
                "marketplace_license_key": {"type": "string", "description": "Optional: an mcp-marketplace.io license key for this listing's paid tier. If valid, upgrades a free XFINLAB API key's daily quota to Pro for this call. Omit if supplied via the X-Marketplace-License-Key header instead, or if not using a marketplace license."},
                "ticker": {"type": "string", "description": "Ticker to analyze, e.g. 'AAPL'."},
                "limit": {"type": "integer", "description": "Number of recent headlines to analyze, 1-25.", "default": 10},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technical_analysis",
        "description": (
            "Get confluence direction/confidence, trend, MACD, volume, chart "
            "patterns, and market-structure signals (BOS/CHOCH/liquidity-sweep/"
            "order-flow/volume-profile/institutional-footprint) for one ticker, "
            "computed from real OHLC price data -- the same engine that powers "
            "XFINLAB's chart-analysis and ai-analysis pages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "XFINLAB Intelligence API key (X-API-Key). Omit if supplied via HTTP header instead."},
                "marketplace_license_key": {"type": "string", "description": "Optional: an mcp-marketplace.io license key for this listing's paid tier. If valid, upgrades a free XFINLAB API key's daily quota to Pro for this call. Omit if supplied via the X-Marketplace-License-Key header instead, or if not using a marketplace license."},
                "ticker": {"type": "string", "description": "Ticker to analyze, e.g. 'TSLA', '0700.HK'."},
                "period": {"type": "string", "description": "History window, e.g. '6mo', '1y'.", "default": "6mo"},
                "interval": {"type": "string", "description": "Candle interval, e.g. '1d'.", "default": "1d"},
                "lang": {"type": "string", "description": "Language for text labels, e.g. 'en', 'zh-HK'.", "default": "en"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_intelligence_feed",
        "description": (
            "Get AI-structured event clusters from recent news: same-story headline "
            "clusters with entity/sentiment/quant-context fields and an AI-written "
            "narrative summary. Optionally scoped to one ticker; otherwise returns "
            "the latest cross-market feed. This is structured fact extraction, not "
            "republished article text, and never includes a directional trading "
            "signal or probability estimate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "XFINLAB Intelligence API key (X-API-Key). Omit if supplied via HTTP header instead."},
                "marketplace_license_key": {"type": "string", "description": "Optional: an mcp-marketplace.io license key for this listing's paid tier. If valid, upgrades a free XFINLAB API key's daily quota to Pro for this call. Omit if supplied via the X-Marketplace-License-Key header instead, or if not using a marketplace license."},
                "ticker": {"type": "string", "description": "Optional ticker to scope the feed to, e.g. 'MSFT'."},
                "limit": {"type": "integer", "description": "Max event clusters, 1-10.", "default": 5},
                "lang": {"type": "string", "description": "Language for the narrative summary.", "default": "en"},
            },
            "required": [],
        },
    },
    {
        "name": "get_global_market_map",
        "description": (
            "Get a cross-region global market snapshot ('World Engine'): macro "
            "indicators (GDP growth/inflation/unemployment, with source "
            "attribution -- world_bank/fred/ecb), filtered regional headlines, "
            "and FinBERT sentiment for each requested region, plus a top-level "
            "global headlines feed (GDELT). Regions: us, europe, japan, korea, "
            "china, hk, tw, sea, me, latam. No AI narrative, no directional "
            "signal -- structured real data only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "XFINLAB Intelligence API key (X-API-Key). Omit if supplied via HTTP header instead."},
                "marketplace_license_key": {"type": "string", "description": "Optional: an mcp-marketplace.io license key for this listing's paid tier. If valid, upgrades a free XFINLAB API key's daily quota to Pro for this call. Omit if supplied via the X-Marketplace-License-Key header instead, or if not using a marketplace license."},
                "regions": {"type": "string", "description": "Comma-separated region keys, e.g. 'us,hk,china'. Omit for all 10 regions."},
                "news_limit": {"type": "integer", "description": "Headlines per region, 1-20.", "default": 6},
                "include_sentiment": {"type": "boolean", "description": "Whether to run FinBERT sentiment on each region's headlines.", "default": True},
            },
            "required": [],
        },
    },
]


def _resolve_api_key(request: Request, arguments: dict) -> Optional[str]:
    header_key = request.headers.get("x-api-key")
    if header_key:
        return header_key
    arg_key = arguments.get("api_key")
    if arg_key:
        return arg_key
    # 2026-09-04: some MCP gateways/marketplaces (e.g. Smithery's config
    # builder) pass a user-configured credential as a URL query parameter
    # on the server URL itself rather than as a real HTTP header or a
    # JSON-RPC tool-call argument -- their own connection-diagram preview
    # showed `https://api.xfinlab.com/api/mcp?X-API-Key={X-API-Key}` for a
    # parameter the user had named "X-API-Key". Accept a few likely query
    # param spellings as a last-resort fallback so listings on gateways
    # that only support this delivery style still work, without changing
    # behavior for the two methods already documented (header / tool arg).
    for param_name in ("X-API-Key", "x-api-key", "api_key", "apiKey"):
        q_key = request.query_params.get(param_name)
        if q_key:
            return q_key
    return None


def _resolve_marketplace_license_key(request: Request, arguments: dict) -> Optional[str]:
    """Mirrors _resolve_api_key()'s header -> tool-arg -> query-param
    fallback chain exactly, for the same reason: this is a shared remote
    multi-tenant server, so there's no process-wide env var that could
    identify one caller's license the way the SDK's own MCP_LICENSE_KEY
    default assumes for a local single-tenant server -- the key has to be
    pulled off each individual request instead."""
    header_key = request.headers.get("x-marketplace-license-key") or request.headers.get("x-license-key")
    if header_key:
        return header_key
    arg_key = arguments.get("marketplace_license_key") or arguments.get("license_key")
    if arg_key:
        return arg_key
    for param_name in ("marketplace_license_key", "license_key", "licenseKey"):
        q_key = request.query_params.get(param_name)
        if q_key:
            return q_key
    return None


def _has_valid_marketplace_license(request: Request, arguments: dict) -> bool:
    """Best-effort, never raises: a missing package, an unreachable
    verification API, a missing key, or an invalid key all just mean "no"
    here. This can only ever upgrade a caller's effective tier for quota
    purposes below -- it never blocks or downgrades a caller who already
    has a valid XFINLAB X-API-Key, so failing closed on any error is safe."""
    if _verify_marketplace_license is None:
        return False
    license_key = _resolve_marketplace_license_key(request, arguments)
    if not license_key:
        return False
    try:
        result = _verify_marketplace_license(slug=_MARKETPLACE_SLUG, key=license_key)
        return bool(result and result.get("valid"))
    except Exception:
        return False


def _auth_and_quota(request: Request, arguments: dict, endpoint: str) -> dict:
    """Returns {"ok": True, "tier": ...} or {"ok": False, "message": ...} --
    deliberately never raises, since tool-call errors must be reported as
    MCP tool content (isError: true), not as JSON-RPC/HTTP-level failures
    (an invalid key is a normal, expected outcome for a tool call, not a
    protocol error).

    2026-09-15: `tier` used for the quota check is now the EFFECTIVE tier,
    which is upgraded free->pro when a valid mcp-marketplace.io license key
    is also presented on the same request (see _has_valid_marketplace_
    license() above). Deliberately applied uniformly across every tool
    here rather than hand-picking specific "pro-gated" tools: this whole
    server already prices access purely by tier (see intelligence_quota_
    service.TIER_LIMITS + the pricing string in mcp_info() below), and a
    marketplace license is meant to stand in for a paid XFINLAB Pro key,
    not a separate, narrower entitlement -- singling out a subset of tools
    would say something about the product this server doesn't actually
    have (no tool here is Pro-only; the difference between tiers has
    always been quota, not feature access), and would drift out of sync
    with TIER_LIMITS the moment either changes independently. An
    already-Pro or Enterprise XFINLAB key is left untouched either way --
    this can only ever raise a free caller's ceiling, never lower anyone
    else's."""
    api_key = _resolve_api_key(request, arguments)
    if not api_key:
        return {"ok": False, "message": "Missing API key -- supply it via the X-API-Key header or an 'api_key' argument. Get a free key at https://www.xfinlab.com/intelligence-api.html"}
    auth = api_key_service.verify_key(api_key)
    if not auth["valid"]:
        return {"ok": False, "message": "Invalid or expired API key."}

    effective_tier = auth["tier"]
    marketplace_licensed = False
    if effective_tier == "free" and _has_valid_marketplace_license(request, arguments):
        effective_tier = "pro"
        marketplace_licensed = True

    weight = intelligence_quota_service.weight_for(endpoint)
    quota = intelligence_quota_service.check(api_key, effective_tier)
    if not quota["allowed"]:
        return {"ok": False, "message": f"Daily quota exceeded ({quota['used']}/{quota['limit']} calls used today for tier '{effective_tier}')."}
    intelligence_quota_service.increment(api_key, weight=weight)
    return {"ok": True, "tier": effective_tier, "marketplace_licensed": marketplace_licensed}


def _tool_result(data: Any, is_error: bool = False) -> dict:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_get_market_events(request: Request, arguments: dict) -> dict:
    auth = _auth_and_quota(request, arguments, "events")
    if not auth["ok"]:
        return _tool_result(auth["message"], is_error=True)

    ticker = arguments.get("ticker")
    limit = max(1, min(int(arguments.get("limit", 20) or 20), 100))
    result = rss_news_service.search_headlines(query=ticker, limit=limit) if ticker else rss_news_service.get_all_headlines(limit=limit)
    if result["status"] != "ok":
        return _tool_result({"events": [], "message": result.get("message") or "No matching events found"})

    events = [
        {"title": i["title"], "source": i["source"], "kind": i["kind"], "published_at": i["published_at"], "url": i["link"]}
        for i in result["items"]
    ]
    return _tool_result({"events": events, "count": len(events), "ticker": ticker})


def _call_get_sentiment(request: Request, arguments: dict) -> dict:
    auth = _auth_and_quota(request, arguments, "sentiment")
    if not auth["ok"]:
        return _tool_result(auth["message"], is_error=True)

    ticker = (arguments.get("ticker") or "").strip()
    if not ticker:
        return _tool_result("Missing required argument: ticker", is_error=True)
    if not finbert_available():
        return _tool_result("Sentiment engine temporarily unavailable", is_error=True)

    limit = max(1, min(int(arguments.get("limit", 10) or 10), 25))
    headlines = rss_news_service.search_headlines(query=ticker, limit=limit)
    if headlines["status"] != "ok" or not headlines["items"]:
        return _tool_result({"ticker": ticker, "articles_analyzed": 0, "results": [], "message": "No recent headlines found for this ticker"})

    titles = [i["title"] for i in headlines["items"]]
    sentiment = analyze_batch(titles)
    if not sentiment.get("available"):
        return _tool_result(sentiment.get("message", "Sentiment engine unavailable"), is_error=True)

    scores = [r["score"] for r in sentiment["results"]]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None
    results = [
        {"headline": t, "label": r["label"], "confidence_pct": r["confidence_pct"], "score": r["score"]}
        for t, r in zip(titles, sentiment["results"])
    ]
    return _tool_result({"ticker": ticker, "average_score": avg_score, "articles_analyzed": len(results), "results": results})


def _call_get_technical_analysis(request: Request, arguments: dict) -> dict:
    auth = _auth_and_quota(request, arguments, "technical")
    if not auth["ok"]:
        return _tool_result(auth["message"], is_error=True)

    ticker = (arguments.get("ticker") or "").strip().upper()
    if not ticker:
        return _tool_result("Missing required argument: ticker", is_error=True)

    from services.technical_analysis_service import get_technical_analysis

    period = arguments.get("period", "6mo")
    interval = arguments.get("interval", "1d")
    lang = arguments.get("lang", "en")
    tech = get_technical_analysis(ticker, period=period, interval=interval, lang=lang)
    if not tech or "error" in tech:
        return _tool_result((tech or {}).get("error", f"No technical data available for {ticker}"), is_error=True)
    return _tool_result(tech)


def _call_get_intelligence_feed(request: Request, arguments: dict) -> dict:
    auth = _auth_and_quota(request, arguments, "intel")
    if not auth["ok"]:
        return _tool_result(auth["message"], is_error=True)

    ticker = arguments.get("ticker")
    limit = max(1, min(int(arguments.get("limit", 5) or 5), 10))
    lang = arguments.get("lang", "en")

    result = rss_news_service.search_headlines(query=ticker, limit=60) if ticker else rss_news_service.get_all_headlines(limit=60)
    if result["status"] != "ok" or not result["items"]:
        return _tool_result({"feed": [], "message": result.get("message") or "No recent events found"})

    feed = build_intelligence_feed(result["items"], max_clusters=limit, lang=lang)
    return _tool_result({"feed": feed, "count": len(feed), "ticker": ticker})


def _call_get_global_market_map(request: Request, arguments: dict) -> dict:
    auth = _auth_and_quota(request, arguments, "world_map")
    if not auth["ok"]:
        return _tool_result(auth["message"], is_error=True)

    from services.world_engine_service import get_global_market_map

    regions_arg = arguments.get("regions")
    region_list = [r.strip() for r in regions_arg.split(",") if r.strip()] if regions_arg else None
    news_limit = max(1, min(int(arguments.get("news_limit", 6) or 6), 20))
    include_sentiment = bool(arguments.get("include_sentiment", True))

    result = get_global_market_map(regions=region_list, news_limit=news_limit, include_sentiment=include_sentiment)
    if not result.get("available"):
        return _tool_result(result.get("message", "World market map unavailable"), is_error=True)
    return _tool_result(result)


_TOOL_HANDLERS = {
    "get_market_events": _call_get_market_events,
    "get_sentiment": _call_get_sentiment,
    "get_technical_analysis": _call_get_technical_analysis,
    "get_intelligence_feed": _call_get_intelligence_feed,
    "get_global_market_map": _call_get_global_market_map,
}


def _jsonrpc_result(msg_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


@router.post("/mcp")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content=_jsonrpc_error(None, -32700, "Parse error: invalid JSON"))

    msg_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    # Notifications (no "id") get no response body per JSON-RPC/MCP spec --
    # e.g. the client's post-initialize "notifications/initialized" ping.
    is_notification = "id" not in body

    if method == "initialize":
        result = {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": _SERVER_INFO,
        }
        return JSONResponse(content=_jsonrpc_result(msg_id, result))

    if method == "notifications/initialized" or (is_notification and method):
        return JSONResponse(status_code=202, content=None)

    if method == "tools/list":
        return JSONResponse(content=_jsonrpc_result(msg_id, {"tools": _TOOLS}))

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            return JSONResponse(content=_jsonrpc_error(msg_id, -32602, f"Unknown tool: {tool_name}"))
        try:
            tool_result = handler(request, arguments)
        except Exception as e:
            tool_result = _tool_result(f"Internal error handling tool call: {e}", is_error=True)
        return JSONResponse(content=_jsonrpc_result(msg_id, tool_result))

    if method == "ping":
        return JSONResponse(content=_jsonrpc_result(msg_id, {}))

    return JSONResponse(content=_jsonrpc_error(msg_id, -32601, f"Method not found: {method}"))


@router.get("/mcp")
def mcp_info():
    """Human-facing info page for anyone who opens the MCP URL directly in a
    browser instead of connecting an MCP client to it.

    2026-09-15 (AJ: MCP Marketplace listing follow-up): added a `pricing`
    field. This server was already a "remote hosted" MCP server per MCP
    Marketplace's own two-model taxonomy (auth/quota handled server-side,
    same X-API-Key + tier system as the REST API -- no separate MCP-only
    gating needed), so listing it there needs no new access-control code,
    just a clear pricing summary for anyone landing on this URL directly
    from the marketplace listing. Numbers must stay in sync with
    services/intelligence_quota_service.py's TIER_LIMITS and intelligence-
    api.html's plan cards -- same "recommendation, not hardcoded truth
    elsewhere" caveat as that module's own docstring.

    2026-09-15 (follow-up, same day): a valid mcp-marketplace.io license
    key (see _has_valid_marketplace_license() above) is now real -- it
    upgrades a free XFINLAB key's quota to Pro for every tool call it's
    presented on. This was NOT true when the listing was first submitted
    (it was deliberately left on the "Free" pricing tier for exactly this
    reason -- see git history). Once a "Monthly" price is set on the
    listing to match, this text should be updated to say so explicitly."""
    return {
        "name": _SERVER_INFO["name"],
        "description": "XFINLAB Intelligence API exposed as an MCP server. POST JSON-RPC 2.0 requests here.",
        "protocolVersion": _PROTOCOL_VERSION,
        "tools": [t["name"] for t in _TOOLS],
        "auth": "X-API-Key header or 'api_key' tool argument -- get a free key at https://www.xfinlab.com/intelligence-api.html",
        "pricing": "Free tier: 300 calls/day, no credit card. Pro tier: 5,000 calls/day, $49/month. Same key and quota as the REST Intelligence API -- one key works everywhere. An mcp-marketplace.io license key (X-Marketplace-License-Key header or 'marketplace_license_key' tool argument) upgrades a free key to Pro-tier quota for the call it's presented on.",
        "docs": "https://www.xfinlab.com/intelligence-api.html",
    }
