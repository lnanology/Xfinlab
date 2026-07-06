
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter
from core.master_pipeline import MasterPipeline

router = APIRouter()

@router.get("/pipeline/{ticker}")
def run_pipeline(ticker: str):
    market_data = {"score": 75, "price": 298, "volatility": 35, "event_risk": 40, "volume": 2500}
    news_data = [{"title": f"{ticker} shows strong growth", "summary": "profit beat expectations"}]
    return MasterPipeline.run(ticker.upper(), market_data, news_data)
