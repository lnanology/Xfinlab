"""
XFINLAB Analysis API
FastAPI endpoint: GET /api/analyze/{symbol}

Flow:
    MarketDataService → RuleEngine → ScoreEngine → RiskEngine → DecisionEngine
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

from services.market_data_service import MarketDataService
from engines.rule_engine import RuleEngine
from engines.score_engine import ScoreEngine
from engines.risk_engine import RiskEngine
from engines.decision_engine import DecisionEngine


# ============================================================
# App Setup
# ============================================================

app = FastAPI(
    title="XFINLAB Analysis API",
    description="Stock analysis using Rule → Score → Risk → Decision engines",
    version="1.0.0",
)


# ============================================================
# Pydantic Response Model
# ============================================================


class AnalysisResponse(BaseModel):
    """Response model for stock analysis endpoint"""

    symbol: str
    price: float
    volume_ratio: float
    rule_scores: dict
    score: float
    score_percent: float
    risk: str
    decision: str


# ============================================================
# Dependency Injection
# ============================================================


def get_stock_data_service() -> MarketDataService:
    return MarketDataService()


def get_rule_engine() -> RuleEngine:
    return RuleEngine()


def get_score_engine() -> ScoreEngine:
    return ScoreEngine()


def get_risk_engine() -> RiskEngine:
    return RiskEngine()


def get_decision_engine() -> DecisionEngine:
    return DecisionEngine()


# ============================================================
# Endpoint
# ============================================================


@app.get("/api/analyze/{symbol}", response_model=AnalysisResponse)
def analyze_symbol(
    symbol: str,
    market_svc: MarketDataService = Depends(get_stock_data_service),
    rule_engine: RuleEngine = Depends(get_rule_engine),
    score_engine: ScoreEngine = Depends(get_score_engine),
    risk_engine: RiskEngine = Depends(get_risk_engine),
    decision_engine: DecisionEngine = Depends(get_decision_engine),
):
    """
    Analyze a stock symbol through the full XFINLAB decision pipeline.

    Args:
        symbol (str): Stock ticker e.g. AAPL, NVDA, TSLA

    Returns:
        AnalysisResponse: Full analysis including score, risk, and decision
    """

    # Step 1: Fetch live market data
    market_data = market_svc.get_stock_data(symbol)
    if not market_data:
        raise HTTPException(
            status_code=404, detail=f"Symbol '{symbol}' not found or data unavailable"
        )

    # Step 2: Rule Engine - evaluate trading rules
    rule_scores = rule_engine.evaluate(
        {
            "volume_ratio": market_data["volume_ratio"],
            "trend": market_data["trend"],
            "breakout": market_data["breakout"],
            "sentiment": market_data["sentiment"],
        }
    )

    # Step 3: Score Engine - calculate total score
    score_result = score_engine.calculate(rule_scores)

    # Step 4: Risk Engine - use volume_ratio as volatility proxy
    volatility = market_data["volume_ratio"] * 15
    risk_result = risk_engine.assess(volatility)

    # Step 5: Decision Engine - make final decision
    decision_result = decision_engine.decide(score_result)

    return AnalysisResponse(
        symbol=market_data["symbol"],
        price=market_data["price"],
        volume_ratio=market_data["volume_ratio"],
        rule_scores=rule_scores,
        score=score_result["total_score"],
        score_percent=score_result["score_percent"],
        risk=risk_result["risk_level"],
        decision=decision_result["decision"],
    )


# ============================================================
# Health Check
# ============================================================


@app.get("/")
def health_check():
    """API health check"""
    return {"status": "ok", "service": "XFINLAB Analysis API v1.0"}
