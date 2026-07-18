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

  - Investing.com's general market news feed.
  - GlobeNewswire's "News about Public Companies" feed -- the practical
    stand-in for "listed-company IR/announcement pages": a 3-company
    spot check (AAPL/MSFT/JPM) found NONE of them has a working direct
    IR-site RSS feed of its own, but official company press releases
    (earnings, M&A, offerings, etc.) ARE distributed through
    GlobeNewswire/PR Newswire's public wires -- this is the honest,
    verified-live path to that data, not a workaround.
  - PR Newswire's "Financial Services" news feed, same reasoning.

Explicitly ruled OUT this pass (checked, not silently skipped -- see
services/license_registry.py for the same "documented, not assumed"
convention):
  - StockTwits: developer API registration is currently closed and their
    ToS bars automated extraction without an approved API -- no
    compliant path today (see services/license_registry.py's
    "stocktwits" entry, tracked as a real gap for task #212, not built).
  - Business Wire: public site showed stale content and no free RSS link
    in navigation; their own docs point to a paid feed product.
  - Seeking Alpha: feed terms explicitly restrict to personal,
    non-commercial use.
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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from services.outbound_http import get_with_backoff

logger = logging.getLogger(__name__)

FEEDS: Dict[str, Dict] = {
    "investing_com": {
        "url": "https://www.investing.com/rss/news.rss",
        "source_label": "Investing.com",
        "kind": "market_news",
    },
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


def get_all_headlines(limit: int = 40) -> Dict:
    """Merged, newest-first headlines across every configured feed."""
    all_items: List[Dict] = []
    sources_ok = []
    for feed_id in FEEDS:
        items = _get_feed_cached(feed_id)
        if items:
            sources_ok.append(feed_id)
        all_items.extend(items)

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
    Client-side keyword filter over the merged feed (title-substring
    match against the company name/ticker) -- the practical way to get
    "per-company" coverage out of feeds that only offer broad category
    subscriptions (see this module's docstring: no per-ticker GlobeNewswire/
    PR Newswire feed exists, so filtering happens here instead of pretending
    a per-company feed exists).
    """
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "請輸入公司名稱或代號。", "items": []}

    needle = _TICKER_STRIP_RE.sub("", query.lower()).strip()
    if not needle:
        return {"status": "error", "message": "查詢字串無效。", "items": []}

    merged = get_all_headlines(limit=200)
    matches = [
        item for item in merged["items"]
        if needle in _TICKER_STRIP_RE.sub("", item["title"].lower())
    ]
    return {
        "status": "ok" if matches else "error",
        "message": None if matches else f"暫時搵唔到同「{query}」相關嘅新聞/公告。",
        "query": query,
        "items": matches[:limit],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_all_headlines(limit=10), indent=2, ensure_ascii=False))
