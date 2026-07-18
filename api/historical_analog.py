from fastapi import APIRouter

from services.historical_analog_service import find_analogs

router = APIRouter()


@router.get("/historical-analog/{symbol}")
def historical_analog(symbol: str, forward_days: int = 10, period: str = "2y"):
    """Honest 'what actually happened last time this ticker was in a
    similar trend+volatility regime' read -- see services/
    historical_analog_service.py's docstring for why this replaces a
    fabricated macro-shock-slider design."""
    return find_analogs(symbol, period=period, forward_days=forward_days)
