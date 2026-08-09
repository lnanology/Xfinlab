"""
World Engine Phase 0 -- 2026-08-09 (XFINLAB_Final_Strategy.md section
5/6/7, "重新包裝GDELT+FRED/ECB+FinBERT做「全球市場地圖」,同步做新API tier").

This is deliberately a REPACKAGING layer, not a new data source. Every
underlying fetch already existed and shipped in earlier tasks:
  - services/gdelt_news_service.py       -- global news (GDELT, #557)
  - services/macro_data_service.py       -- macro baseline, 10 regions
                                             (World Bank, #374)
  - services/fred_macro_service.py       -- US high-frequency macro
                                             override (new, this task)
  - services/ecb_macro_service.py        -- Eurozone macro override
                                             (new, this task)
  - services/global_news_region_service.py -- region-filtered headlines
                                             (#375)
  - services/finbert_sentiment_service.py -- real sentiment scoring (#266)

What's new here is a single call that returns a structured snapshot
across ALL regions at once -- "a global market map" -- suitable for (a)
a new Intelligence API endpoint/tier (api/intelligence.py's
/v1/world/market-map) and (b) an MCP tool (api/mcp_server.py's
get_global_market_map), both aimed at the same B2B-API-first positioning
as the rest of the Intelligence API: real structured data for a
developer/AI-agent to read, never a directional signal.

Deliberately excludes services/global_macro_commentary_service.py's AI
narrative paragraph -- that call costs one LLM invocation PER region,
which is fine for a single-region homepage widget but would make a
10-region "map everything at once" API call needlessly expensive (10x
LLM calls) for a product whose entire value proposition is "cheap
structured data, not AI opinion." Callers who want an AI paragraph can
still call the existing /v1/intel endpoints per-ticker or the homepage
commentary directly; this module returns numbers and headlines only.

Honesty contract (same standard as every module above): a region's macro
block reflects exactly which source actually answered (World Bank vs
FRED vs ECB, each response says so explicitly via `macro_source`) --
never silently blended or overwritten with a fabricated composite.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services import ecb_macro_service, fred_macro_service, gdelt_news_service
from services.finbert_sentiment_service import analyze_batch as finbert_analyze_batch
from services.global_news_region_service import get_region_headlines
from services.macro_data_service import REGIONS, get_macro_snapshot

logger = logging.getLogger(__name__)


def _get_macro_for_region(region: str) -> Dict:
    """World Bank is the always-available baseline (annual, ~190
    countries). FRED overrides for 'us' and ECB overrides for 'europe'
    when their respective services are available/successful -- both are
    higher-frequency, non-proxy sources for those two regions
    specifically. Every other region keeps the World Bank baseline;
    there is no FRED/ECB equivalent for e.g. Korea or Brazil."""
    baseline = get_macro_snapshot(region)

    if region == "us" and fred_macro_service.is_available():
        fred_result = fred_macro_service.get_us_snapshot()
        if fred_result.get("available"):
            fred_result["macro_source"] = "fred"
            fred_result["fallback_available"] = baseline.get("available", False)
            return fred_result

    if region == "europe":
        ecb_result = ecb_macro_service.get_eurozone_snapshot()
        if ecb_result.get("available"):
            ecb_result["macro_source"] = "ecb"
            ecb_result["fallback_available"] = baseline.get("available", False)
            return ecb_result

    baseline["macro_source"] = "world_bank" if baseline.get("available") else None
    return baseline


def get_region_snapshot(region: str, news_limit: int = 6, include_sentiment: bool = True) -> Dict:
    """
    Returns:
        {"available": True, "region": "hk", "label": "香港",
         "macro": {...}, "macro_source": "world_bank"|"fred"|"ecb",
         "news": {...}, "sentiment": {...} | None}
        {"available": False, "message": "..."} -- unknown region key only.
    """
    cfg = REGIONS.get(region)
    if not cfg:
        return {"available": False, "message": f"未知地區代碼：{region}"}

    macro = _get_macro_for_region(region)
    news = get_region_headlines(region, limit=news_limit)

    sentiment = None
    if include_sentiment and news.get("items"):
        titles = [item["title"] for item in news["items"]]
        finbert_result = finbert_analyze_batch(titles)
        if finbert_result.get("available"):
            scores = [r["score"] for r in finbert_result["results"]]
            avg = round(sum(scores) / len(scores), 1)
            sentiment = {
                "available": True,
                "source": "finbert",
                "avg_score": avg,
                "label": "Positive" if avg >= 70 else "Negative" if avg < 40 else "Neutral",
                "n_headlines": len(scores),
            }
        else:
            sentiment = {"available": False, "message": finbert_result.get("message")}

    return {
        "available": True,
        "region": region,
        "label": cfg["label"],
        "label_en": cfg["label_en"],
        "macro": macro,
        "macro_source": macro.get("macro_source"),
        "news": news,
        "sentiment": sentiment,
    }


def get_global_market_map(regions: Optional[List[str]] = None, news_limit: int = 6, include_sentiment: bool = True) -> Dict:
    """
    The actual "World Engine" product surface: one call, every region.

    Returns:
        {"as_of": "...", "regions": {"us": {...}, "hk": {...}, ...},
         "global_headlines": {...}}  -- see gdelt_news_service.get_global_macro_headlines()

    `regions` defaults to all 10 keys in macro_data_service.REGIONS; a
    caller may pass a subset (e.g. ["us", "hk", "china"]) to reduce the
    number of FinBERT/GDELT calls for a cheaper, faster response --
    reflected in api/intelligence.py's quota weighting (see that file's
    ENDPOINT_WEIGHT comment for world_map).
    """
    target_regions = [r for r in (regions or list(REGIONS.keys())) if r in REGIONS]
    if not target_regions:
        return {"available": False, "message": "冇有效嘅地區代碼。"}

    region_snapshots = {
        r: get_region_snapshot(r, news_limit=news_limit, include_sentiment=include_sentiment)
        for r in target_regions
    }

    try:
        global_headlines = gdelt_news_service.get_global_macro_headlines(limit=20)
    except Exception as e:
        logger.info("world_engine_service: global headlines fetch failed: %s", e)
        global_headlines = {"status": "error", "items": [], "total_before_limit": 0}

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regions": region_snapshots,
        "global_headlines": global_headlines,
    }


def list_regions() -> List[Dict]:
    """Thin passthrough of macro_data_service.list_regions() so API/MCP
    consumers of this module don't need to import that module directly
    just to discover valid region keys."""
    return [
        {"region": key, "label": v["label"], "label_en": v["label_en"]}
        for key, v in REGIONS.items()
    ]


if __name__ == "__main__":
    import json
    print(json.dumps(get_global_market_map(regions=["us", "hk"]), indent=2, ensure_ascii=False, default=str))
