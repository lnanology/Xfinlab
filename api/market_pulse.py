"""
Live Market Pulse -- homepage-level "global sentiment" summary.

Part of the CRO/Neuro-UX homepage proposal (see
HOMEPAGE_CRO_REDESIGN_PROPOSAL.md, Phase E: 🟡 medium risk, but explicitly
flagged there as "無新增cost（用現有Alpaca/yfinance）" and not gated behind
any of the 🔴 high-risk decisions (no login-bypass AI cost, no fabricated
authority claims, no fabricated testimonials, no colour rebrand).

Design:
- Aggregates a small, fixed basket of broad-market + sector proxies (SPY/
  QQQ/DIA/IWM for broad US equities, XLK/XLF/XLE for sector rotation, plus
  BTC-USD for crypto) using the EXISTING, already-audited
  services/technical_analysis_service.py Confluence Engine -- same real
  price-action math (trend/RSI/MACD/support-resistance/Fibonacci) already
  used everywhere else on the site, zero AI-provider cost.
- Averages each basket member's confluence score into one overall
  sentiment reading, plus a per-ticker breakdown SORTED by confluence
  score (strongest first) so it reads as a sector-rotation leaderboard
  rather than a static grid -- "which sector is strongest right now" is
  more useful and more "alive" feeling than an unordered list.
- Cached in-memory for 5 minutes: this runs on every homepage load
  (including the client-side auto-refresh in index.html), so without a
  cache it would refetch 8 tickers' worth of history from Alpaca/yfinance
  on every single visitor/refresh cycle. A stale-by-5-minutes market
  sentiment reading is a completely reasonable tradeoff for a homepage
  widget (this is explicitly NOT the same code path as
  api/chart_analysis.py's ticker-specific analysis, which stays uncached
  beyond its own 10-minute AI-response cache).
"""

import time
from typing import Dict, List, Optional

from fastapi import APIRouter

from services.technical_analysis_service import get_technical_analysis

router = APIRouter()

_PULSE_BASKET = ["SPY", "QQQ", "DIA", "IWM", "XLK", "XLF", "XLE", "BTC-USD"]
_PULSE_LABELS = {
    "SPY": "美股大盤", "QQQ": "科技股", "DIA": "道瓊工業", "IWM": "小型股",
    "XLK": "科技板塊", "XLF": "金融板塊", "XLE": "能源板塊", "BTC-USD": "加密貨幣",
}

_CACHE_TTL_SECONDS = 300
_cache: Optional[Dict] = None
_cache_time: float = 0.0


def _compute_pulse() -> Dict:
    breakdown: List[Dict] = []
    scores: List[float] = []

    for ticker in _PULSE_BASKET:
        try:
            tech = get_technical_analysis(ticker, period="3mo")
        except Exception as e:
            tech = {"error": str(e)}

        if not tech or "error" in tech:
            breakdown.append({
                "ticker": ticker,
                "label": _PULSE_LABELS.get(ticker, ticker),
                "available": False,
            })
            continue

        confluence = tech.get("confluence", {})
        score = confluence.get("score", 0.0)
        scores.append(score)
        breakdown.append({
            "ticker": ticker,
            "label": _PULSE_LABELS.get(ticker, ticker),
            "available": True,
            "price": tech.get("last_close"),
            "trend": tech.get("trend"),
            "rsi": tech.get("rsi"),
            "confluence_direction": confluence.get("direction"),
            "confluence_score": score,
        })

    if scores:
        avg_score = round(sum(scores) / len(scores), 1)
    else:
        avg_score = 0.0

    if not scores:
        overall = "數據不足"
    elif avg_score >= 20:
        overall = "偏多"
    elif avg_score <= -20:
        overall = "偏空"
    else:
        overall = "訊號分歧，中性"

    # Simple dispersion-based "volatility" read: how spread out the basket's
    # individual scores are from the average -- wide spread = markets
    # disagreeing with each other = choppier/more uncertain conditions.
    if len(scores) >= 2:
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        dispersion = round(variance ** 0.5, 1)
    else:
        dispersion = None

    if dispersion is None:
        volatility_desc = "數據不足"
    elif dispersion >= 50:
        volatility_desc = "市場分歧大"
    elif dispersion >= 25:
        volatility_desc = "中等波動"
    else:
        volatility_desc = "市場方向一致"

    # Sort available members by confluence score descending -- turns the
    # basket into a sector-rotation leaderboard ("what's strongest right
    # now") instead of a fixed-order grid. Unavailable members (data fetch
    # failed) sort last so the ranking only reflects real data.
    available = [b for b in breakdown if b.get("available")]
    unavailable = [b for b in breakdown if not b.get("available")]
    available.sort(key=lambda b: b["confluence_score"], reverse=True)
    sorted_breakdown = available + unavailable
    top_sector = available[0] if available else None

    return {
        "overall_sentiment": overall,
        "overall_score": avg_score,
        "volatility_desc": volatility_desc,
        "top_sector": {
            "label": top_sector["label"],
            "ticker": top_sector["ticker"],
            "confluence_direction": top_sector["confluence_direction"],
        } if top_sector else None,
        "basket": sorted_breakdown,
        "data_source": "即市技術分析（真實價格數據，非AI猜測）",
        "disclaimer": "呢個係整體市場技術面參考，唔係投資建議。",
    }


@router.get("/market-pulse")
def market_pulse():
    global _cache, _cache_time

    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL_SECONDS:
        return {**_cache, "cached": True}

    result = _compute_pulse()
    _cache = result
    _cache_time = now
    return {**result, "cached": False}
