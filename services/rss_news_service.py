"""
RSS News Ingestion Service -- Data Layer expansion, Step 5 (2026-07-18).

This is the direct follow-up to the user's "合法資料收集" (Legal Data
Collection) proposal's Level 2 tier (RSS) -- one rung more permissive
than Level 3/4 scraping, which this session deliberately did not reach
for without a verified-live source (see module docstring conventions
already established in growth/reddit_bot.py and services/outbound_http.py).

Sources used -- each verified LIVE by direct fetch on 2026-07-18 (not
assumed from a blog post or old training knowledge; RSS feeds get killed
all the time, e.g. Reuters shut down its public RSS feeds back in 2020):

  - GlobeNewswire's "News about Public Companies" feed -- the practical
    stand-in for "listed-company IR/announcement pages": a 3-company
    spot check (AAPL/MSFT/JPM) found NONE of them has a working direct
    IR-site RSS feed of its own, but official company press releases
    (earnings, M&A, offerings, etc.) ARE distributed through
    GlobeNewswire/PR Newswire's public wires -- this is the honest,
    verified-live path to that data, not a workaround.
  - PR Newswire's "Financial Services" news feed, same reasoning.
  - GDELT's global news monitoring (via services/gdelt_news_service.py),
    replacing Investing.com as of 2026-08-11 -- see that date's note
    below.

2026-08-11: Investing.com's RSS feed REMOVED from this pool. A direct
fetch of investing.com/webmaster-tools/rss found Fusion Media's
site-wide footer notice explicitly prohibiting "use, store, reproduce,
display, modify, transmit or distribute" site data without prior
written permission -- unambiguous, not an ambiguous ToS to interpret
(see services/license_registry.py's investing_com_rss entry, upgraded
to confirmed non_commercial/high that same day). Replaced with GDELT
(services/gdelt_news_service.py), already integrated elsewhere in this
codebase and already confirmed public-domain/unrestricted-commercial-use
(GDELT's own terms: "available for unlimited and unrestricted use for
any academic, commercial, or governmental use of any kind without fee").
GDELT indexes global news monitoring across 100+ languages via real
server-side search, which is broader coverage than a single wire's RSS
feed, not just a same-size substitute. get_all_headlines() now merges
GDELT's general macro/market feed; search_headlines() now also calls
GDELT's server-side search in addition to the existing client-side
substring filter over the RSS pool.

Other sources explicitly ruled OUT (checked, not silently skipped --
see services/license_registry.py for the same "documented, not assumed"
convention):
  - StockTwits: developer API registration is currently closed and their
    ToS bars automated extraction without an approved API -- no
    compliant path today (see services/license_registry.py's
    "stocktwits" entry, tracked as a real gap for task #212, not built).
  - Business Wire: public site showed stale content and no free RSS link
    in navigation; their own docs point to a paid feed product.
  - Seeking Alpha, CNN/Fox Business: feed terms explicitly restrict to
    personal, non-commercial use (re-verified 2026-08-11 alongside the
    investing_com_rss check -- same industry-standard restriction, not
    unique to investing.com).
  - Nasdaq / MarketWatch (Dow Jones) feeds: endpoint headers looked live
    but actual item content couldn't be verified this pass, and Dow
    Jones content is explicitly copyrighted -- flagged as a gray zone
    needing a real legal check before integrating, not done here.

Minimal data retention (the proposal's mandatory hygiene rule, same
principle NewsService.get_company_news() already follows for NewsAPI):
only title / source / published_at / link are ever kept -- never the
full article or press-release body. Users are pointed back to the
original source via `link`.

No new pip dependency added -- parsed with the standard-library
xml.etree.ElementTree rather than pulling in `feedparser`, since RSS
2.0's title/link/pubDate/description elements are simple enough not to
need a dedicated library.
"""

import logging
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from services.outbound_http import get_with_backoff
from services import gdelt_news_service

logger = logging.getLogger(__name__)

# 2026-08-30 fix (AJ live-tested /v1/events and /v1/sentiment for "AAPL"
# on the production Intelligence API console and got a real, honest
# "no headlines found" -- not a broken fetch, but a genuinely weak
# result for one of the most-covered stocks in the world). Root cause:
# search_headlines() below matched (and passed to GDELT's search) the
# literal ticker string only -- "aapl" as a title substring, or "AAPL" as
# a GDELT keyword. Real news headlines/articles overwhelmingly say
# "Apple", not the bare ticker, so a ticker-only query structurally
# undershoots for exactly the pool this module has (2 general-purpose
# wires + GDELT's global monitoring, none of which are finance-specific
# feeds where bare tickers are common). This resolves a bare ticker to
# its real SEC-registered company name (same public, no-auth, already-
# proven-reliable source used by services/sec_ownership_service.py,
# services/sec_xbrl_service.py, etc. for the same lookup) and searches
# with BOTH the raw query and the resolved name, unioned -- never
# replacing the raw-query path, so a query that's already a company name
# or a ticker with no SEC match behaves exactly as before.
TICKER_TITLE_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_USER_AGENT = "XFINLABBot/1.0 (+https://www.xfinlab.com; contact: support@xfinlab.com)"
_TICKER_TITLE_CACHE_TTL_DAYS = 7
_ticker_title_cache = {"data": None, "fetched_at": None}
_BARE_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _load_ticker_title_map() -> dict:
    """Own copy of the ticker->title lookup (SEC's own public company_
    tickers.json) -- deliberately independent of services/sec_ownership_
    service.py's copy, matching this codebase's per-module-independence
    convention (see services/sec_form4_service.py's module docstring for
    why every SEC-adjacent module keeps its own resolver rather than a
    shared import)."""
    today = date.today()
    cached = _ticker_title_cache["data"]
    fetched_at = _ticker_title_cache["fetched_at"]
    if cached and fetched_at and (today - fetched_at).days < _TICKER_TITLE_CACHE_TTL_DAYS:
        return cached
    try:
        res = get_with_backoff(TICKER_TITLE_MAP_URL, headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        if res.status_code != 200:
            return cached or {}
        payload = res.json()
        mapping = {str(e["ticker"]).upper(): (e.get("title") or "") for e in payload.values()}
        _ticker_title_cache["data"] = mapping
        _ticker_title_cache["fetched_at"] = today
        return mapping
    except Exception as e:
        logger.info("rss_news_service: ticker->title map fetch failed: %s", e)
        return cached or {}


def _resolve_company_name(query: str) -> Optional[str]:
    """Returns a real SEC-registered company name for a bare-ticker-
    looking query (e.g. "AAPL" -> "Apple Inc."), or None if `query`
    doesn't look like a bare ticker or has no match -- never a guessed
    name. "Inc."/"Corp"/"Corporation"/etc suffix is stripped for search
    purposes (news headlines almost never include the legal suffix)."""
    q = (query or "").strip().upper()
    if not _BARE_TICKER_RE.match(q):
        return None
    title = _load_ticker_title_map().get(q)
    if not title:
        return None
    short = re.sub(
        r"\s+(Inc\.?|Incorporated|Corp\.?|Corporation|Co\.|Company|Ltd\.?|Limited|plc|Group|Holdings|N\.V\.|S\.A\.)\.?$",
        "", title, flags=re.I,
    ).strip()
    return short or title

FEEDS: Dict[str, Dict] = {
    "globenewswire_public_companies": {
        "url": (
            "https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
            "GlobeNewswire%20-%20News%20about%20Public%20Companies"
        ),
        "source_label": "GlobeNewswire",
        "kind": "company_announcement",
    },
    "prnewswire_financial_services": {
        "url": (
            "https://www.prnewswire.com/rss/financial-services-latest-news/"
            "financial-services-latest-news-list.rss"
        ),
        "source_label": "PR Newswire",
        "kind": "company_announcement",
    },
}

# Cache is time-based (not per-calendar-day like trending_stocks_service,
# since news freshness matters on a scale of minutes, not once-a-day).
_CACHE_TTL_SECONDS = 900  # 15 minutes -- frequent enough to feel live,
# infrequent enough that this stays a "good citizen" against each feed
# (same spirit as services/outbound_http.py's honest-UA/backoff already
# applied to every request this function makes).
_cache: Dict[str, Dict] = {}  # feed_id -> {"fetched_at": epoch, "items": [...]}


def _parse_pubdate(raw: Optional[str]) -> Optional[str]:
    """RSS 2.0 pubDate is RFC-822 (e.g. 'Fri, 26 Jun 2026 21:03:00 GMT').
    Returns an ISO-8601 string, or None if missing/unparseable -- never a
    fabricated timestamp."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _fetch_feed(feed_id: str) -> List[Dict]:
    cfg = FEEDS[feed_id]
    try:
        res = get_with_backoff(cfg["url"], timeout=10)
        if res.status_code != 200:
            logger.info("rss_news_service: %s returned HTTP %s", feed_id, res.status_code)
            return []
        root = ET.fromstring(res.content)
    except Exception as e:
        logger.info("rss_news_service: failed to fetch/parse %s: %s", feed_id, e)
        return []

    items = []
    # RSS 2.0 shape: <rss><channel><item>...</item></channel></rss>.
    # Some wires nest an Atom-style feed instead -- handle both defensively
    # rather than assuming every source is pure RSS 2.0.
    channel_items = root.findall(".//item")
    if not channel_items:
        channel_items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for it in channel_items:
        title_el = it.find("title")
        link_el = it.find("link")
        date_el = it.find("pubDate")
        if title_el is None:
            title_el = it.find("{http://www.w3.org/2005/Atom}title")
        if date_el is None:
            date_el = it.find("{http://www.w3.org/2005/Atom}published")

        title = (title_el.text or "").strip() if title_el is not None else None
        link = (link_el.text or "").strip() if link_el is not None and link_el.text else None
        if link is None and link_el is not None:
            # Atom uses <link href="..."/> instead of a text node
            link = link_el.get("href")

        if not title or not link:
            continue

        items.append({
            "title": title,
            "link": link,
            "published_at": _parse_pubdate(date_el.text if date_el is not None else None),
            "source": cfg["source_label"],
            "kind": cfg["kind"],
        })

    return items


def _get_feed_cached(feed_id: str) -> List[Dict]:
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(feed_id)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["items"]

    items = _fetch_feed(feed_id)
    if items:
        _cache[feed_id] = {"fetched_at": now, "items": items}
        return items

    # Fetch failed -- serve stale cache if we have one rather than a hard
    # empty result, same graceful-degradation convention as the rest of
    # this codebase's data services.
    if cached:
        return cached["items"]
    return []


def _gdelt_items_as_rss_shape(limit: int) -> List[Dict]:
    """Adapts gdelt_news_service's item shape to this module's shape
    (adds `kind` -- "market_news", same label investing_com_rss used to
    carry, so downstream consumers keying off `kind` -- e.g.
    ai_news_object_service.py's company_announcement boost -- see
    unchanged behavior). GDELT items already have title/link/
    published_at/source; this only adds the one missing field."""
    try:
        result = gdelt_news_service.get_global_macro_headlines(limit=limit)
    except Exception as e:
        logger.info("rss_news_service: GDELT macro headlines fetch failed: %s", e)
        return []
    return [{**item, "kind": "market_news"} for item in result.get("items", [])]


def get_all_headlines(limit: int = 40) -> Dict:
    """Merged, newest-first headlines across every configured RSS feed
    plus GDELT's global news monitoring (replacing investing_com_rss as
    of 2026-08-11 -- see this module's docstring)."""
    all_items: List[Dict] = []
    sources_ok = []
    for feed_id in FEEDS:
        items = _get_feed_cached(feed_id)
        if items:
            sources_ok.append(feed_id)
        all_items.extend(items)

    gdelt_items = _gdelt_items_as_rss_shape(limit)
    if gdelt_items:
        sources_ok.append("gdelt")
    all_items.extend(gdelt_items)

    all_items.sort(key=lambda x: x["published_at"] or "", reverse=True)
    return {
        "status": "ok" if all_items else "error",
        "items": all_items[:limit],
        "sources_used": sources_ok,
        "total_before_limit": len(all_items),
    }


_TICKER_STRIP_RE = re.compile(r"[^a-z0-9\s]")


def search_headlines(query: str, limit: int = 20) -> Dict:
    """
    Two complementary search paths merged together:
    (1) client-side keyword filter over the RSS pool (title-substring
        match against the company name/ticker) -- the practical way to
        get "per-company" coverage out of feeds that only offer broad
        category subscriptions (see this module's docstring: no
        per-ticker GlobeNewswire/PR Newswire feed exists, so filtering
        happens here instead of pretending a per-company feed exists).
    (2) GDELT's own server-side search (services/gdelt_news_service.py),
        added 2026-08-11 replacing investing_com_rss -- genuine
        full-text search across GDELT's global monitoring, not a
        substring filter over a fixed small pool, so it can surface
        per-company coverage the RSS pool alone would miss.
    Deduplicated by link before returning.

    2026-08-30: if `query` looks like a bare ticker (e.g. "AAPL"), it is
    resolved to its real SEC-registered company name (e.g. "Apple") via
    _resolve_company_name(), and BOTH the raw ticker and the resolved
    name are searched through both paths above, unioned together. Real
    headlines/articles almost always say "Apple", never "AAPL", so a
    ticker-only query structurally misses nearly everything for exactly
    the well-known names users are most likely to ask about. A query
    that isn't a bare ticker, or a ticker with no SEC match, searches
    exactly as before (single term, unchanged behavior).
    """
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "請輸入公司名稱或代號。", "items": []}

    needle = _TICKER_STRIP_RE.sub("", query.lower()).strip()
    if not needle:
        return {"status": "error", "message": "查詢字串無效。", "items": []}

    resolved_name = _resolve_company_name(query)
    search_terms = [query] if not resolved_name else [query, resolved_name]
    needles = {needle}
    if resolved_name:
        resolved_needle = _TICKER_STRIP_RE.sub("", resolved_name.lower()).strip()
        if resolved_needle:
            needles.add(resolved_needle)

    merged = get_all_headlines(limit=200)
    matches = [
        item for item in merged["items"]
        if any(n in _TICKER_STRIP_RE.sub("", item["title"].lower()) for n in needles)
    ]

    gdelt_matches: List[Dict] = []
    for term in search_terms:
        try:
            # 7-day window (was the function default of 3d, applied
            # implicitly here before this fix) -- widened for this call
            # site only; services/global_news_region_service.py's own
            # explicit timespan="2d" call is untouched.
            gdelt_result = gdelt_news_service.search_global_events(term, limit=limit, timespan="7d")
            gdelt_matches.extend(
                {**item, "kind": "market_news"} for item in gdelt_result.get("items", [])
            )
        except Exception as e:
            logger.info("rss_news_service: GDELT search failed for %r: %s", term, e)

    seen_links = set()
    combined: List[Dict] = []
    for item in matches + gdelt_matches:
        link = item.get("link")
        if link in seen_links:
            continue
        seen_links.add(link)
        combined.append(item)
    combined.sort(key=lambda x: x["published_at"] or "", reverse=True)

    return {
        "status": "ok" if combined else "error",
        "message": None if combined else f"暫時搵唔到同「{query}」相關嘅新聞/公告。",
        "query": query,
        "resolved_company_name": resolved_name,
        "items": combined[:limit],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_all_headlines(limit=10), indent=2, ensure_ascii=False))
