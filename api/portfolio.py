from fastapi import APIRouter
from engines.portfolio_engine import PortfolioEngine
from services.dashboard_snapshot_service import get_dashboard_tickers, compute_snapshots

router = APIRouter()


@router.get("/portfolio")
def portfolio(token: str = None):
    """
    Dashboard Portfolio Allocation panel. Was previously always the
    same 3 hardcoded stocks (NVDA/AAPL/MSFT) with fixed fake scores
    for every user, regardless of what they actually track. Now
    allocates across the user's real watchlist (or a small default
    basket if logged out / no watchlist yet), weighted by each
    ticker's real market_score computed from live data.
    """
    tickers = get_dashboard_tickers(token)
    snapshots = compute_snapshots(tickers)
    screener_results = [
        {"ticker": s["ticker"], "final_score": s["market_score"]}
        for s in snapshots
    ]
    return PortfolioEngine.allocate(screener_results)
