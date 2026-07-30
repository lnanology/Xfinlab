"""
GDELT Global Events/News Service -- 2026-07-31.

Added following a review of the user's Market Data Gateway proposal:
GDELT's own terms make all datasets "available for unlimited and
unrestricted use for any academic, commercial, or governmental use of
any kind without fee" (see gdeltproject.org/about.html) -- a genuinely
free-and-commercial-clean source, unlike several others reviewed in the
same pass (Polygon/Twelve Data/Tiingo/EODHD free tiers, which explicitly
bar commercial/third-party display -- see services/license_registry.py).
No API key needed.

Uses the GDELT 2.0 DOC API (article-level search across GDELT's global
news monitoring), the practical equivalent of rss_news_service.py's feed
ingestion but with actual server-side keyword/topic search instead of
client-side substring filtering over a fixed set of feeds -- useful for
"what is global news saying about X right now" queries that a US-centric
RSS feed wouldn't surface well.

Same minimal-retention convention as rss_news_service.py /
NewsService.get_company_news(): only title/link/published_at/source/
language/country are ever kept, never full article text. Users are
pointed back to the original article via `link`.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff

logger = logging.getLogger(__name__)

GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

_CACHE_TTL_SECONDS = 900  # 15 minutes -- same cadence as rss_news_service.py
_cache: Dict[str, Dict] = {}  # cache_key -> {"fetched_at": epoch, "items": [...]}


def _parse_seendate(raw: Optional[str]) -> Optional[str]:
    """GDELT's `seendate` is 'YYYYMMDDHHMMSS' (UTC, no separators).
    Returns an ISO-8601 string, or None if missing/unparseable -- never a
    fabricated timestamp."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _query_gdelt(query: str, limit: int, timespan: Optional[str]) -> List[Dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "DateDesc",
        "maxrecords": min(max(limit, 1), 250),
    }
    if timespan:
        params["timespan"] = timespan

    try:
        res = get_with_backoff(GDELT_DOC_API_URL, params=params, timeout=15)
        if res.status_code != 200:
            logger.info("gdelt_news_service: HTTP %s for query=%r", res.status_code, query)
            return []
        payload = res.json()
    except Exception as e:
        logger.info("gdelt_news_service: failed to fetch/parse query=%r: %s", query, e)
        return []

    items: List[Dict] = []
    for art in payload.get("articles", []) or []:
        title = (art.get("title") or "").strip()
        link = art.get("url")
        if not title or not link:
            continue
        items.append({
            "title": title,
            "link": link,
            "published_at": _parse_seendate(art.get("seendate")),
            "source": art.get("domain") or "GDELT",
            "language": art.get("language"),
            "source_country": art.get("sourcecountry"),
        })
    return items


def _query_gdelt_cached(cache_key: str, query: str, limit: int, timespan: Optional[str]) -> List[Dict]:
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(cache_key)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["items"]

    items = _query_gdelt(query, limit, timespan)
    if items:
        _cache[cache_key] = {"fetched_at": now, "items": items}
        return items

    # Fetch failed -- serve stale cache if we have one, same graceful-
    # degradation convention as rss_news_service.py, rather than a hard
    # empty result.
    if cached:
        return cached["items"]
    return []


def get_global_macro_headlines(limit: int = 40) -> Dict:
    """Broad global economy/markets news, newest-first -- the GDELT
    equivalent of rss_news_service.get_all_headlines(), but pulling from
    GDELT's full global monitoring (100+ languages, translated to
    English titles) instead of a fixed set of English-language wires."""
    query = "(economy OR markets OR inflation OR earnings OR \"central bank\") sourcelang:english"
    items = _query_gdelt_cached(f"macro:{limit}", query, limit, timespan="1d")
    return {
        "status": "ok" if items else "error",
        "items": items[:limit],
        "total_before_limit": len(items),
    }


def search_global_events(query: str, limit: int = 20, timespan: str = "3d") -> Dict:
    """
    Server-side keyword search across GDELT's global news monitoring --
    for "what is global/non-US news saying about X" queries a US-centric
    RSS wire wouldn't surface. `query` can be a company name, ticker,
    country, or topic; passed close to as-is to GDELT's own search
    syntax (which supports quoted phrases and boolean OR/AND).
    """
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "請輸入查詢字詞。", "items": []}

    safe_query = query if len(query) <= 200 else query[:200]
    items = _query_gdelt_cached(f"search:{safe_query}:{limit}:{timespan}", safe_query, limit, timespan)
    return {
        "status": "ok" if items else "error",
        "message": None if items else f"暫時響全球新聞搵唔到同「{query}」相關嘅報導。",
        "query": query,
        "items": items[:limit],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_global_macro_headlines(limit=10), indent=2, ensure_ascii=False))
