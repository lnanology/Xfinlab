"""
Homepage Hero "Live AI Result" card.

Product decision (2026-07 rebrand): the Hero should show a REAL AI result,
not a static mockup screenshot, so a first-time visitor immediately sees
what the platform actually produces. This must NOT reuse
api/public_demo.py's /demo/analyze/{ticker} endpoint -- that endpoint is
each visitor's OWN personal 30-minute trial window (see
api/public_demo.py's docstring), and auto-firing it on every homepage
load would silently burn a visitor's trial budget before they ever get to
try it themselves.

Instead this is a small, separate, unthrottled endpoint in the same
spirit as api/market_pulse.py: real market data, real technical-analysis
math (services/technical_analysis_service.py -- zero AI-provider cost),
server-side cached for 5 minutes so it can be hit by every homepage
visitor without hammering the underlying data source or costing anything
per-view.

2026-07 update: the Hero card now auto-rotates through a basket of 10
liquid large-caps every 10 seconds (index.html's rotateHeroResult()),
rather than pinning to a single "strongest signal" pick. Basket matches
the site's existing 10 SEO landing pages (aapl.html/amzn.html/brk.html/
googl.html/jpm.html/meta.html/msft.html/nvda.html/tsla.html/v.html) so
the same 10 names are consistent across the site. Every entry in the
response is a REAL computed result (same confluence engine, same
Decision Score(TM)/Confidence(TM)/RiskDNA(TM) formulas used everywhere
else) -- there is no fabricated placeholder entry for a ticker whose
data fetch failed; it's simply omitted from the list.
"""

import time
from fastapi import APIRouter

from services.technical_analysis_service import get_technical_analysis
from engines.risk_engine import RiskEngine

router = APIRouter()

_SHOWCASE_BASKET = [
    "AAPL", "AMZN", "BRK-B", "GOOGL", "JPM",
    "META", "MSFT", "NVDA", "TSLA", "V",
]

_cache = None
_cache_time = 0
_CACHE_TTL_SECONDS = 300  # 5 minutes, same cadence as api/market_pulse.py


def _build_showcase_item(ticker: str):
    tech = get_technical_analysis(ticker)
    if not tech or "error" in tech:
        return None

    confluence = tech.get("confluence", {})
    score = confluence.get("score", 0)
    # Decision Score(TM): map confluence's -100..+100 net-signal score to
    # a 0-100 scale -- same (score+100)/2 mapping already used in
    # api/pipeline_api.py for the same purpose (avoid a second, different
    # convention for "confluence score out of 100" existing in the code).
    decision_score = round((score + 100) / 2, 1)
    direction = confluence.get("direction", "")
    if direction == "偏多":
        direction_label = "Bullish"
    elif direction == "偏空":
        direction_label = "Bearish"
    else:
        direction_label = "Neutral"

    volume_ratio = tech.get("volume_ratio") or 1.0
    risk = RiskEngine().assess(volume_ratio * 15)
    risk_label = risk["risk_level"].replace(" Risk", "")

    support = tech.get("support")
    resistance = tech.get("resistance")

    return {
        "ticker": tech["symbol"],
        "price": tech["last_close"],
        "decision_score": decision_score,
        "direction": direction_label,
        "confidence_pct": confluence.get("confidence_pct", 0),
        "risk_level": risk_label,
        "support": support["level"] if support else None,
        "resistance": resistance["level"] if resistance else None,
    }


def _build_showcase():
    items = []
    for ticker in _SHOWCASE_BASKET:
        item = _build_showcase_item(ticker)
        if item is not None:
            items.append(item)

    if not items:
        return None

    # Strongest, clearest signal first (most decisive |score|) -- purely
    # cosmetic ordering for whatever the card shows before the first
    # rotation tick; the frontend cycles through every item regardless.
    items.sort(key=lambda it: abs(it["decision_score"] - 50), reverse=True)
    return items


@router.get("/hero-showcase")
def hero_showcase():
    global _cache, _cache_time
    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        return _cache

    items = _build_showcase()
    if items is None:
        # Data source unavailable for the whole basket -- return an
        # honest "unavailable" shape rather than serving stale/fake data.
        return {"available": False}

    payload = {"available": True, "items": items}
    _cache = payload
    _cache_time = now
    return payload
