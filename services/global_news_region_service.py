"""
Global News Region Filter (2026-07-24) -- part of the "全球新聞+宏觀AI評語"
layer, alongside services/macro_data_service.py.

This does NOT add new RSS feeds. It re-uses the existing, already-verified
-compliant pool from services/rss_news_service.py (Investing.com,
GlobeNewswire, PR Newswire) and filters it down to headlines relevant to
one of the 10 regions defined in services/macro_data_service.REGIONS, via
the same keyword-substring technique rss_news_service.search_headlines()
already uses for per-company filtering.

Honest scope limitation (documented, not silently assumed away): this
session verified BBC's business RSS feed (feeds.bbci.co.uk/news/business/
rss.xml) as live and added it here as a second, broader source, since it
carries more non-US/global coverage than the existing 3 US-centric wires.
Several other candidate region-specific feeds (Focus Taiwan, Taipei Times,
ChannelNewsAsia) were checked this same session and either returned empty
content or are domain-blocked for this environment's fetch tool -- NOT
added, rather than guessing they work. Region coverage today is therefore
"global wires filtered by keyword", not "one dedicated local feed per
country" -- genuinely local per-market feeds (SCMP, Nikkei Asia, Korea
Herald, etc.) remain a documented gap to fill incrementally as each one is
individually verified live, same convention as rss_news_service.py's own
"explicitly ruled out this pass" section.
"""

import logging
from typing import Dict, List

from services.macro_data_service import REGIONS
from services.outbound_http import get_with_backoff
from services.rss_news_service import _TICKER_STRIP_RE, get_all_headlines
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

_BBC_BUSINESS_URL = "https://feeds.bbci.co.uk/news/business/rss.xml"
_BBC_CACHE_TTL_SECONDS = 900
_bbc_cache: Dict = {"fetched_at": 0, "items": []}


def _parse_pubdate(raw):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _get_bbc_business_cached() -> List[Dict]:
    """BBC Business RSS -- verified live 2026-07-24 by direct fetch.
    Kept as its own small fetcher (rather than folding into
    rss_news_service.FEEDS) so this module's region-filter feature can
    ship independently without touching that already-stable module."""
    now = datetime.now(timezone.utc).timestamp()
    if _bbc_cache["items"] and (now - _bbc_cache["fetched_at"]) < _BBC_CACHE_TTL_SECONDS:
        return _bbc_cache["items"]

    try:
        res = get_with_backoff(_BBC_BUSINESS_URL, timeout=10)
        if res.status_code != 200:
            logger.info("global_news_region_service: BBC feed returned HTTP %s", res.status_code)
            return _bbc_cache["items"]
        root = ET.fromstring(res.content)
    except Exception as e:
        logger.info("global_news_region_service: BBC feed fetch failed: %s", e)
        return _bbc_cache["items"]

    items = []
    for it in root.findall(".//item"):
        title_el = it.find("title")
        link_el = it.find("link")
        date_el = it.find("pubDate")
        title = (title_el.text or "").strip() if title_el is not None else None
        link = (link_el.text or "").strip() if link_el is not None and link_el.text else None
        if not title or not link:
            continue
        items.append({
            "title": title,
            "link": link,
            "published_at": _parse_pubdate(date_el.text if date_el is not None else None),
            "source": "BBC Business",
            "kind": "market_news",
        })

    if items:
        _bbc_cache["fetched_at"] = now
        _bbc_cache["items"] = items
    return _bbc_cache["items"]


def get_region_headlines(region: str, limit: int = 8) -> Dict:
    """
    Filters the combined RSS pool (existing 3 US wires + BBC Business) down
    to headlines whose title contains one of the region's keywords (see
    services/macro_data_service.REGIONS).

    Returns:
        {"available": True, "region": "hk", "items": [...], "matched": 3}
        {"available": True, "region": "hk", "items": [], "matched": 0,
         "message": "..."} -- feeds fetched fine, just no keyword hits
            right now (normal for smaller markets on a quiet news day).
    """
    cfg = REGIONS.get(region)
    if not cfg:
        return {"available": False, "message": f"未知地區代碼：{region}"}

    pool = get_all_headlines(limit=200)["items"] + _get_bbc_business_cached()
    keywords = cfg["keywords"]

    matches = []
    seen_links = set()
    for item in pool:
        title_lower = _TICKER_STRIP_RE.sub("", item["title"].lower())
        if any(kw in item["title"].lower() for kw in keywords) and item["link"] not in seen_links:
            matches.append(item)
            seen_links.add(item["link"])

    matches.sort(key=lambda x: x["published_at"] or "", reverse=True)
    result = {
        "available": True,
        "region": region,
        "items": matches[:limit],
        "matched": len(matches),
    }
    if not matches:
        result["message"] = f"暫時未有同「{cfg['label']}」直接相關嘅頭條，可能今日新聞較少涉及呢個市場。"
    return result
