from fastapi import APIRouter

from engines.portfolio_engine import PortfolioEngine

router = APIRouter()


@router.get("/portfolio")
def portfolio():

    screener_results = [
        {
            "ticker": "NVDA",
            "final_score": 76.5
        },
        {
            "ticker": "AAPL",
            "final_score": 68.2
        },
        {
            "ticker": "MSFT",
            "final_score": 72.8
        }
    ]

    return PortfolioEngine.allocate(
        screener_results
    )