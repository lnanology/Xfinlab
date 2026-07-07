from fastapi import APIRouter
from services.quota_middleware import check_and_increment
from fastapi.responses import FileResponse
from ai.research_agent import ResearchAgent
from ai.report_generator import ReportGenerator
from services.market_data_service import MarketDataService
import os

router = APIRouter()
market_service = MarketDataService()

@router.get("/report/{ticker}")
def generate_report(ticker: str):
    ticker = ticker.upper()

    market_data = market_service.get_stock_data(ticker)
    analysis = {
        "ticker": ticker,
        "price": market_data.get("price", 0),
        "market_score": min(100, market_data.get("volume_ratio", 1) * 40 + 30),
        "news_score": 50,
        "strategy_score": 50,
        "risk_score": 30,
        "final_score": 65,
        "rating": "Neutral",
        "risk": {"risk_level": "LOW"}
    }

    research = ResearchAgent.analyze(ticker, market_data)
    pdf_path = ReportGenerator.generate(ticker, analysis, research)

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path)
    )
