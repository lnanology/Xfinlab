from fastapi import APIRouter
from services.quota_middleware import check_and_increment
from ai.research_agent import ResearchAgent
from services.market_data_service import MarketDataService

router = APIRouter()
market_service = MarketDataService()

@router.get("/research/{ticker}")
def research(ticker: str):
    market_data = market_service.get_stock_data(ticker.upper())
    return ResearchAgent.analyze(ticker.upper(), market_data)
