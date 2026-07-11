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

Picks whichever ticker in a small liquid-stock basket currently has the
strongest confluence signal (|score| highest) -- makes the card feel
genuinely alive/current rather than pinned to one name forever, while
staying deterministic and explainable (same real formula used
everywhere else: services/technical_analysis_service.py's confluence
engine).
"""

import time
from fastapi import APIRouter

from services.technical_analysis_service import get_technical_analysis
from engines.risk_engine import RiskEngine

router = APIRouter()

_SHOWCASE_BASKET = ["TSLA", "NVDA", "AAPL", "MSFT", "GOOGL"]

_cache = None
_cache_time = 0
_CACHE_TTL_SECONDS = 300  # 5 minutes, same cadence as api/market_pulse.py


def _build_showcase():
    candidates = []
    for ticker in _SHOWCASE_BASKET:
        tech = get_technical_analysis(ticker)
        if not tech or "error" in tech:
            continue
        confluence = tech.get("confluence", {})
        candidates.append((ticker, tech, confluence))

    if not candidates:
        return None

    # Pick the strongest, clearest signal (most decisive |score|) rather
    # than always the same ticker -- real market conditions decide which
    # name shows up.
    best_ticker, tech, confluence = max(
        candidates, key=lambda c: abs(c[2].get("score", 0))
    )

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


@router.get("/hero-showcase")
def hero_showcase():
    global _cache, _cache_time
    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        return _cache

    result = _build_showcase()
    if result is None:
        # Data source unavailable for the whole basket -- return an
        # honest "unavailable" shape rather than serving stale/fake data.
        return {"available": False}

    payload = {"available": True, **result}
    _cache = payload
    _cache_time = now
    return payload
