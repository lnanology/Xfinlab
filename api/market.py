from fastapi import APIRouter
from services.market_data_service import get_stock_data

router = APIRouter()


@router.get("/analyze/{symbol}")
def analyze_stock(symbol: str):
    return get_stock_data(symbol)
