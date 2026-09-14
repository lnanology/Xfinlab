from fastapi import APIRouter
from services.quota_middleware import check_and_increment
from services.feature_flags_service import require_feature_enabled
from ai.research_agent import ResearchAgent
from services.market_data_service import MarketDataService

router = APIRouter()
market_service = MarketDataService()

@router.get("/research/{ticker}")
def research(ticker: str, token: str = None):
    # 2026-09-14: admin.html's "research_agent" toggle was persisted but
    # never actually enforced -- see services/feature_flags_service.py.
    require_feature_enabled("research_agent")
    # 2026-07-11 fix: 同api/report.py一樣，check_and_increment之前得
    # imported冇call過，令「3次/日」quota從未真正生效。
    check_and_increment(token, "research")

    market_data = market_service.get_stock_data(ticker.upper())
    return ResearchAgent.analyze(ticker.upper(), market_data)
