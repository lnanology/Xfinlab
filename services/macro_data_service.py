"""
Global Macro Data Service (2026-07-24) -- backend for the "全球新聞+宏觀AI評語"
(global news + macro AI commentary) layer.

Context: the user's core problem is that legitimate, commercially-licensed
LIVE market data for non-US exchanges (HK/TW/JP/KR/etc) costs real money
per market (see services/license_registry.py + this session's cost
research: HKEX official delayed-data redistribution licence is the
cheapest verified path at ~US$640/month for Hong Kong ALONE -- there is no
free way to legally show per-market real-time/EOD equity prices to paying
users across a dozen countries at once).

But the user's marketing (multi-language YouTube) is pulling in viewers
from many different countries NOW, before revenue justifies paying for
a dozen separate exchange licences. This service is the honest middle
ground: give every region a genuine, legally-clean piece of context
(macro economic indicators) TODAY, at zero cost, while the deeper
per-market equity data gets added market-by-market as revenue allows
(HKEX first, per the user's own priority).

Data source: the World Bank Open Data API (api.worldbank.org). Verified
live by direct fetch on 2026-07-24. This is a public-domain / CC-BY
dataset explicitly intended for reuse including commercial products (see
https://data.worldbank.org/summary-terms-of-use) -- unlike yfinance/
Twelve Data's free tiers, there is no personal-use-only restriction here.
No API key needed.

Known gap, documented rather than silently papered over (same convention
as services/rss_news_service.py's "explicitly ruled out" section):
Taiwan (TWN) is NOT a World Bank member and returns an empty result set
(confirmed by direct fetch) -- callers must treat this as "macro
unavailable" for Taiwan, not retry-as-if-transient. Taiwan is already
covered on the market-data side by the existing free official TWSE
source; this gap is specific to macro indicators only.

Indicators pulled (annual; World Bank data lags 6-18 months behind
present -- this is background economic context, not a live signal, and
must never be presented to users as "today's" number):
  - NY.GDP.MKTP.KD.ZG  GDP growth, annual %
  - FP.CPI.TOTL.ZG     Inflation (consumer prices), annual %
  - SL.UEM.TOTL.ZS     Unemployment, % of total labour force

Honesty contract (same standard as finbert_sentiment_service.py): if the
World Bank API fails or a region has no data, callers get an explicit
"available": False with a message -- never a fabricated/interpolated
number.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from services.outbound_http import get_with_backoff

logger = logging.getLogger(__name__)

WORLD_BANK_BASE = "https://api.worldbank.org/v2/country"

# Region key -> (display label, World Bank ISO3 country code used as a
# representative proxy for that region, plus the news-keyword list used
# by services/global_news_region_service.py to filter the shared RSS
# pool down to region-relevant headlines).
#
# Representative-proxy note: several of these "regions" are broad
# multi-country groupings (Europe / Southeast Asia / Middle East / South
# America) that don't map to a single World Bank entity the way a single
# country does. Rather than silently pick one country and call it the
# whole region's number, each entry is honestly labelled with which
# specific country's indicator is actually being shown.
REGIONS: Dict[str, Dict] = {
    "us":     {"label": "美國",     "label_en": "United States",     "wb_code": "USA", "keywords": ["united states", "u.s.", "usa", "wall street", "fed ", "federal reserve", "s&p 500", "nasdaq", "dow jones"]},
    "europe": {"label": "歐洲(以英國為例)", "label_en": "Europe (UK as proxy)", "wb_code": "GBR", "keywords": ["europe", "eu ", "eurozone", "uk ", "britain", "bank of england", "ecb", "european"]},
    "japan":  {"label": "日本",     "label_en": "Japan",              "wb_code": "JPN", "keywords": ["japan", "tokyo", "nikkei", "boj", "bank of japan", "yen"]},
    "korea":  {"label": "韓國",     "label_en": "South Korea",        "wb_code": "KOR", "keywords": ["korea", "seoul", "kospi", "won", "samsung", "sk hynix"]},
    "china":  {"label": "中國",     "label_en": "China",              "wb_code": "CHN", "keywords": ["china", "chinese", "beijing", "shanghai", "shenzhen", "yuan", "renminbi", "pboc"]},
    "hk":     {"label": "香港",     "label_en": "Hong Kong",          "wb_code": "HKG", "keywords": ["hong kong", "hkex", "hang seng", "hsbc"]},
    "tw":     {"label": "台灣",     "label_en": "Taiwan",             "wb_code": "TWN", "keywords": ["taiwan", "taipei", "tsmc", "taiex"]},
    "sea":    {"label": "東南亞(以新加坡為例)", "label_en": "Southeast Asia (Singapore as proxy)", "wb_code": "SGP", "keywords": ["singapore", "asean", "southeast asia", "malaysia", "indonesia", "thailand", "vietnam", "philippines"]},
    "me":     {"label": "中東(以沙特為例)", "label_en": "Middle East (Saudi Arabia as proxy)", "wb_code": "SAU", "keywords": ["middle east", "saudi", "uae", "dubai", "qatar", "opec", "gulf"]},
    "latam":  {"label": "南美(以巴西為例)", "label_en": "South America (Brazil as proxy)", "wb_code": "BRA", "keywords": ["brazil", "latin america", "south america", "mexico", "argentina", "bovespa"]},
}

_INDICATORS = {
    "gdp_growth_pct": "NY.GDP.MKTP.KD.ZG",
    "inflation_pct": "FP.CPI.TOTL.ZG",
    "unemployment_pct": "SL.UEM.TOTL.ZS",
}

# Cache TTL is long (macro data is annual and updates a handful of times a
# year at most) -- refetching more than once a day would be pointless
# load on the World Bank API for data that hasn't changed.
_CACHE_TTL_SECONDS = 24 * 3600
_cache: Dict[str, Dict] = {}  # wb_code -> {"fetched_at": epoch, "data": {...}}


def list_regions() -> List[Dict]:
    return [
        {"region": key, "label": v["label"], "label_en": v["label_en"], "wb_code": v["wb_code"]}
        for key, v in REGIONS.items()
    ]


def _fetch_indicator(wb_code: str, indicator_id: str) -> Optional[Dict]:
    """Returns the single most-recent non-null observation for one
    indicator, or None if the API failed / has no data for this country
    (e.g. Taiwan, which isn't a World Bank member -- see module
    docstring)."""
    url = f"{WORLD_BANK_BASE}/{wb_code}/indicator/{indicator_id}"
    try:
        res = get_with_backoff(url, params={"format": "json", "per_page": 5}, timeout=10)
        if res.status_code != 200:
            logger.info("macro_data_service: %s/%s returned HTTP %s", wb_code, indicator_id, res.status_code)
            return None
        payload = res.json()
    except Exception as e:
        logger.info("macro_data_service: failed to fetch %s/%s: %s", wb_code, indicator_id, e)
        return None

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        # World Bank returns [meta, []] (empty data array) for
        # non-member entities like Taiwan -- honest "no data", not an error.
        return None

    for row in payload[1]:
        if row.get("value") is not None:
            return {"year": row.get("date"), "value": round(row["value"], 2)}
    return None


def get_macro_snapshot(region: str) -> Dict:
    """
    Returns:
        {"available": True, "region": "hk", "label": "香港", "wb_code": "HKG",
         "as_of": "2026-07-24T...", "indicators": {
             "gdp_growth_pct": {"year": "2025", "value": 3.49},
             "inflation_pct": {"year": "2025", "value": 1.8} or None,
             "unemployment_pct": {"year": "2024", "value": 3.1} or None,
         }}
        {"available": False, "message": "..."} -- unknown region key, or
            World Bank has genuinely no data for this entity at all
            (Taiwan: every indicator comes back None -- callers should
            fall back to news-only coverage for that region, never
            fabricate a placeholder number).
    """
    cfg = REGIONS.get(region)
    if not cfg:
        return {"available": False, "message": f"未知地區代碼：{region}"}

    wb_code = cfg["wb_code"]
    now = datetime.now(timezone.utc).timestamp()
    cached = _cache.get(wb_code)
    if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        indicators = cached["data"]
    else:
        indicators = {}
        for key, indicator_id in _INDICATORS.items():
            indicators[key] = _fetch_indicator(wb_code, indicator_id)
        # Cache even a mostly-empty result (e.g. Taiwan) -- re-fetching
        # every request for an entity that will never have World Bank
        # data is pointless load.
        _cache[wb_code] = {"fetched_at": now, "data": indicators}

    if all(v is None for v in indicators.values()):
        return {
            "available": False,
            "region": region,
            "label": cfg["label"],
            "wb_code": wb_code,
            "message": f"{cfg['label']}暫時冇公開宏觀數據（World Bank未收錄呢個地區）。",
        }

    return {
        "available": True,
        "region": region,
        "label": cfg["label"],
        "label_en": cfg["label_en"],
        "wb_code": wb_code,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators,
    }


if __name__ == "__main__":
    import json
    for r in REGIONS:
        print(json.dumps(get_macro_snapshot(r), indent=2, ensure_ascii=False))
