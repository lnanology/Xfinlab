from fastapi import APIRouter
from engines.screener_engine import ScreenerEngine

router = APIRouter()

@router.get("/screener")
def screener():
    stocks = [
        {"ticker": "AAPL", "market_score": 94, "news_score": 53, "strategy_score": 50, "risk_score": 29},
        {"ticker": "NVDA", "market_score": 88, "news_score": 72, "strategy_score": 80, "risk_score": 45},
        {"ticker": "TSLA", "market_score": 60, "news_score": 40, "strategy_score": 55, "risk_score": 75}
    ]
    return ScreenerEngine.screen(stocks)
