from fastapi import APIRouter

from engines.news_engine import NewsEngine
from engines.risk_engine import RiskEngine
from engines.scoring_engine import ScoringEngine

router = APIRouter()


@router.get("/full-analysis/{ticker}")
async def full_analysis(ticker: str):

    # Temporary mock values
    market_score = 78
    strategy_score = 82

    news_data = [
        {
            "title": f"{ticker} reports strong growth",
            "summary": "record profit and bullish outlook"
        }
    ]

    news_result = NewsEngine.analyze(news_data)

    risk_result = RiskEngine.calculate(
        volatility=25,
        event_risk=20,
        news_score=news_result["score"]
    )

    score_result = ScoringEngine.calculate(
        market_score=market_score,
        news_score=news_result["score"],
        strategy_score=strategy_score,
        overall_risk=risk_result["overall_risk"]
    )

    return {
        "ticker": ticker.upper(),

        "market_score": market_score,

        "strategy_score": strategy_score,

        "news": news_result,

        "risk": risk_result,

        "investment_score": score_result["final_score"],

        "rating": score_result["rating"]
    }