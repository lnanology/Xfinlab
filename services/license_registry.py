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
        license_type="commercial",
        commercial_use_allowed=True,
        terms_url="https://huggingface.co/terms-of-service",
        risk_level="low",
        notes=(
            "Used by services/finbert_sentiment_service.py (Stage 2 "
            "roadmap: 'FinBERT 新聞情緒升級') to call the ProsusAI/finbert "
            "model hosted on HuggingFace's Inference API, replacing/"
            "augmenting the old hand-picked keyword sentiment list in "
            "engines/news_engine.py. "
            "2026-07-31 re-verification (directly fetched huggingface.co/"
            "terms-of-service): 'Inference Providers' is explicitly listed "
            "as one of Hugging Face's own paid, usage-metered commercial "
            "Services ('Payment' section: billed monthly in advance plus "
            "usage-based overage) -- there is no personal/non-commercial "
            "restriction anywhere in this ToS, unlike Polygon/Twelve Data/"
            "Marketstack/Finnhub above. This lowers risk from the prior "
            "conservative 'medium' rating to 'low'. One remaining, lower-"
            "stakes caveat: the ProsusAI/finbert model card itself "
            "(confirmed via huggingface.co/api/models/ProsusAI/finbert) "
            "carries NO declared license tag at all -- so the model "
            "WEIGHTS' own reuse terms are technically undefined/all-"
            "rights-reserved by ProsusAI. This does not block XFINLAB's "
            "actual usage pattern, though: this codebase only ever "
            "consumes classification OUTPUTS via the hosted API call "
            "(governed by the HF platform ToS just confirmed above), and "
            "never downloads, redistributes, or self-hosts the model "
            "weights -- so the model's own undeclared license does not "
            "apply to XFINLAB's usage the way it would if the weights "
            "were being redistributed. Gated entirely behind an "
            "HF_API_TOKEN env var (finbert_sentiment_service.is_"
            "available()); when unset or the API call fails, callers fall "
            "back to the original keyword heuristic rather than "
            "fabricating a FinBERT-labelled score. No new package "
            "dependency -- called over plain HTTPS via services/"
            "outbound_http.py's backoff helper, not the `transformers`/"
            "`torch` self-hosting path (this backend is a single small "
            "Railway dyno; a ~440MB in-process model was judged not worth "
            "the memory/cold-start cost)."
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
    # 2026-07-31: added after the user asked to add Polygon.io and Twelve
    # Data as free-tier rotation candidates alongside Alpaca. Both
    # providers' free tiers turned out to be personal/non-commercial-use
    # only on review (see notes below) -- same class of risk already
    # flagged for yahoo_finance above. Per an explicit decision with the
    # user, both are gated to dev/test-only usage in the new
    # services/dev_data_rotation_service.py harness (never imported by
    # api/*.py or backend/main.py) rather than wired into production.
    "polygon_io": LicenseRecord(
        source_id="polygon_io",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://massive.com/terms/market_data_terms.pdf",
        risk_level="high",
        notes=(
            "Free 'Basic' tier: end-of-day/delayed data, 5 calls/minute, "
            "no credit card. Polygon's (now rebranded Massive.com) Market "
            "Data ToS states any business/professional/commercial use is "
            "incompatible with 'Non-Professional' status -- even on "
            "behalf of an organization outside the securities industry. "
            "XFINLAB is a commercial product serving real end users, so "
            "the free tier alone does not license production use; a paid "
            "Business-tier plan would be required first. NOT wired into "
            "any production route -- used only in services/"
            "dev_data_rotation_service.py (gated behind "
            "ALLOW_DEV_DATA_ROTATION=true) to validate the rotation/rate-"
            "limit engineering pattern with real API responses."
        ),
        replacement_candidates=["polygon_io_business_tier"],
    ),
    "twelve_data": LicenseRecord(
        source_id="twelve_data",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://twelvedata.com/terms",
        risk_level="high",
        notes=(
            "Free 'Basic' plan: 8 calls/minute, 800 calls/day, covers US "
            "equities/forex/crypto. Twelve Data's own terms state free-"
            "subscription users 'may only use the Services for personal, "
            "non-commercial purposes and may not display or distribute "
            "Twelve Data Services to third parties in any manner' -- an "
            "explicit third-party-display bar that XFINLAB's product "
            "(displaying data to free and paying end users) would breach "
            "on the free tier. Their Business plan (from $29/month) is "
            "required for commercial display/internal use. NOT wired "
            "into any production route -- used only in services/"
            "dev_data_rotation_service.py (gated behind "
            "ALLOW_DEV_DATA_ROTATION=true), same treatment as polygon_io "
            "above."
        ),
        replacement_candidates=["twelve_data_business_tier"],
    ),
    # 2026-07-31 (later same day): user asked to add Finnhub and
    # Marketstack too, same "dev/test-only rotation" treatment as
    # Polygon/Twelve Data above -- see services/dev_data_rotation_service.py.
    "finnhub": LicenseRecord(
        source_id="finnhub",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="https://finnhub.io/terms-of-service",
        risk_level="high",
        notes=(
            "Free tier: 60 calls/minute, real-time quotes + company "
            "fundamentals. UNLIKE Polygon/Twelve Data/Marketstack below, "
            "this codebase could NOT independently verify Finnhub's actual "
            "Terms of Service text -- their site is a client-rendered SPA "
            "that blocked both automated fetch and search-snippet access, "
            "and no browser-rendering tool was available in that session "
            "to load the real page. Treated conservatively (commercial_use_"
            "allowed=False) based on circumstantial evidence only: their "
            "own FAQ's noncommittal 'review the terms before commercial "
            "use' wording, and multiple third-party sources noting Finnhub "
            "routes commercial inquiries to sales@finnhub.io for a "
            "'commercial license' (implying the free key alone doesn't "
            "cover it). This entry should be corrected the moment someone "
            "actually reads the primary-source ToS text -- flagged here so "
            "that gap isn't silently forgotten. NOT wired into any "
            "production route -- used only in services/"
            "dev_data_rotation_service.py (gated behind "
            "ALLOW_DEV_DATA_ROTATION=true), same treatment as polygon_io/"
            "twelve_data above."
        ),
        replacement_candidates=["finnhub_commercial_license"],
    ),
    "marketstack": LicenseRecord(
        source_id="marketstack",
        license_type="non_commercial",
        commercial_use_allowed=False,
        terms_url="https://marketstack.com/pricing",
        risk_level="high",
        notes=(
            "Free plan: 100 requests/MONTH (not per-minute), end-of-day "
            "data only, 12 months history. Confirmed directly via "
            "marketstack.com/pricing's own feature comparison table: "
            "'Commercial Use' is listed as an explicit, named, checked "
            "feature starting at the paid Basic plan ($9.99/mo) and above "
            "-- it is visibly ABSENT from the Free plan's feature list. "
            "This is the clearest, most direct confirmation found for any "
            "provider checked this session (a literal named feature gated "
            "to paid tiers on the provider's own site, not an inference "
            "from a sales-contact link). NOT wired into any production "
            "route -- used only in services/dev_data_rotation_service.py "
            "(gated behind ALLOW_DEV_DATA_ROTATION=true), same treatment "
            "as polygon_io/twelve_data/finnhub above."
        ),
        replacement_candidates=["marketstack_basic_tier"],
    ),
    # 2026-07-31: added while building out the free-commercial-source
    # combo the user asked for (GDELT/FRED/ECB) after Polygon/Twelve Data
    # turned out to be free-tier-non-commercial above. All 3 verified by
    # direct fetch of their actual terms pages (not assumed from search
    # snippets) before wiring any of them into services/gdelt_news_service.py
    # / services/global_news_region_service.py.
    "gdelt": LicenseRecord(
        source_id="gdelt",
        license_type="public_domain",
        commercial_use_allowed=True,
        terms_url="https://www.gdeltproject.org/about.html",
        risk_level="low",
        notes=(
            "GDELT's own terms: all datasets 'available for unlimited and "
            "unrestricted use for any academic, commercial, or "
            "governmental use of any kind without fee.' No API key, no "
            "rate-limit-driven commercial gate like Polygon/Twelve Data/"
            "Tiingo/EODHD's free tiers above. Used by services/"
            "gdelt_news_service.py (GDELT 2.0 DOC API, article-level "
            "search) and wired into services/global_news_region_service.py "
            "as an additional per-region source alongside the existing RSS "
            "pool. Same minimal-retention convention as rss_news_service.py "
            "-- only title/link/published_at/source/language kept, never "
            "full article text."
        ),
    ),
    "fred": LicenseRecord(
        source_id="fred",
        license_type="commercial",
        commercial_use_allowed=True,
        terms_url="https://fred.stlouisfed.org/docs/api/terms_of_use.html",
        risk_level="low",
        notes=(
            "Free API key (St. Louis Fed). Terms of Use verified by direct "
            "fetch 2026-07-31: no personal/non-commercial-only bar like "
            "Polygon/Twelve Data/Tiingo/EODHD above -- the terms even "
            "classify the API itself as a 'commercial item' for government-"
            "procurement purposes. Two real obligations to honor, not "
            "optional: (1) mandatory attribution notice wherever used -- "
            "'This product uses the FRED® API but is not endorsed or "
            "certified by the Federal Reserve Bank of St. Louis.'; (2) some "
            "individual DATA SERIES (not the API itself) are owned by third "
            "parties and marked 'Copyright' in their notes -- those specific "
            "series require contacting the data owner before any non-"
            "personal use, so any series pulled in must be checked for that "
            "marker before display. NOT YET integrated into any service as "
            "of this entry -- documented here ahead of building services/"
            "fred_macro_service.py so the attribution + copyrighted-series "
            "check ships from day one, not bolted on after."
        ),
    ),
    "ecb_data_portal": LicenseRecord(
        source_id="ecb_data_portal",
        license_type="commercial",
        commercial_use_allowed=True,
        terms_url="https://www.ecb.europa.eu/services/disclaimer/html/index.en.html",
        risk_level="low",
        notes=(
            "Free SDMX 2.1 REST API, no key required. ECB's disclaimer & "
            "copyright page verified by direct fetch 2026-07-31: 'users of "
            "this website may make free use of the information' subject to "
            "conditions -- (1) must cite the ECB as source when distributed/"
            "reproduced; (2) if incorporated into something SOLD (any "
            "medium), must inform buyers the data is available free of "
            "charge from the ECB, both before payment and each time they "
            "access it -- directly relevant since XFINLAB is a paid "
            "product, so any ECB-sourced figure shown to paying users needs "
            "that disclosure somewhere reachable (e.g. a data-sources/"
            "methodology page), not just a citation; (3) modifications "
            "(e.g. seasonal adjustment) must be stated explicitly. No "
            "blanket non-commercial bar like Polygon/Twelve Data/Tiingo/"
            "EODHD. NOT YET integrated into any service as of this entry."
        ),
    ),
    # 2026-07-31 (later same day): user shared a research summary of
    # open-source finance tooling and asked to add BaoStock specifically
    # (the only one of that list judged to fill a real product gap --
    # zero A-share coverage anywhere in this codebase's data layer).
    "baostock": LicenseRecord(
        source_id="baostock",
        license_type="unknown",
        commercial_use_allowed=False,
        terms_url="http://www.baostock.com",
        risk_level="high",
        notes=(
            "Free, no-registration Python client for China A-share daily "
            "history/fundamentals (pip install baostock; actively "
            "maintained, v0.9.1 as of Apr 2026 per PyPI). The wrapper "
            "LIBRARY itself is confirmed BSD-licensed via PyPI/GitHub "
            "PKG-INFO -- that covers the Python client code only, NOT "
            "necessarily the underlying A-share DATA's redistribution "
            "terms, which is the actual open question here. Same "
            "situation as finnhub above: baostock.com is a client-"
            "rendered SPA that blocked both WebFetch and WebSearch from "
            "seeing the real 免责声明/使用条款 (disclaimer/terms-of-use) "
            "page text, and no browser-rendering tool was available in "
            "that session to load it. Treated conservatively "
            "(commercial_use_allowed=False) purely because a permissive "
            "code license is not evidence either way about the data's "
            "own terms -- this is not circumstantial evidence pointing "
            "toward non-commercial like finnhub's, just a genuine "
            "unknown. This entry should be corrected the moment someone "
            "actually reads baostock.com's primary-source terms text. "
            "NOT wired into any production route -- used only in "
            "services/dev_data_rotation_service.py (gated behind "
            "ALLOW_DEV_DATA_ROTATION=true), same treatment as finnhub/"
            "marketstack/polygon_io/twelve_data above. Also unlike those "
            "four: BaoStock is a stateful login/query/logout session "
            "client, not a metered HTTP API, so the calls_per_minute "
            "figure registered for it in dev_data_rotation_service.py is "
            "a precautionary self-imposed cap, not a provider-published "
            "limit."
        ),
        replacement_candidates=["baostock_verified_commercial_terms", "sec_edgar"],
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
