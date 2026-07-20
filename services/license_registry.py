"""
License Registry — XFINLAB Architecture, Phase 1.

Central, single-source-of-truth list of every external data source's
licensing status. This is pure bookkeeping: it does NOT change any live
request behaviour by itself. Its job is to make "can we legally use this
data source, and how?" a one-line lookup instead of institutional
knowledge that lives in someone's head.

Directly addresses the known risk: Yahoo Finance (via yfinance) is used
for market data but its terms of service do not grant a commercial-use
license — this registry documents that clearly so it can't get lost, and
gives future data-source swaps a checklist to fill in.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LicenseRecord:
    source_id: str
    license_type: str  # "commercial" | "non_commercial" | "unknown" | "public_domain"
    commercial_use_allowed: bool
    terms_url: Optional[str] = None
    risk_level: str = "unknown"  # "low" | "medium" | "high"
    notes: str = ""
    replacement_candidates: List[str] = field(default_factory=list)


# --- Registry data ---
# Add a new entry here whenever a new external data source is introduced
# anywhere in the codebase (market data, news, crypto, etc).
_LICENSES: Dict[str, LicenseRecord] = {
    "yahoo_finance": LicenseRecord(
        source_id="yahoo_finance",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        risk_level="high",
        notes=(
            "Accessed via the unofficial `yfinance` Python library, which "
            "scrapes Yahoo Finance's public endpoints. Yahoo's own ToS does "
            "not grant a commercial-use license for this data. XFINLAB is a "
            "commercial product, so this is a known legal risk that should "
            "be resolved before scaling paid usage. Currently used in "
            "services/market_data_service.py and services/"
            "technical_analysis_service.py."
        ),
        replacement_candidates=[
            "polygon_io", "twelve_data", "finnhub", "eod_historical_data", "alpaca_markets",
        ],
    ),
    # 2026-07-18 data-compliance pass: this registry previously only had
    # ONE entry (yahoo_finance) even though 5 other external sources were
    # already live in the codebase -- adding them so "can we legally use
    # this?" is a real one-line lookup for every source actually in use,
    # not just the one that happened to be documented first.
    "alpaca_markets": LicenseRecord(
        source_id="alpaca_markets",
        license_type="commercial",
        commercial_use_allowed=True,
        terms_url="https://alpaca.markets/support/end-user-agreement",
        risk_level="low",
        notes=(
            "Free IEX feed via Alpaca's Market Data API. Alpaca's terms "
            "explicitly permit displaying this data to end users in a "
            "commercial app -- the one source in this registry that's "
            "actually clean for XFINLAB's use case as-is. US-listed "
            "symbols only; see services/technical_analysis_service.py's "
            "Alpaca-first / yfinance-fallback routing."
        ),
    ),
    "newsapi_org": LicenseRecord(
        source_id="newsapi_org",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://newsapi.org/terms",
        risk_level="medium",
        notes=(
            "Used by services/news_service.py. NewsAPI.org's free "
            "'Developer' plan is explicitly for development/testing only "
            "and disallows production commercial use; their paid "
            "'Business' plan is required for that. Whether this project's "
            "NEWS_API_KEY is on the free or a paid plan hasn't been "
            "confirmed here -- flag as commercial_use_allowed=False until "
            "verified, rather than assuming it's fine. Exposure is "
            "somewhat reduced regardless: only title/source/published_at/"
            "url are stored (see NewsService.get_company_news()), never "
            "full article text, and users are pointed back to the "
            "original article via `url` rather than XFINLAB redisplaying "
            "the content itself."
        ),
        replacement_candidates=["newsapi_org_business_tier"],
    ),
    "coingecko": LicenseRecord(
        source_id="coingecko",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://www.coingecko.com/en/api_terms",
        risk_level="medium",
        notes=(
            "Used by services/crypto_service.py (free, no-API-key public "
            "endpoints). CoinGecko's public/Demo API terms are oriented "
            "around non-commercial/personal use; their docs point "
            "commercial products at a paid 'Pro' API plan. Whether that's "
            "needed for XFINLAB's specific usage pattern (aggregate price/"
            "market-cap/volume figures, not redistributing raw datasets) "
            "hasn't been legally confirmed -- flagged conservatively."
        ),
        replacement_candidates=["coingecko_pro"],
    ),
    "reddit_unauthenticated": LicenseRecord(
        source_id="reddit_unauthenticated",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://www.redditinc.com/policies/data-api-terms",
        risk_level="medium",
        notes=(
            "growth/reddit_bot.py hits Reddit's unauthenticated /r/{sub}/"
            "hot.json endpoint (not the official OAuth Data API). Not "
            "currently wired into any live production endpoint (grepped: "
            "no api/ router or scheduled job imports RedditBot as of "
            "2026-07-18), so exposure today is limited to this standalone "
            "script -- but Reddit's Data API terms require going through "
            "their official OAuth API with a registered app for any real "
            "usage, which this doesn't do. 2026-07-18 fix stopped the "
            "worse practice of spoofing a Chrome User-Agent (see the "
            "file's own docstring) as an interim mitigation; migrating to "
            "`praw` + a registered Reddit app is the real fix, needs "
            "Reddit developer credentials this session doesn't have."
        ),
        replacement_candidates=["reddit_oauth_api_via_praw"],
    ),
    # 2026-07-18 Data Layer expansion pass: services/rss_news_service.py's
    # 3 live sources, plus documenting the StockTwits gap this same pass
    # found and deliberately did NOT build around (see task #212 -- their
    # developer registrations are closed and their ToS bars unauthorized
    # automated extraction, so there is no compliant path today).
    "investing_com_rss": LicenseRecord(
        source_id="investing_com_rss",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://www.investing.com/rss/news.rss",
        risk_level="medium",
        notes=(
            "Used by services/rss_news_service.py. Publicly published RSS "
            "feed intended for syndication; exact commercial-redistribution "
            "terms weren't independently verified this pass -- flagged "
            "conservatively. Exposure minimized: only title/link/"
            "published_at/source kept, never full article text, same "
            "convention as NewsService.get_company_news()."
        ),
    ),
    "globenewswire_rss": LicenseRecord(
        source_id="globenewswire_rss",
        license_type="public_domain",
        commercial_use_allowed=True,
        terms_url="https://www.globenewswire.com/rss/list",
        risk_level="low",
        notes=(
            "Used by services/rss_news_service.py. GlobeNewswire's RSS "
            "feeds are explicitly published for public syndication "
            "(journalists/bloggers/readers can freely subscribe); content "
            "is itself a company's own public press release. Only title/"
            "link/published_at kept, never full release text."
        ),
    ),
    "prnewswire_rss": LicenseRecord(
        source_id="prnewswire_rss",
        license_type="public_domain",
        commercial_use_allowed=True,
        terms_url="https://www.prnewswire.com/rss/",
        risk_level="low",
        notes=(
            "Used by services/rss_news_service.py. Same reasoning as "
            "globenewswire_rss -- publicly syndicated company press "
            "releases, headline/link/date only kept here."
        ),
    ),
    "stocktwits": LicenseRecord(
        source_id="stocktwits",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://stocktwits.com/about/legal/terms/",
        risk_level="high",
        notes=(
            "NOT integrated anywhere in this codebase (checked 2026-07-18, "
            "see task #212). Their developer API registration is "
            "explicitly closed ('we unfortunately won't be accepting new "
            "registrations'), and their current Terms of Service bar "
            "automated data extraction 'except through an approved API'. "
            "The only working endpoint found (unauthenticated symbol "
            "stream) is therefore against their own terms to use -- "
            "recorded here so nobody re-discovers this gap and quietly "
            "scrapes it without knowing it's against ToS. Revisit if/when "
            "their developer program reopens."
        ),
        replacement_candidates=["stocktwits_official_api_when_reopened"],
    ),
    "sec_edgar": LicenseRecord(
        source_id="sec_edgar",
        license_type="public_domain",
        commercial_use_allowed=True,
        terms_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        risk_level="low",
        notes=(
            "Used by services/fundamentals_service.py (EPS/Revenue via "
            "the free XBRL companyconcept API, US SEC filers only) to "
            "fill the fund_score/valuation gap this codebase previously "
            "had no real data source for. Public-domain US government "
            "data, no API key, 10 req/sec limit, no daily cap -- the "
            "same underlying data Bloomberg/FactSet/Refinitiv build "
            "their commercial products on. Chosen over Finnhub (needs "
            "written approval for commercial use on the free tier) and "
            "Financial Modeling Prep (free tier explicitly requires a "
            "paid Data Display/Licensing Agreement before commercial "
            "display) -- the only one of the three with no commercial-"
            "use ambiguity or extra cost."
        ),
    ),
    "twse_official": LicenseRecord(
        source_id="twse_official",
        license_type="public_domain",
        commercial_use_allowed=True,
        terms_url="https://www.twse.com.tw",
        risk_level="low",
        notes=(
            "Taiwan Stock Exchange's own free, anonymous, official JSON "
            "endpoint (MI_INDEX20 -- today's top 20 securities by volume/"
            "value), used by services/trending_stocks_service.py. A "
            "government exchange publishing its own market data for "
            "public consumption -- the lowest-risk source in this "
            "registry alongside alpaca_markets."
        ),
    ),
    "huggingface_inference_api": LicenseRecord(
        source_id="huggingface_inference_api",
        license_type="unknown",
        commercial_use_allowed=True,
        terms_url="https://huggingface.co/inference-api",
        risk_level="medium",
        notes=(
            "Used by services/finbert_sentiment_service.py (Stage 2 "
            "roadmap: 'FinBERT 新聞情緒升級') to call the ProsusAI/finbert "
            "model hosted on HuggingFace's Inference API, replacing/"
            "augmenting the old hand-picked keyword sentiment list in "
            "engines/news_engine.py. HuggingFace's own Inference API "
            "terms generally permit commercial use of hosted public "
            "models, but the ProsusAI/finbert model card's own license "
            "terms have not been independently re-verified for this "
            "specific commercial usage pattern (calling it via the "
            "hosted API rather than downloading the weights) -- flagged "
            "conservatively, same treatment as coingecko_free_tier above. "
            "Gated entirely behind an HF_API_TOKEN env var "
            "(finbert_sentiment_service.is_available()); when unset or "
            "the API call fails, callers fall back to the original "
            "keyword heuristic rather than fabricating a FinBERT-"
            "labelled score. No new package dependency -- called over "
            "plain HTTPS via services/outbound_http.py's backoff helper, "
            "not the `transformers`/`torch` self-hosting path (this "
            "backend is a single small Railway dyno; a ~440MB in-process "
            "model was judged not worth the memory/cold-start cost)."
        ),
    ),
    "shipping_sector_etfs_proxy": LicenseRecord(
        source_id="shipping_sector_etfs_proxy",
        license_type="commercial",
        commercial_use_allowed=True,
        risk_level="low",
        notes=(
            "Used by services/shipping_proxy_service.py (Stage 3 roadmap: "
            "'航運/供應鏈壓力代理指標'). Not a new external data source -- "
            "just two additional tickers (BDRY, BOAT, both real/actively-"
            "traded ETFs) routed through the exact same Alpaca-first/"
            "yfinance-fallback OHLC infra already documented under "
            "alpaca_markets / yahoo_finance above (see services/"
            "technical_analysis_service.fetch_ohlc_history). Explicitly "
            "NOT the official Baltic Dry Index (BDI) -- that's a "
            "licensed, subscription-only Baltic Exchange benchmark this "
            "codebase has no feed for. Every output field of this service "
            "is labeled 'proxy' precisely so it's never mistaken for the "
            "real BDI. Inherits the same risk profile as its two upstream "
            "sources: low when Alpaca serves the request, elevated to "
            "yahoo_finance's risk_level on its yfinance fallback path."
        ),
        replacement_candidates=["oilpriceapi_baltic_dry_index"],
    ),
    "oilpriceapi_baltic_dry_index": LicenseRecord(
        source_id="oilpriceapi_baltic_dry_index",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://www.oilpriceapi.com",
        risk_level="high",
        notes=(
            "NOT currently integrated anywhere in this codebase -- "
            "documented here only as a tracked future option, per the "
            "Stage 3 roadmap's mention of an 'optional real-BDI path'. "
            "OilPriceAPI's free tier exposes a Baltic Dry Index endpoint, "
            "but its commercial-use terms have not been reviewed and it "
            "would introduce a new required paid/keyed external "
            "dependency (OILPRICEAPI_KEY) for a single metric. Deliberately "
            "not built speculatively against an unverified ToS -- the "
            "same reasoning that led this codebase to previously reject "
            "StockTwits (see stocktwits above) and prefer SEC EDGAR over "
            "paid FMP. If a user configures OILPRICEAPI_KEY themselves in "
            "the future, this entry should be revisited and its ToS "
            "actually reviewed before any code goes live behind that key."
        ),
    ),
}


def get_license(source_id: str) -> Optional[LicenseRecord]:
    return _LICENSES.get(source_id)


def list_licenses() -> List[LicenseRecord]:
    return list(_LICENSES.values())


def list_high_risk_sources() -> List[LicenseRecord]:
    """Sources that should be prioritised for replacement or a paid plan."""
    return [r for r in _LICENSES.values() if r.risk_level == "high"]


def register_license(record: LicenseRecord) -> None:
    """Add or update a license record. Call this when a new data source is
    introduced anywhere in the codebase, so the registry never drifts out
    of sync with reality."""
    _LICENSES[record.source_id] = record


if __name__ == "__main__":
    for rec in list_high_risk_sources():
        print(f"[HIGH RISK] {rec.source_id}: {rec.notes}")
