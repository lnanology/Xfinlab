"""
XFINLAB Full Analysis V3
Real pipeline: market_data → strategy → news → risk → scoring → decision

GET /api/full-analysis/{ticker}
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter
from services.quota_middleware import check_and_increment, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.market_data_service import MarketDataService
from services.news_service import NewsService
from engines.strategy_engine import StrategyEngine
from engines.news_engine import NewsEngine
from engines.risk_engine import RiskEngine
from engines.decision_engine import DecisionEngine

router = APIRouter()

# ============================================================
# Response Model
# ============================================================

class FullAnalysisResponse(BaseModel):
    ticker: str
    price: Optional[float]
    market_score: float
    strategy_score: float
    news_score: float
    risk_score: float
    final_score: float
    rating: str
    news: dict
    risk: dict


# ============================================================
# Services & Engines (singleton)
# ============================================================

market_service = MarketDataService()
news_service = NewsService()
strategy_engine = StrategyEngine("strategies/AJ_Strategy_V1.json")
decision_engine = DecisionEngine()


# ============================================================
# Endpoint
# ============================================================

@router.get("/full-analysis/{ticker}", response_model=FullAnalysisResponse)
async def full_analysis(ticker: str, token: str = None):
    """
    Full investment analysis pipeline

    Flow:
        MarketDataService → market_score
        StrategyEngine    → strategy_score
        NewsService       → news articles
        NewsEngine        → news_score
        RiskEngine        → risk_score
        ScoringEngine     → final_score + rating

    Args:
        ticker (str): Stock symbol e.g. AAPL, NVDA, TSLA

    Returns:
        FullAnalysisResponse: Complete investment decision
    """
    check_and_increment(token, "full_analysis")
    symbol = ticker.upper()

    # ── Step 1: Market Data ──────────────────────────────
    try:
        market_data = market_service.get_stock_data(symbol)
        price = market_data.get("price", 0)
        volume_ratio = market_data.get("volume_ratio", 1.0)

        # Convert volume ratio to market score (0-100)
        market_score = min(100, round(volume_ratio * 40 + 30, 2))

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Market data error for {symbol}: {str(e)}")

    # ── Step 2: Strategy Score ───────────────────────────
    try:
        strategy_input = {
            "volume_ratio": market_data.get("volume_ratio", 1.0),
            "trend": market_data.get("trend", "neutral"),
            "breakout": market_data.get("breakout", False),
            "sentiment": market_data.get("sentiment", "neutral"),
        }
        strategy_result = strategy_engine.evaluate(strategy_input)
        strategy_score = min(100, round(sum(strategy_result.values()) * 1.0, 2))

    except Exception:
        strategy_score = 50.0  # Fallback

    # ── Step 3: News Data ────────────────────────────────
    try:
        raw_news = news_service.get_company_news(symbol)
        news_data = [
            {
                "title": article.get("title", ""),
                "summary": article.get("title", "")  # Use title as summary
            }
            for article in raw_news[:10]
        ]
    except Exception:
        news_data = []

    # ── Step 4: News Engine ──────────────────────────────
    news_result = NewsEngine.analyze(news_data)
    news_score = news_result["score"]

    # ── Step 5: Risk Engine ──────────────────────────────
    volatility = volume_ratio * 15  # Proxy for volatility
    risk_result = RiskEngine.calculate(
        volatility=volatility,
        event_risk=20,
        news_score=news_score
    )
    risk_score = risk_result["overall_risk"]

    # ── Step 6: Final Score ──────────────────────────────
    # Routed through DecisionEngine.decide_full() (which itself calls
    # ScoringEngine.calculate() -- same formula, now centralized) so this
    # endpoint uses the one real "decision engine" going forward instead of
    # reaching into ScoringEngine directly. Output is unchanged.
    score_result = decision_engine.decide_full(
        market_score=market_score,
        news_score=news_score,
        strategy_score=strategy_score,
        overall_risk=risk_score
    )

    return FullAnalysisResponse(
        ticker=symbol,
        price=price,
        market_score=market_score,
        strategy_score=strategy_score,
        news_score=news_score,
        risk_score=risk_score,
        final_score=score_result["final_score"],
        rating=score_result["rating"],
        news=news_result,
        risk=risk_result,
    )
