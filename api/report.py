from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from services.quota_middleware import check_and_increment
from fastapi.responses import FileResponse
from ai.research_agent import ResearchAgent
from ai.report_generator import ReportGenerator
from services.market_data_service import MarketDataService
import os

router = APIRouter()
market_service = MarketDataService()


class LiveReportRequest(BaseModel):
    """2026-07-31 (task #600): mirrors exactly the fields js/decision-
    footer.js's renderDecisionFooter() already accepts and renders on
    ai-analysis.html/chart-analysis.html -- the frontend just forwards the
    SAME object it already built for the on-screen Decision Report, so
    the PDF can never disagree with what's on screen. See ReportGenerator
    .generate_from_live_data()'s docstring for why this is a separate,
    simpler path from the older /report/{ticker} LLM-narrative endpoint
    below."""
    ticker: str
    decisionScore: Optional[float] = None
    confidencePct: Optional[float] = None
    riskLabel: Optional[str] = None
    keyReasons: Optional[List[str]] = None
    suggestedAction: Optional[str] = None
    invalidation: Optional[str] = None
    stopLoss: Optional[float] = None
    takeProfits: Optional[List[float]] = None
    riskPct: Optional[float] = None


@router.post("/report/generate")
def generate_live_report(body: LiveReportRequest, token: str = None):
    # Same free-tier point-earning gate every other AI-adjacent report/
    # analysis endpoint in this codebase already uses (see
    # services/quota_middleware.py's check_and_increment docstring --
    # never hard-blocks, just records a point for free users).
    check_and_increment(token, "report")

    ticker = body.ticker.upper().strip()
    pdf_path = ReportGenerator.generate_from_live_data(ticker, body.dict())

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path)
    )

@router.get("/report/{ticker}")
def generate_report(ticker: str, token: str = None):
    # 2026-07-11 fix: check_and_increment 之前得imported冇call過，
    # 即係PDF報告呢個功能一直冇real quota限制（FREE_LIMITS話明1次/日）。
    # 同api/full_analysis_v3.py用返同一個pattern。
    check_and_increment(token, "report")

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
