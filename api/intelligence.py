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
SQLAlchemy layer). Paid tiers (Pro/Enterprise) have no self-serve
signup/Stripe billing yet -- those keys are issued manually by the admin
via /intelligence/admin/issue-key (gated by api.admin.verify_admin, same
convention as every other admin endpoint). This is a deliberate, honest
stopgap: don't build a billing system before there's a single paying
customer to bill.

2026-07-31: Free tier is the exception -- POST /intelligence/v1/signup
below issues and emails a key automatically, no admin step, tracked in a
separate self_serve_api_keys table (see api_key_service.py).

Versioned under /api/v1/intelligence/* -- the rest of this app's ~50
routers are unversioned flat /api/*; this is a clean-slate decision for
this one new product line, not a retrofit of the existing 50 endpoints
(that would be a large, separate, unnecessary migration).
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.openapi.utils import get_openapi

from services import api_key_service, intelligence_quota_service
from services import rss_news_service
from services.request_ip import get_client_ip
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


def _maybe_send_upgrade_nudge(api_key: str, tier: str, limit: int) -> None:
    """2026-08-18: fires the "you hit your free-tier limit" email exactly
    once per key per day, at the moment a 429 is about to be raised. Only
    for `free` -- Pro is already paying and Enterprise is unlimited, so
    neither tier has anything to upgrade to via this nudge. Entirely
    best-effort: wrapped so a DB hiccup, a missing email, or an SMTP
    failure can never turn a normal 429 into a 500. This is the answer to
    AJ's "比人拉我API, 我得到咩" -- the free tier itself doesn't make
    money, but the exact moment someone maxes it out is the highest-intent
    moment to ask if they want more, so that moment shouldn't be a silent
    JSON error."""
    if tier != "free":
        return
    try:
        if not intelligence_quota_service.should_send_upgrade_nudge(api_key):
            return
        email = api_key_service.get_email_for_key(api_key)
        if not email:
            return
        from services.email_service import EmailService
        sent = EmailService.send_intelligence_api_quota_exceeded(email, tier, limit)
        if sent:
            intelligence_quota_service.record_upgrade_nudge_sent(api_key)
    except Exception:
        pass


_MAX_BATCH_TICKERS = 10


def _split_tickers(raw: Optional[str]) -> list:
    """2026-08-17 (roadmap item #3, "重有咩可以做" round 2 -- batch/multi-
    ticker support): shared by Events and Sentiment. Splits a comma-
    separated ticker list, uppercases, dedupes while preserving order, and
    caps at _MAX_BATCH_TICKERS so a single request can't fan out into an
    unbounded number of downstream fetches. Returns [] for None/empty
    input (the existing "no ticker" case on Events stays untouched)."""
    if not raw:
        return []
    seen = set()
    out = []
    for part in raw.split(","):
        t = part.strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:_MAX_BATCH_TICKERS]


def _maybe_send_endpoint_upgrade_nudge(api_key: str, endpoint: str, cap: int) -> None:
    """2026-08-25: mirrors _maybe_send_upgrade_nudge above, but for the new
    free-tier-only per-endpoint sub-cap (debate/intel -- see
    FREE_TIER_ENDPOINT_DAILY_CAP). Same best-effort posture: a DB hiccup,
    missing email, or SMTP failure can never turn a normal 429 into a 500."""
    try:
        if not intelligence_quota_service.should_send_endpoint_nudge(api_key, endpoint):
            return
        email = api_key_service.get_email_for_key(api_key)
        if not email:
            return
        from services.email_service import EmailService
        sent = EmailService.send_intelligence_api_endpoint_cap_reached(email, endpoint, cap)
        if sent:
            intelligence_quota_service.record_endpoint_nudge_sent(api_key, endpoint)
    except Exception:
        pass


def _check_and_spend_quota(
    api_key: str,
    tier: str,
    endpoint: str,
    response: Response,
    multiplier: int = 1,
    ticker: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> dict:
    """2026-08-17 (roadmap item #1, "重有咩可以做" round 2): also stamps
    X-RateLimit-Limit / X-RateLimit-Remaining on `response` so a client can
    pace its own requests instead of discovering the ceiling by hitting a
    429. `response` is the FastAPI-injected Response each caller receives
    via its own `response: Response` parameter -- mutating its `.headers`
    here is honored on the final response even though the route still
    returns a plain dict body (see FastAPI's Response-as-dependency
    pattern). Unlimited tiers (enterprise, limit==-1) report "unlimited"
    rather than a fabricated number.

    2026-08-17 (roadmap item #3 follow-up): `multiplier` scales the base
    endpoint weight for batch/multi-ticker requests (Events/Sentiment) --
    a 3-ticker Sentiment call does roughly 3x the downstream work of a
    single-ticker one, so it should cost roughly 3x the quota, not the
    same flat weight regardless of how many tickers were requested.

    2026-08-25 (AJ: "跟IP定有其他策略?"): `client_ip` layers a second,
    IP-keyed sub-cap on top of the per-key one below, only for free tier +
    the capped endpoints -- closes the "just re-register for a fresh key"
    loophole (see check_endpoint_cap_by_ip's docstring in
    intelligence_quota_service.py). Only debate/intel's call sites pass
    this; every other endpoint passes None and this whole block is a
    no-op for them."""
    # 2026-08-25: free-tier per-endpoint sub-cap (debate/intel), checked
    # BEFORE the overall weighted-pool check below -- see
    # FREE_TIER_ENDPOINT_DAILY_CAP's docstring in intelligence_quota_
    # service.py for why this exists (raising the pool to 300 shouldn't
    # translate into unlimited exposure on the two LLM/shared-rate-limit
    # endpoints) and how it doubles as the free->paid conversion trigger.
    cap_status = intelligence_quota_service.check_endpoint_cap(api_key, tier, endpoint)
    ip_cap_status = (
        intelligence_quota_service.check_endpoint_cap_by_ip(client_ip, endpoint)
        if tier == "free" and client_ip
        else {"capped": False, "allowed": True}
    )
    blocked = None
    if cap_status["capped"] and not cap_status["allowed"]:
        blocked = cap_status
    elif ip_cap_status["capped"] and not ip_cap_status["allowed"]:
        blocked = ip_cap_status
    if blocked:
        _maybe_send_endpoint_upgrade_nudge(api_key, endpoint, blocked["limit"])
        raise HTTPException(
            status_code=429,
            detail=(
                f"Free-tier daily cap reached for '{endpoint}' "
                f"({blocked['used']}/{blocked['limit']} calls used today) -- "
                f"resets at midnight UTC, or upgrade to Pro to remove this cap."
            ),
            headers={
                "X-RateLimit-Endpoint-Limit": str(blocked["limit"]),
                "X-RateLimit-Endpoint-Remaining": "0",
            },
        )

    weight = intelligence_quota_service.weight_for(endpoint) * max(1, multiplier)
    quota = intelligence_quota_service.check(api_key, tier)
    if not quota["allowed"]:
        _maybe_send_upgrade_nudge(api_key, tier, quota["limit"])
        raise HTTPException(
            status_code=429,
            detail=f"Daily quota exceeded ({quota['used']}/{quota['limit']} calls used today for tier '{tier}')",
            headers={
                "X-RateLimit-Limit": str(quota["limit"]),
                "X-RateLimit-Remaining": "0",
            },
        )
    intelligence_quota_service.increment(api_key, weight=weight)
    if cap_status["capped"]:
        intelligence_quota_service.increment_endpoint(api_key, endpoint)
    if ip_cap_status["capped"]:
        intelligence_quota_service.increment_endpoint_by_ip(client_ip, endpoint)
    # 2026-08-25 (AJ: "咁FREE KEY比人用，我接到數據訓ENGINE或儲存之類嗎"):
    # aggregate-only product signal, never the response payload -- see
    # log_query()'s docstring. Best-effort, always logged regardless of
    # tier so trending-ticker signal reflects real usage across the board.
    intelligence_quota_service.log_query(api_key, endpoint, ticker)
    if quota["limit"] == -1:
        response.headers["X-RateLimit-Limit"] = "unlimited"
        response.headers["X-RateLimit-Remaining"] = "unlimited"
    else:
        response.headers["X-RateLimit-Limit"] = str(quota["limit"])
        response.headers["X-RateLimit-Remaining"] = str(max(0, quota["remaining"] - weight))
    return quota


@router.get("/intelligence/status")
def intelligence_status():
    """Public, unauthenticated -- lets a prospective developer check what's
    live before they even have a key, same pattern as
    GET /api/agent-debate/status.

    2026-08-17 (task #4 follow-up, "重有咩可以升級" -- upgrade #4, live status
    widget): extended from the original 3 keys (events/sentiment/debate) to
    cover all 7 public endpoints. Only sentiment and debate have a genuine
    binary gate here -- their route handlers explicitly raise 503 if
    finbert_available()/debate_available() is false (see intelligence_
    sentiment/intelligence_debate above). The other 5 (events, intel,
    technical, stress_test, regime_signal) never 503 by design -- on an
    upstream hiccup they soft-fail to 200 with an `error` field or null
    sub-fields instead (see the schema docs on intelligence-api.html). So
    `True` here means "not gated behind an external reachability check",
    not a claimed uptime guarantee -- deliberately not fabricating a
    monitoring signal that doesn't exist for endpoints that don't have one.
    """
    return _envelope(data={
        "events": True,  # rss_news_service has no external gate
        "sentiment": finbert_available(),
        "debate": debate_available(),
        "intel": True,  # never 503s -- returns partial/null fields on AI failure instead
        "technical": True,  # no external AI gate
        "stress_test": True,  # pure computation once price history resolves
        "regime_signal": True,  # reads a local persisted leaderboard, no external gate
        "forecast": True,  # pure computation once price history resolves, ml_cross_check/capital_flow_context degrade individually rather than gating the whole endpoint
        "insider": True,  # never 503s -- returns data: null for a ticker with no CIK match or an upstream miss
        "company_network": True,  # never 503s -- pure re-packaging of insider/13F/13D/COT, each sub-section honestly flags its own availability
        "short_interest": True,  # never 503s -- returns data: null for no reportable short position or an upstream miss
        "energy": True,  # never 503s -- returns data: null for a ticker with no crude/nat-gas linkage
        "exchange": True,  # never 503s -- returns data: null for a non-crypto ticker
        "fundamentals": True,  # never 503s -- returns data: null for no CIK match or zero usable 10-K concepts
        "vix_term_structure": True,  # never 503s -- returns data: null only if every CBOE index fetch/cache/persist fails
        "bank_health": True,  # never 503s -- returns data: null for a ticker with no FDIC-mapped lead subsidiary
        "agriculture": True,  # never 503s -- returns data: null for a ticker with no USDA commodity linkage
        "real_estate": True,  # never 503s -- returns data: null for a ticker with no housing-market linkage
        "supply_chain": True,  # never 503s -- returns data: null for a ticker with no freight/logistics linkage
        "consumer_demand": True,  # never 503s -- returns data: null for a ticker with no consumer-spending linkage
        "opportunity_radar": True,  # market-wide, dormant until FRED_API_KEY set (same gate as real_estate/supply_chain/consumer_demand)
        "webhooks": True,  # management endpoints, never 503 -- Pro-tier gated (403 for free keys), see services/webhook_service.py
    })


# ---------------------------------------------------------------------------
# 2026-08-17 (task #4 follow-up, "重有咩可以升級" -- upgrade #4, changelog):
# hand-maintained, Keep-a-Changelog-style entries -- deliberately NOT
# auto-generated from git log (would be noisy/unfiltered and could leak
# internal-only commit messages). Every entry below is dated against a real
# docstring/comment already in this file or intelligence-api.html (see the
# "2026-0X-XX" markers throughout both), not invented after the fact.
# Exposed both as JSON (for integrators who want to watch for breaking
# changes programmatically) and rendered on intelligence-api.html#changelog.
# ---------------------------------------------------------------------------
INTELLIGENCE_CHANGELOG = [
    {
        "date": "2026-08-31",
        "changes": [
            {"type": "changed", "text": "GET /v1/opportunity-radar -- expanded from 3 to 5 industries: added energy (EIA WTI crude/Henry Hub spot prices, natural gas storage) and agriculture (USDA corn/wheat/soybean price received by farmers). Each industry now gates independently on its own data source's key (FRED/EIA/USDA) rather than the whole endpoint going dark if just one is unset."},
            {"type": "added", "text": "Webhooks: opportunity_radar_shift event type -- fires when an Opportunity Radar industry's net improving/worsening lean flips (e.g. real estate goes from net-improving to net-worsening). Market-wide, Pro-tier only, same delivery mechanics as the existing 2 event types."},
        ],
    },
    {
        "date": "2026-08-31",
        "changes": [
            {"type": "added", "text": "GET /v1/opportunity-radar -- structural macro-mismatch read across US real estate, supply chain/manufacturing, and consumer demand, plus a US macro backdrop. Each indicator reports its own real % change over its trailing observations (exact dates included), and each industry reports a plain improving/worsening/flat count -- deliberately not a fabricated single cross-industry 'Opportunity Score'."},
        ],
    },
    {
        "date": "2026-08-31",
        "changes": [
            {"type": "added", "text": "GET /v1/supply-chain/{ticker} -- FRED inventory/sales ratio, manufacturing new orders, durable goods orders, industrial production, and manufacturing employment for freight/logistics-linked tickers (carriers, railroads, transportation ETFs). Second of 3 cross-industry expansion candidates."},
            {"type": "added", "text": "GET /v1/consumer-demand/{ticker} -- FRED retail sales, personal consumption expenditures, and durable goods consumption for consumer-spending-linked tickers (large retailers, e-commerce, consumer-discretionary ETFs). Third of 3 cross-industry expansion candidates -- not Google Trends search-interest data, see that endpoint's docs for why."},
            {"type": "fixed", "text": "News search (/v1/events, /v1/sentiment) now resolves bare ticker queries to their real company name before searching headlines, and widens the GDELT lookback window -- fixes zero-results for well-known large-cap tickers whose headlines almost never contain the bare ticker symbol."},
        ],
    },
    {
        "date": "2026-08-30",
        "changes": [
            {"type": "added", "text": "GET /v1/real-estate/{ticker} -- FRED 30-year mortgage rate, Case-Shiller home price index, housing starts, and existing home sales for housing-linked tickers (homebuilders, REITs, a mortgage originator, housing-sector ETFs). First of 3 cross-industry expansion candidates."},
        ],
    },
    {
        "date": "2026-08-30",
        "changes": [
            {"type": "changed", "text": "GET /v1/company-network/{ticker} -- added smart_money_crossholdings (Phase 4: for each tracked concentrated manager -- Berkshire Hathaway, Pershing Square, Scion Asset Management -- that holds this ticker, what else that same manager holds by real reported 13F value. Zero new data source, pure re-query of already-collected filing rows; real issuer names, no guessed tickers, no ranking or score)."},
        ],
    },
    {
        "date": "2026-08-30",
        "changes": [
            {"type": "changed", "text": "GET /v1/company-network/{ticker} -- added business_relationship_mentions (Phase 2: literal, sourced sentence excerpts from the issuer's own latest 10-K naming a competitor/supplier/customer -- quotable and independently verifiable, never a cleaned-up inferred list) and event_impact (Phase 3: what the real stock price actually did after each of the ticker's most recent tracked Form 4 / 13D-13G events, computed live from real historical closes -- a factual record of one past outcome, not a prediction, average, or causal claim). Both are new sub-sections on the existing endpoint, not a new route. Quota weight raised 5->7 to reflect the extra document fetch."},
        ],
    },
    {
        "date": "2026-08-29",
        "changes": [
            {"type": "added", "text": "GET /v1/company-network/{ticker} -- combines 13F institutional ownership, 13D/13G activist filings, Form 4 insider trading, and CFTC COT (if linked) into one relationship view, plus a day-over-day what_changed diff. Zero new data sources."},
        ],
    },
    {
        "date": "2026-08-28",
        "changes": [
            {"type": "added", "text": "POST /v1/webhooks/subscribe, GET /v1/webhooks, DELETE /v1/webhooks/{id} -- Pro-tier push notifications for vix_regime_change and new_13d_filing events, instead of polling."},
            {"type": "added", "text": "GET /v1/fundamentals/{ticker} -- latest annual (10-K) revenue, net income, diluted EPS, total assets/liabilities, operating cash flow from SEC XBRL. First real fundamentals endpoint in the Intelligence API."},
            {"type": "added", "text": "GET /v1/vix-term-structure -- CBOE VIX9D/VIX/VIX3M/VIX6M term structure and contango/backwardation regime read."},
            {"type": "added", "text": "GET /v1/bank-health/{ticker} -- FDIC Call Report health (ROA/ROE/assets/equity) for major bank holding companies' lead subsidiaries."},
            {"type": "added", "text": "GET /v1/agriculture/{ticker} -- USDA corn/wheat/soybean price-received context for CORN/WEAT/SOYB."},
        ],
    },
    {
        "date": "2026-08-27",
        "changes": [
            {"type": "added", "text": "GET /v1/insider/{ticker} -- SEC Form 4 insider-trading transactions, cross-indexed by issuer CIK via EDGAR."},
            {"type": "added", "text": "GET /v1/short-interest/{ticker} -- FINRA bi-weekly equity short interest (current/previous shares, days-to-cover, change %)."},
            {"type": "added", "text": "GET /v1/energy/{ticker} -- EIA WTI crude / Henry Hub nat-gas / storage context for energy-linked tickers (USO, UNG)."},
            {"type": "added", "text": "GET /v1/exchange/{ticker} -- same crypto ticker's live stats from Binance and Coinbase side by side."},
        ],
    },
    {
        "date": "2026-08-24",
        "changes": [
            {"type": "added", "text": "GET /v1/forecast/{ticker} -- Bear/Base/Bull price-path fan chart (10th/50th/90th percentile of a real historical-return bootstrap) plus an independently-validated ML up-probability cross-check and a capital-flow/liquidity regime reading. Never fabricates a fixed bull/base/bear probability split."},
            {"type": "added", "text": "Self-serve Pro checkout is now live (real Stripe subscription) -- Pro no longer requires the manual early-access follow-up."},
        ],
    },
    {
        "date": "2026-08-18",
        "changes": [
            {"type": "added", "text": "Free-tier keys now get a one-time-per-day email when they hit their daily quota (429), pointing at Pro instead of just returning a bare error."},
            {"type": "added", "text": "Listed on APIs.guru and the Postman API Network (public workspace, published docs) -- the API is now discoverable outside xfinlab.com, not just prepared for submission."},
        ],
    },
    {
        "date": "2026-08-17",
        "changes": [
            {"type": "added", "text": "GET /v1/events and GET /v1/sentiment now accept a comma-separated list of up to 10 tickers (e.g. \"AAPL,MSFT,TSLA\") for watchlist-style queries -- single-ticker requests are unaffected, batch requests cost proportionally more quota."},
            {"type": "added", "text": "Third-party API directory submission copy prepared for APIs.guru and the Postman API Network (see API_DIRECTORY_SUBMISSION.md in the repo) -- pending AJ's own account action to actually submit."},
            {"type": "added", "text": "Postman collection at GET /api/intelligence/postman.json -- import via Postman's Import > Link, every request pre-filled with a working example."},
            {"type": "added", "text": "Public roadmap at GET /api/intelligence/roadmap (this page, #roadmap) -- backs the Pro plan's previously-unbacked \"public roadmap\" promise."},
            {"type": "added", "text": "X-RateLimit-Limit / X-RateLimit-Remaining headers on every authenticated response, so clients can pace requests instead of discovering the ceiling from a 429."},
            {"type": "added", "text": "Changelog and live status widget (this page, #changelog)."},
            {"type": "added", "text": "Per-endpoint response field documentation on each endpoint card."},
            {"type": "added", "text": "Scoped OpenAPI 3.1 spec export at GET /api/intelligence/openapi.json."},
            {"type": "added", "text": "Live \"Try it\" console -- run real requests against the API from this page."},
            {"type": "added", "text": "Full translation of this page into all 47 supported XFINLAB languages."},
            {"type": "changed", "text": "Data Sourcing split into a standalone \"US price data\" card and a merged \"Taiwan & other markets\" card."},
            {"type": "fixed", "text": "Endpoint-count heading corrected from \"Six endpoints\" to \"Seven endpoints\" (Regime-Aware Signal, shipped 2026-08-10, wasn't reflected in the page copy)."},
        ],
    },
    {
        "date": "2026-08-14",
        "changes": [
            {"type": "added", "text": "MCP Server documented and published -- 7 tools mirroring the REST endpoints, for Claude and other MCP-compatible AI agents."},
        ],
    },
    {
        "date": "2026-08-11",
        "changes": [
            {"type": "changed", "text": "News source switched from an RSS feed with non-commercial-use terms to GDELT (public domain) plus official press-release wires (GlobeNewswire, PR Newswire) -- full commercial-redistribution licensing."},
            {"type": "fixed", "text": "GET /v1/technical/{ticker} no longer includes the raw OHLC price-bar array in its response -- every price-derived field is a computed result now, not the underlying feed."},
        ],
    },
    {
        "date": "2026-08-10",
        "changes": [
            {"type": "added", "text": "GET /v1/regime-signal/{ticker} -- current causal market regime plus the best-performing signal combo for that regime, backed by walk-forward-validated backtests."},
        ],
    },
    {
        "date": "2026-07-31",
        "changes": [
            {"type": "added", "text": "GET /v1/intel/latest and GET /v1/intel/{ticker} -- the AI Intelligence Feed, clustered/enriched event intelligence with an AI-written narrative."},
            {"type": "added", "text": "GET /v1/technical/{ticker} -- confluence, trend, MACD, chart patterns, and market structure."},
            {"type": "added", "text": "POST /v1/stress-test -- historical-bootstrap Monte Carlo simulation."},
            {"type": "added", "text": "Automated Free-tier self-serve signup (POST /v1/signup) -- keys issued and emailed instantly, no admin step."},
        ],
    },
    {
        "date": "2026-07-30",
        "changes": [
            {"type": "added", "text": "Intelligence API v1 launch -- GET /v1/events, GET /v1/sentiment, GET /v1/debate."},
        ],
    },
]


@router.get("/intelligence/changelog")
def intelligence_changelog():
    """Public, unauthenticated. See INTELLIGENCE_CHANGELOG's docstring
    comment above for why this is hand-maintained rather than generated."""
    return _envelope(data=INTELLIGENCE_CHANGELOG)


# ---------------------------------------------------------------------------
# 2026-08-17 (follow-up to task #4's changelog, "重有咩可以做" round 2 --
# roadmap): the Pro plan card on intelligence-api.html has promised "Early
# say in the public roadmap" since it was written, but no public roadmap
# ever existed -- an unbacked promise, same category of issue as the
# "Six endpoints" heading that was stale until this session found it.
# This is that roadmap, for real. Every item below is something actually
# discussed/identified as a next step in this project (not invented to
# sound impressive) -- rate-limit headers, a Postman collection, batch
# ticker support, third-party directory listings, and SDK publishing are
# all real candidates raised in the same conversation that produced the
# changelog above. `status` is "planned" (not started) or "in_progress";
# shipped items move to INTELLIGENCE_CHANGELOG instead of staying here,
# so this list only ever shows what's still ahead.
# ---------------------------------------------------------------------------
INTELLIGENCE_ROADMAP = [
    {
        "status": "planned",
        "title": "Published SDKs on PyPI / npm",
        "text": "The Python/Node SDKs already exist (see sdk/ in the repo) and install fine straight from GitHub -- publishing them as real packages is gated on enough paying developers using this API to justify the ongoing maintenance overhead, not on the code itself.",
    },
]


@router.get("/intelligence/roadmap")
def intelligence_roadmap():
    """Public, unauthenticated. See INTELLIGENCE_ROADMAP's docstring
    comment above -- this is what backs the Pro plan's "public roadmap"
    promise on intelligence-api.html."""
    return _envelope(data=INTELLIGENCE_ROADMAP)


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


# ---------------------------------------------------------------------------
# 2026-07-31: Self-serve Free-tier signup (Task #575). Automated, no admin
# step -- closes the "no self-serve billing" gap for the Free tier only.
# Pro/Enterprise deliberately still route through /intelligence/early-access
# above until a real payment processor (Stripe recommended over Paddle for
# usage-metered API billing -- see chat) is actually connected, which needs
# the business owner's own merchant account and is out of scope here.
# ---------------------------------------------------------------------------


class FreeSignupRequest(BaseModel):
    email: str  # same plain-str rationale as EarlyAccessRequest.email above

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, v: str) -> str:
        v = (v or "").strip()
        if "@" not in v or "." not in v.split("@")[-1] or len(v) < 5:
            raise ValueError("Please provide a valid email address")
        return v


@router.post("/intelligence/v1/signup")
def intelligence_self_serve_signup(body: FreeSignupRequest, request: Request):
    """Public, unauthenticated. Issues a Free-tier key immediately and
    emails it -- never returned in the JSON response body, so it can't sit
    in browser devtools/network logs. Guarded by a disposable-email check
    (reusing services/disposable_email_domains.py, the same blocklist
    already used for site registration) and a per-IP daily rate limit
    (services/api_key_service.check_self_serve_signup_rate) so this can't
    be scripted into unlimited free-key generation."""
    from services.disposable_email_domains import is_disposable_email

    if is_disposable_email(body.email):
        raise HTTPException(status_code=400, detail="Please use a non-disposable email address")

    # 2026-08-25 fix (found while answering AJ's "跟IP定有其他策略?"): this
    # used to read request.client.host directly, which on Railway is the
    # platform's own internal proxy address -- THE SAME for every visitor
    # (see services/request_ip.py's module docstring for the full
    # explanation) -- so the "5 signups/IP/day" limit below was actually
    # one shared global counter across every real signer-upper, not a
    # per-visitor limit. get_client_ip() reads X-Forwarded-For (which
    # Railway's edge sets correctly) instead.
    ip = get_client_ip(request)
    if not api_key_service.check_self_serve_signup_rate(ip):
        raise HTTPException(
            status_code=429,
            detail="Too many signup attempts from this network today -- please try again tomorrow",
        )
    api_key_service.record_self_serve_signup_attempt(ip)

    result = api_key_service.issue_self_serve_free_key(body.email)

    # 2026-08-25: template factored out to api_key_service.send_api_key_email
    # so backend/auth/auth.py's new "every free signup gets a key" hook can
    # send the identical email instead of a second, driftable copy -- also
    # fixes this template's stale "200 weighted calls/day" (the real
    # TIER_LIMITS["free"] is 100; see that function's docstring).
    sent = api_key_service.send_api_key_email(result["email"], result["key"])

    if not sent:
        # The key already exists in self_serve_api_keys at this point, but
        # if we can't deliver it there's no way for the customer to receive
        # it (same "show it once" posture as issue_key()) -- report the
        # failure honestly rather than claiming success.
        raise HTTPException(
            status_code=502,
            detail="Key was issued but the confirmation email failed to send -- please try again or contact support@xfinlab.com",
        )

    return _envelope(data={"email": result["email"], "tier": "free", "sent": True})


@router.get("/intelligence/v1/events")
def intelligence_events(
    request: Request,
    response: Response,
    ticker: Optional[str] = None,
    limit: int = 20,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """`ticker` accepts a single symbol, no ticker (all headlines), or a
    comma-separated list up to _MAX_BATCH_TICKERS (e.g. "AAPL,MSFT,TSLA")
    for watchlist-style queries -- roadmap item #3, 2026-08-17. No-ticker
    and single-ticker requests return the exact same shape as before this
    change; a multi-ticker request merges/dedupes results across all
    requested symbols and adds a `tickers` field to each event."""
    auth = _require_api_key(x_api_key)
    tickers = _split_tickers(ticker)
    _check_and_spend_quota(x_api_key, auth["tier"], "events", response, multiplier=max(1, len(tickers)), ticker=(",".join(tickers) if tickers else None))

    limit = max(1, min(limit, 100))

    if len(tickers) <= 1:
        single = tickers[0] if tickers else None
        if single:
            result = rss_news_service.search_headlines(query=single, limit=limit)
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

    # Batch mode (2+ tickers): merge/dedupe by link across all requested
    # symbols, tagging each event with which of the requested tickers it
    # matched (a single headline can legitimately match more than one).
    by_link: dict = {}
    any_ok = False
    for t in tickers:
        result = rss_news_service.search_headlines(query=t, limit=limit)
        if result["status"] != "ok":
            continue
        any_ok = True
        for item in result["items"]:
            link = item["link"]
            entry = by_link.get(link)
            if entry is None:
                entry = {
                    "title": item["title"],
                    "source": item["source"],
                    "kind": item["kind"],
                    "published_at": item["published_at"],
                    "url": link,
                    "tickers": [],
                }
                by_link[link] = entry
            if t not in entry["tickers"]:
                entry["tickers"].append(t)

    if not any_ok:
        return _envelope(data=[], error="No matching events found for the requested tickers")

    events = sorted(by_link.values(), key=lambda e: e["published_at"] or "", reverse=True)[:limit]
    return _envelope(data=events, meta={"count": len(events), "tickers": tickers})


@router.get("/intelligence/v1/sentiment")
def intelligence_sentiment(
    response: Response,
    ticker: str,
    limit: int = 10,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """`ticker` accepts a single symbol or a comma-separated list up to
    _MAX_BATCH_TICKERS (e.g. "AAPL,MSFT,TSLA") -- roadmap item #3,
    2026-08-17. A single ticker returns the exact same shape as before
    this change. A comma-separated list returns `results_by_ticker` keyed
    by symbol instead of one flat `results` array -- averaging sentiment
    scores across unrelated tickers into a single number would be a
    misleading aggregate, not a real one."""
    auth = _require_api_key(x_api_key)
    tickers = _split_tickers(ticker)
    if not tickers:
        raise HTTPException(status_code=422, detail="ticker is required")
    _check_and_spend_quota(x_api_key, auth["tier"], "sentiment", response, multiplier=len(tickers), ticker=",".join(tickers))

    if not finbert_available():
        raise HTTPException(status_code=503, detail="Sentiment engine temporarily unavailable")

    limit = max(1, min(limit, 25))

    if len(tickers) == 1:
        ticker = tickers[0]
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

    # Batch mode (2+ tickers): one sub-object per ticker, never one
    # flattened/averaged result set.
    results_by_ticker: dict = {}
    for t in tickers:
        headlines = rss_news_service.search_headlines(query=t, limit=limit)
        if headlines["status"] != "ok" or not headlines["items"]:
            results_by_ticker[t] = {
                "average_score": None,
                "articles_analyzed": 0,
                "results": [],
                "message": "No recent headlines found for this ticker",
            }
            continue

        titles = [item["title"] for item in headlines["items"]]
        sentiment = analyze_batch(titles)
        if not sentiment.get("available"):
            results_by_ticker[t] = {
                "average_score": None,
                "articles_analyzed": 0,
                "results": [],
                "error": sentiment.get("message", "Sentiment engine unavailable"),
            }
            continue

        scores = [r["score"] for r in sentiment["results"]]
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        results_by_ticker[t] = {
            "average_score": avg_score,
            "articles_analyzed": len(sentiment["results"]),
            "results": [
                {
                    "headline": title,
                    "label": r["label"],
                    "confidence_pct": r["confidence_pct"],
                    "score": r["score"],
                }
                for title, r in zip(titles, sentiment["results"])
            ],
        }

    return _envelope(
        data={"tickers": tickers, "results_by_ticker": results_by_ticker},
        meta={"source": "finbert"},
    )


@router.get("/intelligence/v1/debate")
def intelligence_debate(
    request: Request,
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Wraps the existing 4-call Bull/Bear/Risk-Manager debate. This is the
    single most expensive endpoint in this router (see
    services/agent_debate_service.py) -- weighted 5x in the quota counter,
    same reasoning api/agent_debate.py already applies to logged-in users."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(
        x_api_key, auth["tier"], "debate", response, ticker=ticker.upper(), client_ip=get_client_ip(request)
    )

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
    request: Request,
    response: Response,
    limit: int = 5,
    lang: str = "zh-HK",
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "intel", response, client_ip=get_client_ip(request))

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
    request: Request,
    response: Response,
    ticker: str,
    limit: int = 5,
    lang: str = "zh-HK",
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(
        x_api_key, auth["tier"], "intel", response, ticker=ticker.upper(), client_ip=get_client_ip(request)
    )

    limit = max(1, min(limit, 10))
    ticker = ticker.upper()

    result = rss_news_service.search_headlines(query=ticker, limit=60)
    if result["status"] != "ok" or not result["items"]:
        return _envelope(data=[], error=result.get("message") or f"No recent events found for {ticker}")

    feed = build_intelligence_feed(result["items"], max_clusters=limit, lang=lang)
    return _envelope(data=feed, meta={"ticker": ticker, "count": len(feed)})


# ---------------------------------------------------------------------------
# 2026-07-31 (monetization batch, task #598): "Decision/Market-Structure API"
# and "Stress-Test API" -- pure packaging of two engines this codebase
# already built and already serves on ai-analysis.html/chart-analysis.html
# (services/technical_analysis_service.py's confluence+MACD+market-structure
# +chart-pattern pipeline) and stress-lab.html (services/monte_carlo_service
# .py's real historical-bootstrap simulation). No new computation, no new
# AI calls -- same honesty posture as every other endpoint in this router:
# real numbers from real data, never a fabricated estimate.
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/technical/{ticker}")
def intelligence_technical(
    response: Response,
    ticker: str,
    period: str = "6mo",
    interval: str = "1d",
    lang: str = "en",
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Confluence direction/confidence, trend, MACD, volume, chart patterns,
    and market-structure (BOS/CHOCH/liquidity-sweep/order-flow/volume-
    profile/institutional-footprint) for one ticker -- everything
    ai-analysis.html's dashboard shows, minus AI prose. `lang` reuses the
    same site-wide per-language translation this endpoint's underlying
    function already does for the website (task #592's fix), so API
    consumers get real localized labels too, not just en/zh."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "technical", response, ticker=ticker.upper())

    from services.technical_analysis_service import get_technical_analysis

    ticker = ticker.upper().strip()
    tech = get_technical_analysis(ticker, period=period, interval=interval, lang=lang)
    if not tech or "error" in tech:
        return _envelope(data=None, error=(tech or {}).get("error", f"No technical data available for {ticker}"))

    # 2026-08-11 (AJ, "做法1"): strip the raw OHLC bar array before this
    # dict leaves the process. get_technical_analysis()'s "ohlc" field
    # (up to 300 real Open/High/Low/Close/Volume bars, see
    # technical_analysis_service.py::_ohlc_series()) is legitimate for
    # this codebase's own UI (chart-analysis.html/ai-analysis.html render
    # a candlestick chart with it), but this router sells access to
    # third-party developers -- for any symbol served via the yfinance
    # fallback (i.e. not US-Alpaca or Taiwan-TWSE), re-exporting those raw
    # bars through a commercial endpoint would be redistributing
    # yahoo_finance data, already confirmed non_commercial/high risk in
    # services/license_registry.py. This module's own docstring already
    # promises "never raw ... data" -- this endpoint was the one place
    # that promise wasn't kept. Every other field (confluence/trend/RSI/
    # MACD/support-resistance/patterns/market-structure/decision_levels)
    # is untouched; only the raw price array is removed. See
    # DATA-LICENSE-MATRIX.md's action-item list for the full writeup.
    tech = {k: v for k, v in tech.items() if k != "ohlc"}

    return _envelope(data=tech, meta={"ticker": ticker, "period": period, "interval": interval})


class WebhookSubscribeRequest(BaseModel):
    event_type: str
    url: str
    ticker: Optional[str] = None


class StressTestRequest(BaseModel):
    symbol: str
    amount: float
    horizon_days: int = 252
    n_simulations: Optional[int] = None
    lang: Optional[str] = None


@router.post("/intelligence/v1/stress-test")
def intelligence_stress_test(
    body: StressTestRequest,
    response: Response,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Real historical-bootstrap Monte Carlo (see services/monte_carlo_
    service.py's module docstring for the honesty notes on method/
    limitations -- returned verbatim in the `method`/`note` fields, never
    stripped out for API consumers). Same MAX_HORIZON_DAYS/MAX_N_SIMULATIONS
    caps stress-lab.html's own callers get; POST (not GET) since this is
    the heaviest-compute endpoint in this router after `debate`/`intel`."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "stress_test", response, ticker=body.symbol.upper())

    from services.monte_carlo_service import simulate, DEFAULT_N_SIMULATIONS

    result = simulate(
        body.symbol,
        amount=body.amount,
        horizon_days=body.horizon_days,
        n_simulations=body.n_simulations or DEFAULT_N_SIMULATIONS,
        lang=body.lang,
    )
    if not result.get("available"):
        return _envelope(data=None, error=result.get("message", "Simulation unavailable"))

    return _envelope(data=result, meta={"symbol": body.symbol.upper()})


# ---------------------------------------------------------------------------
# 2026-08-24 (Capital Flow Engine roadmap, Layer 7 -- "Probabilistic
# K-Line Path Generator", flagship for the Intelligence API v2 direction
# discussed with AJ): packages services/probabilistic_forecast_service.py.
# GET with a path param (not POST like stress-test) since this needs no
# `amount` -- everything is expressed in the ticker's own price terms.
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/forecast/{ticker}")
def intelligence_forecast(
    ticker: str,
    response: Response,
    horizon_days: int = 5,
    n_simulations: int = None,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Bear/Base/Bull fan-chart price path (10th/50th/90th percentile of a
    real historical-return bootstrap, see services/probabilistic_forecast_
    service.py's module docstring for the full honesty contract), plus an
    independently-validated ML up-probability cross-check when one exists,
    plus a capital-flow/liquidity regime reading. Never fabricates a fixed
    bull/base/bear PROBABILITY split -- the returned band_note explains
    what the percentiles actually mean."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "forecast", response, ticker=ticker.upper())

    from services.probabilistic_forecast_service import get_probabilistic_forecast, MAX_HORIZON_DAYS

    ticker = ticker.upper().strip()
    horizon_days = max(1, min(int(horizon_days or 5), MAX_HORIZON_DAYS))
    result = get_probabilistic_forecast(ticker, horizon_days=horizon_days, n_simulations=n_simulations)
    if not result.get("available"):
        return _envelope(data=None, error=result.get("message", f"No forecast available for {ticker}"))

    return _envelope(data=result, meta={"ticker": ticker, "horizon_days": horizon_days})


# ---------------------------------------------------------------------------
# 2026-08-10 (P3 of the Quant Research Factory roadmap -- "Regime-Aware
# Signal" productization): packages services/regime_router_service.py for
# external API consumers. Pure packaging of an already-built engine, same
# honesty posture as the rest of this router -- `available: false` with a
# `reason` string (not a fabricated pick) when the persisted leaderboard
# doesn't yet have enough graded trades for this ticker/regime pair, exactly
# like the ai-analysis.html/chart-analysis.html frontend wiring for the same
# service. This is a READ of a persisted leaderboard, never a synchronous
# 35-candidate walk-forward scan -- see regime_router_service.get_best_for_
# regime()'s own docstring for why.
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/regime-signal/{ticker}")
def intelligence_regime_signal(
    response: Response,
    ticker: str,
    regime: Optional[str] = None,
    min_trades: int = 5,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Current causal market regime for `ticker` (services/regime_router_
    service.py's own causal-only classifier, see that module's docstring
    for why it doesn't reuse the live Confluence/Regime Belief engines)
    plus whichever composed signal combo (services/formula_composer_
    service.py) has historically performed best in that regime. If
    `regime` is omitted, the current regime is computed first and used
    for the lookup -- the actual "what should I use right now" answer."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "regime", response, ticker=ticker.upper())

    from services.regime_router_service import get_best_for_regime, get_current_regime

    ticker = ticker.upper().strip()
    min_trades = max(1, min(min_trades, 50))

    current = get_current_regime(ticker)
    if "error" in current:
        return _envelope(data=None, error=current["error"])

    lookup_regime = regime or current["regime"]
    result = get_best_for_regime(ticker, lookup_regime, min_trades=min_trades)

    return _envelope(
        data={"current_regime": current, "regime_used": lookup_regime, **result},
        meta={"ticker": ticker},
    )


# ---------------------------------------------------------------------------
# 2026-08-27 (Data Factory -> Intelligence API monetization; AJ's selection
# "加入Intelligence API (推薦)" after Data Factory's 11 sources went live
# and fully surfaced on ai-analysis.html with diminishing marginal returns
# on adding an 12th source vs. monetizing the ones already built): four new
# endpoints wrapping the newest Data Factory collectors as sellable API
# product -- pure packaging, no new computation, same honesty posture as
# every other endpoint in this router. All four soft-fail to `data: null`
# with an `error` string on an upstream miss or an out-of-universe ticker
# (e.g. energy context requested for a ticker with no crude/nat-gas
# linkage, or exchange comparison for a non-crypto ticker) -- never a
# fabricated reading.
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/insider/{ticker}")
def intelligence_insider(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """SEC Form 4 insider-trading transactions for `ticker` (services/
    sec_form4_service.py -- non-derivative open-market transactions from
    the most recent filings cross-indexed under the issuer's own CIK via
    EDGAR's browse-edgar feed, not just what the issuer itself filed).
    24h server-side cached, so repeat calls for the same ticker within a
    day don't re-hit EDGAR."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "insider", response, ticker=ticker.upper())

    from services.sec_form4_service import get_recent_insider_transactions

    ticker = ticker.upper().strip()
    result = get_recent_insider_transactions(ticker)
    if not result or not result.get("available"):
        return _envelope(data=None, error=(result or {}).get("message", f"No insider-trading data available for {ticker}"))

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/company-network/{ticker}")
def intelligence_company_network(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Company relationship intelligence for `ticker` (services/
    company_network_service.py -- Phase 1 of the "Company Intelligence"
    direction, 2026-08-29). Combines four already-collected Data Factory
    signals into one view: SEC 13F institutional ownership + conviction
    score, SEC 13D/13G activist filings, SEC Form 4 insider trading, and
    CFTC COT futures positioning if the ticker has a directly linked
    contract. Zero new data sources -- pure re-packaging of endpoints
    already live elsewhere in this API (/v1/insider is a subset of this
    response's insider_trading field).

    Also returns `what_changed`: a day-over-day diff of this ticker's
    network_summary numbers against the prior day's snapshot. Pure
    mechanical diff, no AI -- `available: False` the first time a ticker
    is queried on a given day (no prior snapshot to diff against yet)
    rather than fabricating a baseline."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "company_network", response, ticker=ticker.upper())

    from services.company_network_service import get_company_network

    ticker = ticker.upper().strip()
    result = get_company_network(ticker)
    if not result or not result.get("available"):
        return _envelope(data=None, error=(result or {}).get("message", f"No company-network data available for {ticker}"))

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/short-interest/{ticker}")
def intelligence_short_interest(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """FINRA bi-weekly equity short-interest for `ticker` (services/
    finra_short_interest_service.py -- the genuinely free public
    settlement-date flat file, distinct from FINRA's member-firm-gated
    Query API). `available: false` with no reported short position is a
    real, honest "not currently shorted at reportable levels" result, not
    an error."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "short_interest", response, ticker=ticker.upper())

    from services.finra_short_interest_service import get_short_interest_for_ticker

    ticker = ticker.upper().strip()
    result = get_short_interest_for_ticker(ticker)
    if not result or not result.get("available"):
        return _envelope(data=None, error=(result or {}).get("message", f"No short-interest data available for {ticker}"))

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/energy/{ticker}")
def intelligence_energy(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """EIA energy-fundamentals context for `ticker` (services/eia_energy_
    service.py -- WTI crude spot, Henry Hub nat-gas spot, and Lower-48
    working nat-gas storage). Only populated for tickers with a real
    crude/nat-gas linkage (currently USO/UNG, see that module's
    _TICKER_TO_SERIES) -- any other ticker returns `data: null`, never a
    fabricated reading for an unrelated symbol."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "energy", response, ticker=ticker.upper())

    from services.eia_energy_service import get_energy_context_for_ticker

    ticker = ticker.upper().strip()
    result = get_energy_context_for_ticker(ticker)
    if not result:
        return _envelope(data=None, error=f"No energy-fundamentals linkage for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/real-estate/{ticker}")
def intelligence_real_estate(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """FRED US housing-market context for `ticker` (services/real_estate_
    service.py -- 30-year mortgage rate, Case-Shiller home price index,
    housing starts, existing home sales). Only populated for tickers with
    a real housing-market linkage (homebuilders, REITs, a mortgage
    originator, housing-sector ETFs -- see that module's _TICKER_TO_NAME)
    -- any other ticker returns `data: null`, never a fabricated reading
    for an unrelated symbol."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "real_estate", response, ticker=ticker.upper())

    from services.real_estate_service import get_real_estate_context_for_ticker

    ticker = ticker.upper().strip()
    result = get_real_estate_context_for_ticker(ticker)
    if not result:
        return _envelope(data=None, error=f"No housing-market linkage for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/supply-chain/{ticker}")
def intelligence_supply_chain(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """FRED US manufacturing/supply-chain context for `ticker` (services/
    supply_chain_service.py -- inventory/sales ratio, manufacturing new
    orders, durable goods orders, industrial production, manufacturing
    employment). Only populated for tickers with a real freight/logistics
    linkage (carriers, railroads, transportation ETFs -- see that
    module's _TICKER_TO_NAME) -- any other ticker returns `data: null`,
    never a fabricated reading for an unrelated symbol."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "supply_chain", response, ticker=ticker.upper())

    from services.supply_chain_service import get_supply_chain_context_for_ticker

    ticker = ticker.upper().strip()
    result = get_supply_chain_context_for_ticker(ticker)
    if not result:
        return _envelope(data=None, error=f"No supply-chain linkage for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/consumer-demand/{ticker}")
def intelligence_consumer_demand(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """FRED US consumer-spending context for `ticker` (services/
    consumer_demand_service.py -- retail sales, personal consumption
    expenditures, durable goods consumption). NOT Google Trends search-
    interest data -- see that module's docstring for why (no officially
    licensed, commercial-use-safe search-trends API exists). Only
    populated for tickers with a real consumer-spending linkage (large
    retailers, e-commerce, consumer-discretionary ETFs -- see that
    module's _TICKER_TO_NAME) -- any other ticker returns `data: null`,
    never a fabricated reading for an unrelated symbol."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "consumer_demand", response, ticker=ticker.upper())

    from services.consumer_demand_service import get_consumer_demand_context_for_ticker

    ticker = ticker.upper().strip()
    result = get_consumer_demand_context_for_ticker(ticker)
    if not result:
        return _envelope(data=None, error=f"No consumer-spending linkage for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/opportunity-radar")
def intelligence_opportunity_radar(
    response: Response,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Structural macro-mismatch read across US real estate, supply
    chain/manufacturing, and consumer demand (services/
    opportunity_radar_service.py), plus a US macro backdrop. Not
    ticker-specific -- one market-wide snapshot per call, same shape as
    /v1/vix-term-structure.

    Deliberately NOT a fabricated single "Opportunity Score" -- each
    indicator reports its own real % change over its trailing
    observation window (exact dates included), and each industry
    reports a plain count of how many of its indicators are improving/
    worsening/flat. See that module's docstring for the full honesty
    contract."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "opportunity_radar", response)

    from services.opportunity_radar_service import get_opportunity_radar

    result = get_opportunity_radar()
    if not result or not result.get("available"):
        return _envelope(data=None, error=(result or {}).get("message", "Opportunity Radar not available"))

    return _envelope(data=result)


@router.get("/intelligence/v1/exchange/{ticker}")
def intelligence_exchange(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Same crypto ticker's live 24h stats from two real spot exchanges --
    Binance (services/crypto_exchange_service.py) and Coinbase (services/
    coinbase_exchange_service.py) -- side by side. Only populated for the
    tracked crypto tickers both services cover; any other ticker returns
    `data: null`, never a fabricated cross-exchange reading."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "exchange", response, ticker=ticker.upper())

    from services.crypto_exchange_service import get_ticker as _get_binance_ticker
    from services.coinbase_exchange_service import get_ticker as _get_coinbase_ticker

    ticker = ticker.upper().strip()
    binance_row = _get_binance_ticker(ticker)
    coinbase_row = _get_coinbase_ticker(ticker)
    if not binance_row and not coinbase_row:
        return _envelope(data=None, error=f"No exchange data available for {ticker}")

    return _envelope(
        data={"binance": binance_row, "coinbase": coinbase_row},
        meta={"ticker": ticker},
    )


@router.get("/intelligence/v1/fundamentals/{ticker}")
def intelligence_fundamentals(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Latest annual (10-K) financial-statement facts for `ticker`
    (services/sec_xbrl_service.py -- revenue, net income, diluted EPS,
    total assets/liabilities, operating cash flow, straight from SEC
    XBRL Company Facts). The first real fundamentals data in the
    Intelligence API -- every other endpoint here is positioning,
    event-driven activity, or macro/commodity context, not the
    company's own reported financial statements. 24h server-side
    cached."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "fundamentals", response, ticker=ticker.upper())

    from services.sec_xbrl_service import get_company_facts

    ticker = ticker.upper().strip()
    result = get_company_facts(ticker)
    if not result or not result.get("facts"):
        return _envelope(data=None, error=f"No 10-K fundamentals data available for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/vix-term-structure")
def intelligence_vix_term_structure(
    response: Response,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """CBOE VIX9D/VIX/VIX3M/VIX6M term structure (services/
    cboe_vix_service.py) -- the options market's own forward-looking
    volatility curve, plus a contango/backwardation regime read. Not
    ticker-specific -- one market-wide snapshot per call."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "vix_term_structure", response)

    from services.cboe_vix_service import get_snapshot

    result = get_snapshot()
    if not result or not result.get("available"):
        return _envelope(data=None, error=(result or {}).get("message", "VIX term structure not available"))

    return _envelope(data=result)


@router.get("/intelligence/v1/bank-health/{ticker}")
def intelligence_bank_health(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """FDIC Call Report health (ROA/ROE/assets/equity) for `ticker`'s
    lead bank subsidiary (services/fdic_banking_service.py). Only
    populated for the handful of major publicly-traded bank holding
    companies this module explicitly maps to a real FDIC certificate
    number (see _TICKER_TO_CERT) -- any other ticker returns `data:
    null`, never a guessed match. Reflects the regulated bank
    subsidiary's own Call Report, not consolidated holding-company
    GAAP financials."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "bank_health", response, ticker=ticker.upper())

    from services.fdic_banking_service import get_bank_health

    ticker = ticker.upper().strip()
    result = get_bank_health(ticker)
    if not result:
        return _envelope(data=None, error=f"No FDIC-mapped bank subsidiary for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.get("/intelligence/v1/agriculture/{ticker}")
def intelligence_agriculture(
    response: Response,
    ticker: str,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """USDA agricultural-commodity price-received context for `ticker`
    (services/usda_agriculture_service.py -- corn/wheat/soybean, pairs
    with CORN/WEAT/SOYB the same way /v1/energy pairs with USO/UNG).
    Only populated for tickers with a real commodity linkage; any other
    ticker returns `data: null`."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "agriculture", response, ticker=ticker.upper())

    from services.usda_agriculture_service import get_agriculture_context_for_ticker

    ticker = ticker.upper().strip()
    result = get_agriculture_context_for_ticker(ticker)
    if not result:
        return _envelope(data=None, error=f"No agricultural-commodity linkage for {ticker}")

    return _envelope(data=result, meta={"ticker": ticker})


@router.post("/intelligence/v1/webhooks/subscribe")
def intelligence_webhooks_subscribe(
    body: WebhookSubscribeRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Pro-tier feature (2026-08-28, AJ: "重有咩賺錢位" -> Webhook Pro專屬):
    push notifications instead of polling, for 2 real Data Factory
    events -- see services/webhook_service.py's VALID_EVENT_TYPES for
    the exact list and why these two were chosen (both already backed by
    a daily scheduled job, so this promises honest same-cadence delivery,
    never a fabricated "real-time" claim). Does NOT spend quota -- this
    is a management action, not a data read."""
    auth = _require_api_key(x_api_key)
    if auth["tier"] == "free":
        raise HTTPException(status_code=403, detail="Webhooks are a Pro-tier feature. Upgrade at https://www.xfinlab.com/pricing.html")

    from services.webhook_service import subscribe
    result = subscribe(x_api_key, body.event_type, body.url, ticker=body.ticker)
    if not result["ok"]:
        return _envelope(data=None, error=result["error"])
    return _envelope(data={"id": result["id"], "event_type": body.event_type, "ticker": body.ticker, "url": body.url})


@router.get("/intelligence/v1/webhooks")
def intelligence_webhooks_list(
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Lists every webhook subscription owned by the caller's own API
    key -- never another key's. Read-only, no quota spend."""
    auth = _require_api_key(x_api_key)
    from services.webhook_service import list_for_key
    return _envelope(data={"webhooks": list_for_key(x_api_key)})


@router.delete("/intelligence/v1/webhooks/{webhook_id}")
def intelligence_webhooks_unsubscribe(
    webhook_id: int,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Deletes a webhook subscription -- only if it belongs to the
    caller's own API key (services/webhook_service.py's unsubscribe()
    checks both id AND api_key in the same DELETE, so guessing another
    key's id can never delete their subscription)."""
    auth = _require_api_key(x_api_key)
    from services.webhook_service import unsubscribe
    deleted = unsubscribe(x_api_key, webhook_id)
    if not deleted:
        return _envelope(data=None, error=f"No webhook subscription {webhook_id} found for this API key")
    return _envelope(data={"deleted": True, "id": webhook_id})


# ---------------------------------------------------------------------------
# 2026-08-17 (task #4 follow-up, AJ: "重有咩可以升級" -- upgrade #2, OpenAPI
# spec export): a hand-scoped OpenAPI 3.x document covering ONLY the 7/8
# publicly-documented endpoints above -- deliberately NOT the app's default
# /openapi.json (which would leak all ~50 internal routers: admin, auth,
# billing, etc. -- see backend/main.py, no custom openapi_url was ever set).
# Built from get_openapi(routes=router.routes) so path/param/request-body
# schemas (esp. StressTestRequest) stay in sync with the real route
# signatures automatically, then filtered down to just PUBLIC_INTEL_PATHS
# and re-prefixed with /api to match the real mounted path. No response_model
# is set on any of these routes (see _envelope() above -- every endpoint
# returns the same {"success","data","meta","error"} shape by convention
# rather than a per-endpoint Pydantic model), so response schemas in the
# generated doc are intentionally generic; the value here is accurate
# paths/params/auth/request-body docs a codegen tool or Postman can import.
# ---------------------------------------------------------------------------
PUBLIC_INTEL_PATHS = {
    "/intelligence/v1/events",
    "/intelligence/v1/sentiment",
    "/intelligence/v1/debate",
    "/intelligence/v1/intel/latest",
    "/intelligence/v1/intel/{ticker}",
    "/intelligence/v1/technical/{ticker}",
    "/intelligence/v1/stress-test",
    "/intelligence/v1/regime-signal/{ticker}",
    "/intelligence/v1/insider/{ticker}",
    "/intelligence/v1/company-network/{ticker}",
    "/intelligence/v1/short-interest/{ticker}",
    "/intelligence/v1/energy/{ticker}",
    "/intelligence/v1/exchange/{ticker}",
    "/intelligence/v1/fundamentals/{ticker}",
    "/intelligence/v1/vix-term-structure",
    "/intelligence/v1/bank-health/{ticker}",
    "/intelligence/v1/agriculture/{ticker}",
    "/intelligence/v1/real-estate/{ticker}",
    "/intelligence/v1/supply-chain/{ticker}",
    "/intelligence/v1/consumer-demand/{ticker}",
    "/intelligence/v1/opportunity-radar",
    "/intelligence/v1/webhooks/subscribe",
    "/intelligence/v1/webhooks",
    "/intelligence/v1/webhooks/{webhook_id}",
}

# Endpoints that can return a 503 (upstream engine unreachable) on top of
# the shared 401/429 -- see intelligence_sentiment/intelligence_debate above.
_PATHS_WITH_503 = {"/intelligence/v1/sentiment", "/intelligence/v1/debate"}


def _build_scoped_openapi_dict() -> dict:
    """Shared by GET /intelligence/openapi.json and GET /intelligence/
    postman.json (roadmap item #2, 2026-08-17) -- both need the same
    scoped-and-filtered document, so the Postman converter below builds
    off this instead of re-deriving its own view of the 7 public routes."""
    raw = get_openapi(
        title="XFINLAB Intelligence API",
        version="1.0.0",
        description=(
            "Structured, real market intelligence for developers -- market events, "
            "FinBERT sentiment, multi-agent AI debate, an AI-structured intelligence "
            "feed, technical/market-structure analysis, Monte Carlo stress testing, "
            "and a regime-aware signal. Every response is traceable to a real "
            "computation -- never a fabricated number or confidence score. "
            "Get a free key instantly at "
            "https://www.xfinlab.com/intelligence-api.html#access"
        ),
        routes=router.routes,
    )

    filtered_paths: dict = {}
    for path, item in (raw.get("paths") or {}).items():
        if path not in PUBLIC_INTEL_PATHS:
            continue
        for method_item in item.values():
            if not isinstance(method_item, dict):
                continue
            method_item["security"] = [{"ApiKeyAuth": []}]
            responses = method_item.setdefault("responses", {})
            responses["401"] = {"description": "Missing or invalid X-API-Key header"}
            responses["429"] = {"description": "Daily quota exceeded for this key's tier"}
            if path in _PATHS_WITH_503:
                responses["503"] = {"description": "Upstream engine temporarily unavailable"}
        filtered_paths["/api" + path] = item

    # Only keep schemas actually referenced by the filtered paths (e.g. not
    # EarlyAccessRequest/FreeSignupRequest, which belong to routes excluded
    # from this public doc). Closure over nested refs (e.g. HTTPValidation
    # Error -> ValidationError) since a kept schema can itself reference
    # another schema not directly named in any path.
    import json as _json
    import re as _re
    all_schemas = (raw.get("components") or {}).get("schemas", {})
    referenced = set(_re.findall(r'"#/components/schemas/([A-Za-z0-9_]+)"', _json.dumps(filtered_paths)))
    changed = True
    while changed:
        changed = False
        for name in list(referenced):
            schema = all_schemas.get(name)
            if not schema:
                continue
            for ref in _re.findall(r'"#/components/schemas/([A-Za-z0-9_]+)"', _json.dumps(schema)):
                if ref not in referenced:
                    referenced.add(ref)
                    changed = True
    kept_schemas = {name: schema for name, schema in all_schemas.items() if name in referenced}

    return {
        "openapi": raw.get("openapi", "3.1.0"),
        "info": {
            "title": "XFINLAB Intelligence API",
            "version": "1.0.0",
            "description": raw.get("info", {}).get("description", ""),
        },
        "servers": [{"url": "https://api.xfinlab.com"}],
        "paths": filtered_paths,
        "components": {
            "schemas": kept_schemas,
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            },
        },
    }


@router.get("/intelligence/openapi.json", include_in_schema=False)
def intelligence_openapi_spec():
    return _build_scoped_openapi_dict()


# ---------------------------------------------------------------------------
# 2026-08-17 (roadmap item #2, "重有咩可以做" round 2 -- Postman collection):
# hand-rolled OpenAPI-3.x -> Postman Collection v2.1 converter, scoped to
# just the 7 public paths already filtered by _build_scoped_openapi_dict().
# Deliberately NOT using the "Run in Postman" hosted button (that requires
# publishing to a Postman team workspace via their API -- an external
# account dependency and ongoing sync burden this project doesn't have a
# reason to take on yet). Instead this is a plain downloadable/importable
# JSON file -- Postman's own "Import > Link" or "Import > File" flow reads
# a v2.1 collection directly, no hosted-button account needed. Query
# parameters get their real OpenAPI default (or a realistic placeholder
# for required ones, e.g. ticker=AAPL matching the "Try it" console's own
# default), so a newly imported collection runs correctly on first click
# rather than needing every field filled in by hand.
# ---------------------------------------------------------------------------
_PLACEHOLDER_BY_PARAM = {
    "ticker": "AAPL",
    "limit": None,  # falls back to the schema's own default below
    "lang": "en",
    "regime": "trending_up",
    "min_trades": None,
    "period": "6mo",
    "interval": "1d",
    "news_limit": None,
    "regions": "us,hk,china",
    "include_sentiment": True,
}

# Only the one POST endpoint in the public set has a request body -- hand-
# written rather than a generic schema-to-example walker, since adding a
# second POST endpoint (batch/multi-ticker support, also on this roadmap)
# is the natural trigger to revisit this as a real generic converter.
_POSTMAN_BODY_EXAMPLES = {
    "/api/intelligence/v1/stress-test": {
        "symbol": "AAPL",
        "amount": 10000,
        "horizon_days": 252,
    },
}


def _postman_param_value(name: str, schema: dict):
    if name in _PLACEHOLDER_BY_PARAM and _PLACEHOLDER_BY_PARAM[name] is not None:
        return _PLACEHOLDER_BY_PARAM[name]
    if isinstance(schema, dict) and "default" in schema:
        return schema["default"]
    return ""


def _openapi_to_postman_collection(spec: dict) -> dict:
    items = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            method_upper = method.upper()
            query_params = []
            postman_path_parts = []
            resolved_path = path
            # Path params are resolved to a real example value (e.g. AAPL)
            # in both `raw` and `path`, rather than left as Postman
            # `:variable` placeholders -- so an imported request works on
            # the first click without the importer also having to define a
            # separate collection variable just to fill in the ticker.
            for segment in path.split("/"):
                if segment.startswith("{") and segment.endswith("}"):
                    param_name = segment[1:-1]
                    example = str(_PLACEHOLDER_BY_PARAM.get(param_name) or "AAPL")
                    postman_path_parts.append(example)
                    resolved_path = resolved_path.replace(segment, example)
                else:
                    postman_path_parts.append(segment)
            for p in op.get("parameters", []):
                if p.get("in") == "query":
                    value = _postman_param_value(p["name"], p.get("schema", {}))
                    query_params.append({
                        "key": p["name"],
                        "value": "" if value is None else str(value),
                        "description": ("required" if p.get("required") else "optional"),
                        "disabled": not p.get("required", False) and value in ("", None),
                    })

            request_item = {
                "name": op.get("summary") or f"{method_upper} {path}",
                "request": {
                    "method": method_upper,
                    "header": [
                        {"key": "X-API-Key", "value": "{{apiKey}}", "type": "text"}
                    ],
                    "url": {
                        "raw": "{{baseUrl}}" + resolved_path + (
                            "?" + "&".join(f"{q['key']}={q['value']}" for q in query_params if not q["disabled"])
                            if any(not q["disabled"] for q in query_params) else ""
                        ),
                        "host": ["{{baseUrl}}"],
                        "path": [seg for seg in postman_path_parts if seg],
                        "query": query_params,
                    },
                },
                "response": [],
            }
            if op.get("description"):
                request_item["request"]["description"] = op["description"]
            if path in _POSTMAN_BODY_EXAMPLES:
                request_item["request"]["header"].append({"key": "Content-Type", "value": "application/json", "type": "text"})
                import json as _json
                request_item["request"]["body"] = {
                    "mode": "raw",
                    "raw": _json.dumps(_POSTMAN_BODY_EXAMPLES[path], indent=2),
                    "options": {"raw": {"language": "json"}},
                }
            items.append(request_item)

    return {
        "info": {
            "name": spec.get("info", {}).get("title", "XFINLAB Intelligence API"),
            "description": spec.get("info", {}).get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "X-API-Key", "type": "string"},
                {"key": "value", "value": "{{apiKey}}", "type": "string"},
                {"key": "in", "value": "header", "type": "string"},
            ],
        },
        "variable": [
            {"key": "baseUrl", "value": "https://api.xfinlab.com"},
            {"key": "apiKey", "value": "xfl_your_key_here"},
        ],
        "item": items,
    }


@router.get("/intelligence/postman.json", include_in_schema=False)
def intelligence_postman_collection():
    """Public, unauthenticated. Postman Collection v2.1 covering the same 7
    public endpoints as GET /intelligence/openapi.json -- import via
    Postman's Import > Link (pointed straight at this URL) or Import >
    File after downloading it."""
    spec = _build_scoped_openapi_dict()
    return _openapi_to_postman_collection(spec)


# ---------------------------------------------------------------------------
# 2026-08-09 (World Engine Phase 0, XFINLAB_Final_Strategy.md section 5/6/7):
# repackages GDELT global events + macro (World Bank baseline, FRED/ECB
# high-frequency overrides for US/Eurozone) + FinBERT sentiment into one
# "global market map" call across all 10 covered regions. Pure packaging
# of already-built services (see services/world_engine_service.py's
# docstring) -- no new AI calls, same honesty posture as the rest of this
# router. Weighted between `events`/`sentiment` (cheap) and `intel`
# (multi-region, multi-source fan-out, but zero LLM calls unlike intel).
# ---------------------------------------------------------------------------

@router.get("/intelligence/v1/world/market-map")
def world_market_map(
    response: Response,
    regions: Optional[str] = None,
    news_limit: int = 6,
    include_sentiment: bool = True,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """Global market map: for each region, macro indicators (with source
    attribution -- world_bank/fred/ecb) + filtered headlines + FinBERT
    sentiment, plus a top-level global headlines feed. `regions` is an
    optional comma-separated subset (e.g. "us,hk,china"); omit for all 10.
    See services/world_engine_service.list_regions() / GET
    /intelligence/v1/world/regions for valid keys."""
    auth = _require_api_key(x_api_key)
    _check_and_spend_quota(x_api_key, auth["tier"], "world_map", response)

    from services.world_engine_service import get_global_market_map

    region_list = [r.strip() for r in regions.split(",") if r.strip()] if regions else None
    news_limit = max(1, min(news_limit, 20))

    result = get_global_market_map(regions=region_list, news_limit=news_limit, include_sentiment=include_sentiment)
    if not result.get("available"):
        return _envelope(data=None, error=result.get("message", "World market map unavailable"))

    return _envelope(data=result, meta={"regions": list(result["regions"].keys())})


@router.get("/intelligence/v1/world/regions")
def world_regions(x_api_key: str = Header(None, alias="X-API-Key")):
    """No-cost lookup of valid region keys for GET /world/market-map --
    not quota-weighted since it's static metadata, not a data fetch."""
    _require_api_key(x_api_key)

    from services.world_engine_service import list_regions

    return _envelope(data=list_regions())


# ---------------------------------------------------------------------------
# 2026-08-09 (task #724, AJ "全做" batch): logged-in-user self-service key
# view/regenerate, for dashboard.html's account area. Auth here is the same
# `token` query-param + jwt_handler.verify_token() convention already used
# by backend/auth/auth.py's /auth/me -- NOT the admin `token` param above
# (that one goes through api.admin.verify_admin, a different secret/check
# entirely; reusing the param name would be confusing but they're unrelated
# mechanisms). Never returns a raw key on GET -- consistent with the
# "shown once at issuance" posture documented in api_key_service.py.
# ---------------------------------------------------------------------------

def _require_user(token: str) -> str:
    """Returns the caller's email or raises 401. Local helper (not
    api/intelligence.py's own _require_api_key, which checks an
    X-API-Key header for the sold product itself -- this is a normal
    logged-in-XFINLAB-user check, for the dashboard account page)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    from backend.auth.jwt_handler import verify_token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload["sub"]


@router.get("/intelligence/v1/my-key")
def my_key_status(token: str = None):
    email = _require_user(token)
    return _envelope(data=api_key_service.get_my_key_status(email))


@router.post("/intelligence/v1/my-key/regenerate")
def my_key_regenerate(token: str = None):
    email = _require_user(token)
    result = api_key_service.regenerate_key_for_user(email)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return _envelope(data=result)


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
